import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever

from app.config import settings


class VectorStoreService:
    def __init__(self, db_path: str | None = None, collection_name: str | None = None):
        self.db_path = db_path or settings.chroma_db_path
        self.collection_name = collection_name or settings.chroma_collection_name
        self.client = chromadb.PersistentClient(
            path=self.db_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        # BM25 关键词检索缓存
        self._bm25_retriever: BM25Retriever | None = None
        self._bm25_docs_cache: list[Document] = []
        self._bm25_cache_version: int = -1

    def add_documents(self, texts: list[str], metadatas: list[dict], ids: list[str]):
        embeddings = self._embed_batch(texts)
        self.collection.add(
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )
        self._invalidate_bm25_cache()

    def query(self, query_embedding: list[float], top_k: int = 4) -> dict:
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )

    def get_unique_sources(self) -> list[str]:
        """获取所有已索引文档的唯一来源列表。"""
        results = self.collection.get(include=["metadatas"])
        seen = set()
        sources = []
        for meta in results.get("metadatas", []) or []:
            if meta and "source" in meta:
                src = meta["source"]
                if src not in seen:
                    seen.add(src)
                    sources.append(src)
        return sources

    def get_document_info(self, source: str) -> dict:
        """获取指定文档的索引信息。"""
        results = self.collection.get(where={"source": source}, include=["metadatas"])
        chunk_count = len(results.get("ids", []))
        pages = set()
        for meta in results.get("metadatas", []) or []:
            if meta and "page" in meta:
                pages.add(meta["page"])
        return {"source": source, "chunk_count": chunk_count, "pages": sorted(pages)}

    def delete_by_source(self, source: str) -> int:
        """删除指定来源的所有文档，返回删除数量。"""
        results = self.collection.get(where={"source": source})
        ids = results.get("ids", [])
        if ids:
            self.collection.delete(ids=ids)
        self._invalidate_bm25_cache()
        return len(ids)

    def delete_by_ids_prefix(self, prefix: str) -> int:
        """删除 ID 以 prefix 开头的所有文档，返回删除数量。"""
        all_ids = self.collection.get(include=[])["ids"]
        matching_ids = [id_ for id_ in all_ids if id_.startswith(prefix)]
        if matching_ids:
            self.collection.delete(ids=matching_ids)
        self._invalidate_bm25_cache()
        return len(matching_ids)

    def clear_all(self):
        """清空整个向量数据库（删除并重建 collection）。"""
        self.client.delete_collection(name=self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._invalidate_bm25_cache()

    def count(self) -> int:
        return self.collection.count()

    def bm25_query(self, query: str, top_k: int = 4) -> list[dict]:
        """BM25 关键词检索，返回与 vector query 同格式的 dict 列表。"""
        if not settings.bm25_enabled:
            return []
        retriever = self._build_bm25_retriever()
        if retriever is None:
            return []
        docs = retriever.invoke(query, config={"k": top_k * 2})
        return [
            {
                "text": d.page_content,
                "source": d.metadata.get("source", "unknown"),
                "page": d.metadata.get("page", "?"),
                "chunk_id": d.metadata.get("chunk_id", ""),
                "chunk_index": d.metadata.get("chunk_index", 0),
                "score": None,
                "source_type": "bm25",
            }
            for d in docs
        ]

    def _build_bm25_retriever(self) -> BM25Retriever | None:
        """从 ChromaDB 文档构建 BM25 retriever，带懒加载缓存。"""
        if not settings.bm25_enabled:
            return None
        current_count = self.collection.count()
        if (
            self._bm25_retriever is not None
            and self._bm25_cache_version == current_count
        ):
            return self._bm25_retriever
        if current_count == 0:
            return None
        all_data = self.collection.get(include=["documents", "metadatas"])
        self._bm25_docs_cache = [
            Document(page_content=doc, metadata=meta)
            for doc, meta in zip(all_data["documents"], all_data["metadatas"])
        ]
        self._bm25_retriever = BM25Retriever.from_documents(self._bm25_docs_cache)
        self._bm25_cache_version = current_count
        return self._bm25_retriever

    def _invalidate_bm25_cache(self) -> None:
        """标记 BM25 缓存失效，下次查询时重建。"""
        self._bm25_retriever = None
        self._bm25_docs_cache = []
        self._bm25_cache_version = -1

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """内部使用嵌入服务批量生成向量。"""
        from app.services.embeddings import get_embeddings

        emb = get_embeddings()
        return emb.embed_documents(texts)
