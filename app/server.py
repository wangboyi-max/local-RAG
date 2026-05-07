import os
import re

from mcp.server.fastmcp import FastMCP

from app.services.ocr import OCRService
from app.services.vector_store import VectorStoreService
from app.services.graph_store import GraphStoreService
from app.services.note_store import NoteStoreService, NOTE_SOURCE
from app.services.task_tracker import TaskTrackerService, TaskStatus
from app.pipelines.ingestion import IngestionPipeline
from app.pipelines.retrieval import RetrievalPipeline

mcp = FastMCP(
    "Graph RAG",
    instructions="本地 Graph RAG 检索服务，支持 OCR 处理扫描版 PDF/图片，结合 Neo4j 知识图谱和向量混合检索。",
)


# 全局单例，避免懒加载多次创建
_note_store = None
_task_tracker = None


def _get_task_tracker() -> TaskTrackerService:
    global _task_tracker
    if _task_tracker is None:
        _task_tracker = TaskTrackerService()
    return _task_tracker


def _get_note_store() -> NoteStoreService:
    global _note_store, _task_tracker
    if _note_store is None:
        vector_store = VectorStoreService()
        graph_store = GraphStoreService()
        _task_tracker = _task_tracker or TaskTrackerService()
        _note_store = NoteStoreService(
            vector_store=vector_store,
            graph_store=graph_store,
            task_tracker=_task_tracker,
        )
    return _note_store


def _get_pipelines():
    """懒加载管线实例，避免启动时加载所有重型模型。"""
    ocr = OCRService()
    vector_store = VectorStoreService()
    graph_store = GraphStoreService()
    ingestion = IngestionPipeline(ocr=ocr, vector_store=vector_store, graph_store=graph_store)
    retrieval = RetrievalPipeline(vector_store=vector_store, graph_store=graph_store)
    return ingestion, retrieval


@mcp.tool()
def search_docs(query: str, top_k: int = 4) -> str:
    """混合检索知识库（向量语义 + 知识图谱实体扩展），返回相关文本块及来源。"""
    _, retrieval = _get_pipelines()
    chunks = retrieval.search(query, top_k=top_k)
    if not chunks:
        return "未在知识库中找到相关内容。"
    return _format_chunks(chunks)


@mcp.tool()
def ingest_file(file_path: str) -> str:
    """将指定的 PDF 或图片文件索引到知识库中（含图谱构建）。file_path 为本地文件的绝对路径。"""
    if not os.path.isfile(file_path):
        return f"错误：文件不存在 - {file_path}"

    ingestion, _ = _get_pipelines()
    try:
        result = ingestion.ingest(file_path)
        action_text = "重新索引（覆盖）" if result["action"] == "replaced" else "索引"
        return (
            f"成功{action_text}文件 `{result['source']}`\n"
            f"- 页数: {result['pages']}\n"
            f"- 文本块: {result['chunks']}"
        )
    except ValueError as e:
        return f"错误：{e}"
    except Exception as e:
        return f"索引失败：{e}"


@mcp.tool()
def list_docs() -> str:
    """列出知识库中所有已索引的文档及其统计信息。"""
    _, retrieval = _get_pipelines()
    sources = retrieval.vector_store.get_unique_sources()
    if not sources:
        return "知识库为空，没有已索引的文档。"

    lines = ["已索引文档列表：\n"]
    for source in sources:
        info = retrieval.vector_store.get_document_info(source)
        lines.append(
            f"- `{source}`: {info['chunk_count']} 个文本块, "
            f"共 {len(info['pages'])} 页"
        )
    return "\n".join(lines)


@mcp.tool()
def delete_docs(source: str) -> str:
    """从知识库中删除指定文档及其所有索引数据（含图谱节点）。source 为文件名。"""
    _, retrieval = _get_pipelines()
    count = retrieval.vector_store.delete_by_source(source)
    if retrieval.graph_store:
        retrieval.graph_store.delete_by_source(source)
    if count > 0:
        return f"已删除 `{source}`，共移除 {count} 个文本块。"
    return f"未找到名为 `{source}` 的文档。"


