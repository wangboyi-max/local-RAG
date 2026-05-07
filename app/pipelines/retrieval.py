import jieba.analyse

from app.config import settings
from app.services.embeddings import get_embeddings
from app.services.vector_store import VectorStoreService
from app.services.graph_store import GraphStoreService, STOP_WORDS


def _chunk_key(meta: dict | None) -> str:
    """生成 chunk 的唯一标识，用于去重。优先用 chunk_id，回退到 source+page+chunk_index。"""
    if meta and meta.get("chunk_id"):
        return meta["chunk_id"]
    if meta and meta.get("source") and meta.get("page") is not None:
        ci = meta.get("chunk_index", 0)
        return f"{meta['source']}|{meta['page']}|{ci}"
    return ""


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
        """三路混合检索：BM25 关键词 + 向量语义 + 图谱扩展，合并去重后排序返回。"""
        k = top_k or settings.top_k

        seen_keys: set[str] = set()
        merged_results: list[dict] = []

        # 1. BM25 关键词检索（精确匹配，优先）
        bm25_chunks = self.vector_store.bm25_query(query, top_k=k)
        for chunk in bm25_chunks:
            key = _chunk_key({
                "chunk_id": chunk.get("chunk_id"),
                "source": chunk.get("source"),
                "page": chunk.get("page"),
                "chunk_index": chunk.get("chunk_index"),
            })
            if key:
                seen_keys.add(key)
            merged_results.append(chunk)

        # 2. 向量语义检索（语义理解）
        candidate_k = max(k, len(merged_results)) + k
        query_embedding = self.embeddings.embed_query(query)
        vector_results = self.vector_store.query(query_embedding, top_k=candidate_k)
        if vector_results.get("documents") and vector_results["documents"][0]:
            docs = vector_results["documents"][0]
            metadatas = vector_results.get("metadatas", [None] * len(docs))[0] or []
            distances = vector_results.get("distances", [[]])[0] or []
            for i, (doc, meta) in enumerate(zip(docs, metadatas)):
                key = _chunk_key(meta)
                if key and key in seen_keys:
                    continue
                merged_results.append({
                    "text": doc,
                    "source": meta.get("source", "unknown") if meta else "unknown",
                    "page": meta.get("page", "?") if meta else "?",
                    "chunk_id": meta.get("chunk_id", "") if meta else "",
                    "chunk_index": meta.get("chunk_index", 0) if meta else 0,
                    "score": round(1 - distances[i], 4) if i < len(distances) else None,
                    "source_type": "vector",
                })
                if key:
                    seen_keys.add(key)

        # 3. 图谱扩展补充（实体关系）
        if self.graph_store:
            keywords = jieba.analyse.extract_tags(query, topK=10, withWeight=False)
            keywords = [w for w in keywords if w not in STOP_WORDS and len(w) > 1]
            if keywords:
                graph_results = self.graph_store.expand_context(
                    keywords, max_depth=settings.graph_max_depth
                )
                for r in graph_results:
                    cid = r.get("chunkId", "")
                    if cid and cid not in seen_keys:
                        merged_results.append({
                            "text": r["text"],
                            "source": r["source"],
                            "page": r["page"],
                            "score": None,
                            "source_type": "graph",
                        })
                        seen_keys.add(cid)

        # 4. 排序：有分数的（向量）按相似度降序在前，无分数的（BM25/图谱）追加
        scored = [r for r in merged_results if r.get("score") is not None]
        unscored = [r for r in merged_results if r.get("score") is None]
        scored.sort(key=lambda x: x["score"], reverse=True)

        return (scored + unscored)[:k]
