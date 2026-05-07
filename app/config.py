import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

# 外部数据目录：插件升级时不破坏数据
# 优先级: LOCAL_RAG_DATA_DIR 环境变量 > ~/.local/share/local-rag
_data_dir = os.environ.get("LOCAL_RAG_DATA_DIR")
if not _data_dir:
    _home = Path.home()
    _data_dir = str(_home / ".local" / "share" / "local-rag")

# 确保数据目录存在
Path(_data_dir).mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    # 数据目录根路径（通过 LOCAL_RAG_DATA_DIR 环境变量或 .env 设置）
    data_dir: str = Field(default=_data_dir, alias="LOCAL_RAG_DATA_DIR")

    # 嵌入模型
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"

    # ChromaDB
    chroma_db_path: str = str(Path(_data_dir) / "chroma_db")
    chroma_collection_name: str = "documents"

    # 文本切分
    chunk_size: int = 1500
    chunk_overlap: int = 200

    # 检索
    top_k: int = 4
    bm25_enabled: bool = True

    # OCR
    ocr_languages: str = "ch,en"
    ocr_dpi: int = 200

    # 文件存储
    upload_dir: str = str(Path(_data_dir) / "uploads")
    notes_dir: str = str(Path(_data_dir) / "notes")

    # Neo4j 知识图谱
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "ragpassword123"

    # 图谱实体提取
    graph_entity_extractor: str = "jieba"  # jieba 或 llm
    graph_max_entities: int = 10
    graph_max_depth: int = 2

    # LLM 实体提取
    llm_api_key: str = ""
    llm_api_base: str = "https://api.minimaxi.com/v1"
    llm_model: str = "MiniMax-M2.7"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "populate_by_name": True}


settings = Settings()