@mcp.tool()
def graph_stats() -> str:
    """返回知识图谱的统计信息（节点数、关系数）。"""
    _, retrieval = _get_pipelines()
    if retrieval.graph_store:
        stats = retrieval.graph_store.get_stats()
        return (
            f"知识图谱统计：\n"
            f"- 文本块节点: {stats['chunk_nodes']}\n"
            f"- 实体节点: {stats['entity_nodes']}\n"
            f"- 关系边: {stats['relationships']}"
        )
    return "知识图谱未启用。"


# ── 笔记工具 ──────────────────────────────────────────────

@mcp.tool()
def create_note(title: str, content: str, tags: str | None = None) -> str:
    """创建 Markdown 笔记并异步同步到 RAG。tags 为逗号分隔的标签。返回 task_id，用 task_status 查询进度。"""
    try:
        note_store = _get_note_store()
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        task_id = note_store.create_note(title, content, tag_list)
        if task_id is None:
            return f"笔记「{title}」已创建（空内容，未同步到 RAG）"
        return f"笔记「{title}」已创建，正在同步到 RAG。\n任务 ID: `{task_id}`\n请用 `task_status` 查询同步进度。"
    except ValueError as e:
        return f"创建失败：{e}"
    except Exception as e:
        return f"创建失败：{e}"


@mcp.tool()
def get_note(title: str) -> str:
    """获取指定笔记的完整内容。title 为笔记文件名（标题）。"""
    note_store = _get_note_store()
    note = note_store.get_note(title)
    if not note:
        return f"未找到笔记：{title}"
    return _format_note(note)


@mcp.tool()
def list_notes(tag: str | None = None) -> str:
    """列出所有笔记，可选按标签过滤。"""
    note_store = _get_note_store()
    notes = note_store.list_notes(tag=tag)
    if not notes:
        filter_text = f"（标签: {tag}）" if tag else ""
        return f"没有找到笔记{filter_text}。"

    lines = ["笔记列表：\n"]
    for n in notes:
        tag_str = f" [{', '.join(n['tags'])}]" if n.get("tags") else ""
        lines.append(
            f"- **{n['title']}**{tag_str}\n"
            f"  更新于: {n['updated_at'][:19]}"
        )
    return "\n".join(lines)


@mcp.tool()
def update_note(title: str, content: str | None = None, tags: str | None = None, new_title: str | None = None) -> str:
    """更新笔记。按标题定位，可更新内容、标签或重命名。内容变动会异步重建 RAG。"""
    try:
        note_store = _get_note_store()
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        task_id = note_store.update_note(title, content=content, tags=tag_list, new_title=new_title)
        if task_id is None:
            return f"笔记 `{title}` 已更新（仅标题/标签，无需重建 RAG）"
        return f"笔记 `{title}` 内容已更新，正在重新同步到 RAG。\n任务 ID: `{task_id}`\n请用 `task_status` 查询同步进度。"
    except ValueError as e:
        return f"更新失败：{e}"
    except Exception as e:
        return f"更新失败：{e}"


@mcp.tool()
def reindex_note(title: str) -> str:
    """重新索引指定笔记到 RAG（手动触发）。按标题定位，适用于外部编辑 .md 文件后重建索引。"""
    try:
        note_store = _get_note_store()
        ok = note_store.reindex_from_file(title)
        if ok:
            return f"笔记 `{title}` 已重新索引到 RAG。"
        return f"笔记 `{title}` 重新索引失败（文件可能不存在或内容为空）。"
    except Exception as e:
        return f"重新索引失败：{e}"


@mcp.tool()
def delete_note(title: str) -> str:
    """删除笔记及其所有 RAG 索引数据。按标题定位。"""
    note_store = _get_note_store()
    if note_store.delete_note(title):
        return f"笔记 `{title}` 及其 RAG 数据已删除。"
    return f"未找到笔记：{title}"


