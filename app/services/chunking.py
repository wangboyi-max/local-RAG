from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config import settings


def get_chinese_text_splitter(
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> RecursiveCharacterTextSplitter:
    """返回支持中文标点感知的文本切分器。"""
    separators = [
        "\n\n",
        "\n",
        "\u3002",       # 。
        "\uff01",       # ！
        "\uff1f",       # ？
        ". ",
        "\uff1b",       # ；
        "; ",
        "\uff0c",       # ，
        ", ",
        " ",
        "",
    ]
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or settings.chunk_size,
        chunk_overlap=chunk_overlap or settings.chunk_overlap,
        separators=separators,
        length_function=len,
    )
