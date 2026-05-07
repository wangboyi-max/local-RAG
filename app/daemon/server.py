"""Daemon HTTP 服务端：单例服务 + 写锁 + REST 端点。"""
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.config import settings

logger = logging.getLogger(__name__)

# 全局写锁，串行化所有突变操作
_write_lock = threading.Lock()


class DaemonServer:
    """Daemon HTTP 服务，初始化服务单例并启动 HTTPServer。"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.port = settings.daemon_port
        self.server = None
        self._init_services()

    def _init_services(self):
        """初始化所有服务单例。"""
        from app.services.ocr import OCRService
        from app.services.vector_store import VectorStoreService
        from app.services.graph_store import GraphStoreService
        from app.services.note_store import NoteStoreService
        from app.services.task_tracker import TaskTrackerService
        from app.pipelines.ingestion import IngestionPipeline
        from app.pipelines.retrieval import RetrievalPipeline

        ocr = OCRService()
        vector_store = VectorStoreService()
        graph_store = GraphStoreService()
        task_tracker = TaskTrackerService(state_file=f"{self.data_dir}/tasks.json")

        self.note_store = NoteStoreService(
            vector_store=vector_store,
            graph_store=graph_store,
            task_tracker=task_tracker,
            write_lock=_write_lock,
        )
        self.task_tracker = task_tracker
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.ingestion = IngestionPipeline(
            ocr=ocr, vector_store=vector_store, graph_store=graph_store
        )
        self.retrieval = RetrievalPipeline(
            vector_store=vector_store, graph_store=graph_store
        )
        logger.info("[daemon] 服务单例初始化完成")

    def start(self):
        # 注入服务实例到 handler class 属性
        _RequestHandler.note_store = self.note_store
        _RequestHandler.task_tracker = self.task_tracker
        _RequestHandler.ingestion = self.ingestion
        _RequestHandler.retrieval = self.retrieval
        _RequestHandler.graph_store = self.graph_store
        self.server = ThreadingHTTPServer(("", self.port), _RequestHandler)
        logger.info("[daemon] 启动于 http://localhost:%d", self.port)
        self.server.serve_forever()

    def shutdown(self):
        if self.server:
            self.server.shutdown()
            logger.info("[daemon] 已关闭")


class _RequestHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器，通过类属性注入服务实例。"""

    # 由 DaemonServer.start() 注入
    note_store = None
    task_tracker = None
    ingestion = None
    retrieval = None
    graph_store = None

    # ── HTTP 方法 ─────────────────────────────────────────

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length else {}

        routes = {
            "/api/shutdown": self._handle_shutdown,
            "/api/search_docs": lambda: self._handle_search_docs(**body),
            "/api/ingest_file": lambda: self._handle_ingest_file(**body),
            "/api/list_docs": self._handle_list_docs,
            "/api/delete_docs": lambda: self._handle_delete_docs(**body),
            "/api/graph_stats": self._handle_graph_stats,
            "/api/create_note": lambda: self._handle_create_note(**body),
            "/api/get_note": lambda: self._handle_get_note(**body),
            "/api/list_notes": lambda: self._handle_list_notes(**body),
            "/api/update_note": lambda: self._handle_update_note(**body),
            "/api/reindex_note": lambda: self._handle_reindex_note(**body),
            "/api/delete_note": lambda: self._handle_delete_note(**body),
            "/api/search_notes": lambda: self._handle_search_notes(**body),
            "/api/task_status": lambda: self._handle_task_status(**body),
        }

        handler = routes.get(self.path)
        if handler:
            try:
                result = handler()
                self._json(200, {"result": result})
            except Exception as e:
                logger.exception("[daemon] %s 执行异常", self.path)
                self._json(500, {"error": str(e)})
        else:
            self._json(404, {"error": f"not found: {self.path}"})

    def log_message(self, format, *args):
        """抑制默认日志输出。"""
        pass

    # ── 写操作（加锁）─────────────────────────────────────

    def _handle_ingest_file(self, file_path: str) -> str:
        import os
        if not os.path.isfile(file_path):
            return f"错误：文件不存在 - {file_path}"
        with _write_lock:
            result = self.ingestion.ingest(file_path)
        action_text = "重新索引（覆盖）" if result["action"] == "replaced" else "索引"
        return (
            f"成功{action_text}文件 `{result['source']}`\n"
            f"- 页数: {result['pages']}\n"
            f"- 文本块: {result['chunks']}"
        )

    def _handle_delete_docs(self, source: str) -> str:
        with _write_lock:
            count = self.retrieval.vector_store.delete_by_source(source)
            if self.graph_store:
                self.graph_store.delete_by_source(source)
        if count > 0:
            return f"已删除 `{source}`，共移除 {count} 个文本块。"
        return f"未找到名为 `{source}` 的文档。"

    def _handle_create_note(self, title: str, content: str, tags: str | None = None) -> str:
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        with _write_lock:
            task_id = self.note_store.create_note(title, content, tag_list)
        if task_id is None:
            return f"笔记「{title}」已创建（空内容，未同步到 RAG）"
        return f"笔记「{title}」已创建，正在同步到 RAG。\n任务 ID: `{task_id}`\n请用 `task_status` 查询同步进度。"

    def _handle_update_note(self, title: str, content: str | None = None, tags: str | None = None, new_title: str | None = None) -> str:
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        with _write_lock:
            task_id = self.note_store.update_note(title, content=content, tags=tag_list, new_title=new_title)
        if task_id is None:
            return f"笔记 `{title}` 已更新（仅标题/标签，无需重建 RAG）"
        return f"笔记 `{title}` 内容已更新，正在重新同步到 RAG。\n任务 ID: `{task_id}`\n请用 `task_status` 查询同步进度。"

    def _handle_reindex_note(self, title: str) -> str:
        with _write_lock:
            ok = self.note_store.reindex_from_file(title)
        if ok:
            return f"笔记 `{title}` 已重新索引到 RAG。"
        return f"笔记 `{title}` 重新索引失败（文件可能不存在或内容为空）。"

    def _handle_delete_note(self, title: str) -> str:
        with _write_lock:
            deleted = self.note_store.delete_note(title)
        if deleted:
            return f"笔记 `{title}` 及其 RAG 数据已删除。"
        return f"未找到笔记：{title}"

    def _handle_shutdown(self) -> str:
        threading.Thread(target=self._shutdown_daemon).start()
        return "daemon 正在关闭..."

    # ── 读操作（无锁）─────────────────────────────────────

    def _handle_search_docs(self, query: str, top_k: int = 4) -> str:
        chunks = self.retrieval.search(query, top_k=top_k)
        if not chunks:
            return "未在知识库中找到相关内容。"
        return _format_chunks(chunks)

    def _handle_list_docs(self) -> str:
        sources = self.retrieval.vector_store.get_unique_sources()
        if not sources:
            return "知识库为空，没有已索引的文档。"
        lines = ["已索引文档列表：\n"]
        for source in sources:
            info = self.retrieval.vector_store.get_document_info(source)
            pages_count = len(info.get("pages", [])) if isinstance(info.get("pages"), list) else info.get("page_count", 0)
            lines.append(f"- `{source}`: {info['chunk_count']} 个文本块, 共 {pages_count} 页")
        return "\n".join(lines)

    def _handle_graph_stats(self) -> str:
        if self.graph_store:
            stats = self.graph_store.get_stats()
            return (
                f"知识图谱统计：\n"
                f"- 文本块节点: {stats['chunk_nodes']}\n"
                f"- 实体节点: {stats['entity_nodes']}\n"
                f"- 关系边: {stats['relationships']}"
            )
        return "知识图谱未启用。"

    def _handle_get_note(self, title: str) -> str:
        note = self.note_store.get_note(title)
        if not note:
            return f"未找到笔记：{title}"
        return _format_note(note)

    def _handle_list_notes(self, tag: str | None = None) -> str:
        notes = self.note_store.list_notes(tag=tag)
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

    def _handle_search_notes(self, query: str, top_k: int = 5) -> str:
        results = self.note_store.search_notes(query, top_k=top_k)
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

    def _handle_task_status(self, task_id: str | None = None) -> str:
        if task_id:
            task = self.task_tracker.get_task(task_id)
            if not task:
                return f"未找到任务：{task_id}"
            return _format_task(task)
        tasks = self.task_tracker.list_tasks()
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

    # ── 内部方法 ──────────────────────────────────────────

    def _json(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _shutdown_daemon(self):
        self._shutdown_signal()


def _format_chunks(chunks: list[dict]) -> str:
    """格式化检索结果为可读文本。"""
    import re
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
        text = _clean_ocr_text(c["text"])
        lines.append(f"--- [{i}] {tag} {c['source']} (第{c['page']}页){score_str}\n{text}\n")
    return "\n".join(lines)


def _clean_ocr_text(text: str) -> str:
    import re
    lines = text.splitlines()
    cleaned = [line.strip() for line in lines]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()


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