@mcp.tool()
def search_notes(query: str, top_k: int = 5) -> str:
    """在笔记内容中搜索相关笔记（向量语义检索）。"""
    note_store = _get_note_store()
    results = note_store.search_notes(query, top_k=top_k)
    if not results:
        return "未在笔记中找到相关内容。"

    lines = [f"找到 {len(results)} 篇相关笔记：\n"]
    for i, r in enumerate(results, 1):
        note = r["note"]
        tag_str = f" [{', '.join(note['tags'])}]" if note.get("tags") else ""
        lines.append(
            f"--- [{i}] `{note['id']}` **{note['title']}**{tag_str} [相关度: {r['score']}]\n"
            f"匹配片段: {r['matched_chunk']}\n"
        )
    return "\n".join(lines)


# ── 任务状态工具 ──────────────────────────────────────────

@mcp.tool()
def task_status(task_id: str | None = None) -> str:
    """查询异步任务状态。不传 task_id 返回所有任务列表。"""
    tracker = _get_task_tracker()

    if task_id:
        task = tracker.get_task(task_id)
        if not task:
            return f"未找到任务：{task_id}"
        return _format_task(task)

    tasks = tracker.list_tasks()
    if not tasks:
        return "没有任务记录。"

    lines = ["任务列表：\n"]
    for t in tasks:
        status_icon = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}.get(t["status"], "")
        progress = f" — {t['progress']}" if t.get("progress") else ""
        result = f" → {t['result']}" if t.get("result") else ""
        error = f" → 错误: {t['error']}" if t.get("error") else ""
        lines.append(
            f"- `{t['task_id']}` {status_icon} {t['title']}\n"
            f"  状态: {t['status']}{progress}{result}{error}\n"
            f"  创建: {t['created_at'][:19]}"
        )
    return "\n".join(lines)


def _format_chunks(chunks: list[dict]) -> str:
    """格式化检索结果为可读文本。"""
    source_types = {"vector": "向量", "bm25": "关键词", "graph": "图谱"}
    type_counts = {}
    for c in chunks:
        st = c.get("source_type", "vector")
        type_counts[st] = type_counts.get(st, 0) + 1
    summary_parts = [f"{source_types.get(st, st)} {n} 条" for st, n in type_counts.items()]
    lines = [f"找到 {len(chunks)} 个相关结果（{', '.join(summary_parts)}）：\n"]
    for i, c in enumerate(chunks, 1):
        st = c.get("source_type", "vector")
        tag = f"[{source_types.get(st, st)}]"
        score_str = f"[相关度: {c['score']}]" if c.get("score") is not None else ""
        lines.append(
            f"--- [{i}] {tag} {c['source']} (第{c['page']}页){score_str}\n"
            f"{_clean_ocr_text(c['text'])}\n"
        )
    return "\n".join(lines)


def _clean_ocr_text(text: str) -> str:
    """清理 OCR 文本中的格式问题：合并连续空行、去除行首尾多余空格。"""
    lines = text.splitlines()
    cleaned = [line.strip() for line in lines]
    merged = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned))
    return merged.strip()


def _format_note(note: dict) -> str:
    tag_str = f"\n标签: {', '.join(note['tags'])}" if note.get("tags") else ""
    return (
        f"📝 **{note['title']}**\n"
        f"创建: {note['created_at'][:19]}\n"
        f"更新: {note['updated_at'][:19]}"
        f"{tag_str}\n"
        f"\n---\n{note['content']}"
    )


def _format_task(task: dict) -> str:
    status_map = {"pending": "⏳ 等待中", "running": "🔄 执行中", "completed": "✅ 已完成", "failed": "❌ 失败"}
    icon = status_map.get(task["status"], task["status"])
    lines = [f"任务 ID: `{task['task_id']}`"]
    lines.append(f"类型: {task['type']} — {icon}")
    lines.append(f"标题: {task['title']}")
    if task.get("progress"):
        lines.append(f"进度: {task['progress']}")
    if task.get("result"):
        lines.append(f"结果: {task['result']}")
    if task.get("error"):
        lines.append(f"错误: {task['error']}")
    lines.append(f"创建: {task['created_at'][:19]}")
    lines.append(f"更新: {task['updated_at'][:19]}")
    return "\n".join(lines)
