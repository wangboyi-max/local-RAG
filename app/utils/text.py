"""文本和任务处理工具：OCR 文本清理、检索格式化、任务格式化。"""
import re
from datetime import datetime, timezone


def clean_ocr_text(text: str) -> str:
    """清理 OCR 文本中的格式问题：合并连续空行、去除行首尾多余空格。"""
    lines = text.splitlines()
    cleaned = [line.strip() for line in lines]
    merged = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned))
    return merged.strip()


def format_chunks(chunks: list[dict]) -> str:
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
            f"{clean_ocr_text(c['text'])}\n"
        )
    return "\n".join(lines)


def format_note(note: dict) -> str:
    """格式化笔记为可读文本。"""
    tag_str = f"\n标签: {', '.join(note['tags'])}" if note.get("tags") else ""
    return (
        f"📝 **{note['title']}**\n"
        f"创建: {note['created_at'][:19]}\n"
        f"更新: {note['updated_at'][:19]}"
        f"{tag_str}\n"
        f"\n---\n{note['content']}"
    )


def format_task(task: dict) -> str:
    """格式化任务状态为可读文本。"""
    status_map = {
        "pending": "⏳ 等待中", "running": "🔄 执行中",
        "completed": "✅ 已完成", "failed": "❌ 失败",
    }
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
    lines.append(f"查询: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')}")
    return "\n".join(lines)
