"""配置管理：默认在当前工作目录下 .knowledge-hub/，自动创建 notes/ 和 rag/ 子目录。"""
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 工作路径：默认当前工作目录下的 .knowledge-hub/
    # 环境变量: LOCAL_RAG_WORK_DIR（.env 中设置即可）
    work_dir: str = ""

    # 嵌入模型
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"

    # ChromaDB
    chroma_db_path: str = ""
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

    # 文件存储（子目录）
    upload_dir: str = ""
    notes_dir: str = ""

    # Neo4j 知识图谱
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "ragpassword123"

    # 图谱实体提取
    graph_entity_extractor: str = "jieba"  # jieba 或 llm
    graph_max_entities: int = 10
    graph_max_depth: int = 2

    # Daemon 端口（内部 HTTP 服务）
    daemon_port: int = 27890

    # LLM 实体提取
    llm_api_key: str = ""
    llm_api_base: str = "https://api.minimaxi.com/v1"
    llm_model: str = "MiniMax-M2.7"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )

    def model_post_init(self, __context) -> None:
        # 默认使用当前工作目录下的 .knowledge-hub/
        if not self.work_dir:
            self.work_dir = str(Path.cwd() / ".knowledge-hub")

        self.work_dir = str(Path(self.work_dir).expanduser().resolve())
        Path(self.work_dir).mkdir(parents=True, exist_ok=True)

        # 子目录：rag/ 存 RAG 数据，notes/ 存 Markdown 笔记
        if not self.chroma_db_path:
            self.chroma_db_path = str(Path(self.work_dir) / "rag" / "chroma_db")
        if not self.upload_dir:
            self.upload_dir = str(Path(self.work_dir) / "rag" / "uploads")
        if not self.notes_dir:
            self.notes_dir = str(Path(self.work_dir) / "notes")

        # 确保子目录存在
        for p in [self.chroma_db_path, self.upload_dir, self.notes_dir]:
            Path(p).mkdir(parents=True, exist_ok=True)


settings = Settings()
