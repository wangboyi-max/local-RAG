import jieba.analyse

from app.config import settings
from app.services.embeddings import get_embeddings
from app.services.vector_store import VectorStoreService
from app.services.graph_store import GraphStoreService, STOP_WORDS


class RetrievalPipeline:
    def __init__(
        self,
        vector_store: VectorStoreService,
        graph_store: GraphStoreService | None = None,
    ):
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.embeddings = get_embeddings()

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        """混合检索：向量语义 + 图谱实体扩展，合并去重后返回。"""
        k = top_k or settings.top_k

        # 1. 向量检索
        query_embedding = self.embeddings.embed_query(query)
        results = self.vector_store.query(query_embedding, top_k=k)

        vector_chunks = []
        seen_chunk_ids = set()
        if results.get("documents") and results["documents"][0]:
            docs = results["documents"][0]
            metadatas = results.get("metadatas", [None] * len(docs))[0] or []
            distances = results.get("distances", [[]])[0] or []
            for i, (doc, meta) in enumerate(zip(docs, metadatas)):
                chunk_id = meta.get("chunk_id", "") if meta else ""
                vector_chunks.append({
                    "text": doc,
                    "source": meta.get("source", "unknown") if meta else "unknown",
                    "page": meta.get("page", "?") if meta else "?",
                    "score": round(distances[i], 4) if i < len(distances) else None,
                    "source_type": "vector",
                })
                if chunk_id:
                    seen_chunk_ids.add(chunk_id)

        # 2. 图谱检索（如果可用）
        graph_chunks = []
        if self.graph_store:
            keywords = jieba.analyse.extract_tags(query, topK=10, withWeight=False)
            keywords = [w for w in keywords if w not in STOP_WORDS and len(w) > 1]
            if keywords:
                graph_results = self.graph_store.expand_context(
                    keywords, max_depth=settings.graph_max_depth
                )
                for r in graph_results:
                    cid = r.get("chunkId", "")
                    if cid and cid not in seen_chunk_ids:
                        graph_chunks.append({
                            "text": r["text"],
                            "source": r["source"],
                            "page": r["page"],
                            "score": None,
                            "source_type": "graph",
                        })
                        seen_chunk_ids.add(cid)

        # 3. 合并：向量结果在前，图谱扩展结果追加
        return vector_chunks + graph_chunks
