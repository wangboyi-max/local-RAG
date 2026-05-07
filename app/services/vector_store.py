import chromadb
from chromadb.config import Settings as ChromaSettings
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

    def add_documents(self, texts: list[str], metadatas: list[dict], ids: list[str]):
        embeddings = self._embed_batch(texts)
        self.collection.add(
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )

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
        return len(ids)

    def delete_by_ids_prefix(self, prefix: str) -> int:
        """删除 ID 以 prefix 开头的所有文档，返回删除数量。"""
        all_ids = self.collection.get(include=[])["ids"]
        matching_ids = [id_ for id_ in all_ids if id_.startswith(prefix)]
        if matching_ids:
            self.collection.delete(ids=matching_ids)
        return len(matching_ids)

    def count(self) -> int:
        return self.collection.count()

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """内部使用嵌入服务批量生成向量。"""
        from app.services.embeddings import get_embeddings

        emb = get_embeddings()
        return emb.embed_documents(texts)
