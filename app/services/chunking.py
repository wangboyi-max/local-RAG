from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config import settings


def get_paragraph_aware_text_splitter(
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> RecursiveCharacterTextSplitter:
    """段落感知文本切分器，优先在语义边界处断开。

    分隔符优先级（从高到低）：
    - \\n\\n\\n  → 章节/大段落边界
    - \\n\\n     → 段落边界
    - \\n        → OCR 行边界
    - 中文句号/叹号/问号、英文句点、分号、逗号
    """
    separators = [
        "\n\n\n",     # 章节/大段落边界
        "\n\n",       # 段落边界
        "\n",         # OCR 行边界
        "\u3002",     # 。
        "\uff01",     # ！
        "\uff1f",     # ？
        ". ",
        "\uff1b",     # ；
        "; ",
        "\uff0c",     # ，
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
