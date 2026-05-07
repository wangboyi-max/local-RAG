import os
from sentence_transformers import SentenceTransformer


def get_model_path(model_name: str) -> str:
    """优先从 ModelScope 缓存加载，回退到 HuggingFace。"""
    ms_cache = os.path.expanduser("~/.cache/modelscope/hub/models")
    ms_path = os.path.join(ms_cache, model_name.replace("/", "/"))
    if os.path.exists(ms_path):
        return ms_path
    return model_name


def get_embeddings():
    model_path = get_model_path("BAAI/bge-m3")
    return SentenceTransformerEmbeddings(
        model_name=model_path,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


class SentenceTransformerEmbeddings:
    """轻量的嵌入包装，兼容 LangChain 接口。"""

    def __init__(self, model_name: str, model_kwargs: dict = None, encode_kwargs: dict = None):
        self.client = SentenceTransformer(model_name, **(model_kwargs or {}))
        self.encode_kwargs = encode_kwargs or {}

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.client.encode(texts, **self.encode_kwargs)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
