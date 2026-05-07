"""笔记服务：笔记以纯 .md 文件存储，无 frontmatter，元数据统一存 index.json。
文件名即标题，改标题 = 重命名文件 + 更新 RAG 索引。
"""
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from app.services.vector_store import VectorStoreService
from app.services.graph_store import GraphStoreService
from app.services.task_tracker import TaskTrackerService, TaskStatus
from app.services.chunking import get_chinese_text_splitter
from app.config import settings

logger = logging.getLogger(__name__)

NOTE_SOURCE = "__notes__"
MAX_CONTENT_LENGTH = 5000


def _sanitize_filename(title: str) -> str:
    """将标题转为安全的文件名，保留中文/英文/数字。"""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '-', title)
    name = re.sub(r'\s+', ' ', name).strip()
    if len(name) > 100:
        name = name[:100].rstrip()
    return name or "untitled"


class NoteStoreService:
    NOTE_MAX_LEN = MAX_CONTENT_LENGTH

    def __init__(
        self,
        vector_store: VectorStoreService,
        graph_store: GraphStoreService | None = None,
        task_tracker: TaskTrackerService | None = None,
    ):
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.task_tracker = task_tracker
        self.notes_dir = Path(settings.notes_dir)
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.notes_dir / "index.json"
        self.chunker = get_chinese_text_splitter()

    def _find_by_title(self, title: str) -> str | None:
        """按标题查找文件名（index.json 中的 note_id）。"""
        for nid, meta in self._load_index().items():
            if meta.get("title") == title:
                return nid
        return None

    def _resolve_id(self, title: str) -> str | None:
        """按标题或文件名定位笔记。"""
        # 直接按文件名查找
        if self._note_path(title).exists():
            return title
        # 按 index 中的 title 查找
        found = self._find_by_title(title)
        if found:
            return found
        return None

    # ── CRUD ──────────────────────────────────────────────

    def create_note(self, title: str, content: str, tags: list[str] | None = None) -> str:
        """创建笔记，返回 task_id。后台同步到 RAG。"""
        if len(content) > self.NOTE_MAX_LEN:
            raise ValueError(f"笔记内容过长，最大 {self.NOTE_MAX_LEN} 字，当前 {len(content)} 字")

        safe_name = _sanitize_filename(title)
        # 重名处理：追加序号
        file_path = self._note_path(safe_name)
        name = safe_name
        counter = 2
        while file_path.exists():
            name = f"{safe_name}_{counter}"
            file_path = self._note_path(name)
            counter += 1

        now = datetime.now(timezone.utc).isoformat()
        self._save_note_file(file_path, content)
        self._add_to_index(name, title, tags or [], now, now)

        if not content.strip():
            return None

        task_id = self.task_tracker.create_task("note_sync", f"创建笔记：{title}")
        self.task_tracker.run_background(task_id, lambda tid: self._sync_to_rag(name, content, tid))
        return task_id

    def get_note(self, title: str) -> dict | None:
        """按标题或文件名读取单条笔记。"""
        actual_id = self._resolve_id(title)
        if actual_id is None:
            return None
        note_path = self._note_path(actual_id)
        if not note_path.exists():
            return None
        content = note_path.read_text(encoding="utf-8")
        meta = self._load_index().get(actual_id, {})
        return {
            "id": actual_id,
            "title": meta.get("title", actual_id),
            "content": content,
            "tags": meta.get("tags", []),
            "created_at": meta.get("created_at", ""),
            "updated_at": meta.get("updated_at", ""),
        }

    def list_notes(self, tag: str | None = None) -> list[dict]:
        """列出笔记，可选按标签过滤。"""
        index = self._load_index()
        notes = []
        for nid, meta in index.items():
            if tag and tag not in meta.get("tags", []):
                continue
            if self._note_path(nid).exists():
                notes.append({"id": nid, **meta})
        notes.sort(key=lambda n: n.get("updated_at", ""), reverse=True)
        return notes

    def update_note(
        self,
        title: str,
        content: str | None = None,
        tags: list[str] | None = None,
        new_title: str | None = None,
    ) -> str | None:
        """更新笔记。按标题定位，可更新内容、标签或改名。"""
        actual_id = self._resolve_id(title)
        if actual_id is None:
            raise ValueError(f"笔记不存在：{title}")

        index = self._load_index()
        meta = index.get(actual_id, {})
        cur_title = meta.get("title", actual_id)
        new_tags = tags if tags is not None else meta.get("tags", [])
        now = datetime.now(timezone.utc).isoformat()

        # 先读取旧内容（重命名前）
        note_path = self._note_path(actual_id)
        old_content = note_path.read_text(encoding="utf-8")

        # 改标题 → 重命名文件
        if new_title is not None and new_title != cur_title:
            new_name = _sanitize_filename(new_title)
            if new_name != actual_id:
                new_path = self._note_path(new_name)
                if new_path.exists():
                    raise ValueError(f"目标文件名已存在：{new_name}")

                # 重命名文件
                note_path.rename(new_path)
                actual_id = new_name
                note_path = new_path

                # 迁移 RAG：删旧数据 → 用新 note_id 重建（用旧内容）
                content_to_index = content if content is not None else old_content
                if content_to_index.strip():
                    self._delete_from_rag(actual_id)
                    self._sync_to_rag(new_name, content_to_index, task_id=None)

                cur_title = new_title

        # 判断内容是否变化
        content_changed = content is not None and content != old_content

        # 更新 index
        self._add_to_index(actual_id, cur_title, new_tags, meta.get("created_at", now), now)

        # 改内容
        if content is not None:
            if len(content) > self.NOTE_MAX_LEN:
                raise ValueError(f"笔记内容过长，最大 {self.NOTE_MAX_LEN} 字，当前 {len(content)} 字")
            self._save_note_file(note_path, content)

        if not content_changed:
            return None

        task_id = self.task_tracker.create_task("note_sync", f"更新笔记：{cur_title}")
        self.task_tracker.run_background(task_id, lambda tid: self._reindex_rag(actual_id, content, tid))
        return task_id

    def delete_note(self, title: str) -> bool:
        """按标题删除笔记及其 RAG 数据。"""
        actual_id = self._resolve_id(title)
        if actual_id is None:
            return False

        self._delete_from_rag(actual_id)
        self._note_path(actual_id).unlink(missing_ok=True)
        self._remove_from_index(actual_id)
        return True

    def search_notes(self, query: str, top_k: int = 5) -> list[dict]:
        """通过向量搜索笔记内容。"""
        from app.services.embeddings import get_embeddings

        emb = get_embeddings()
        query_embedding = emb.embed_documents([query])[0]
        results = self.vector_store.query(query_embedding, top_k=top_k * 2)

        note_ids_seen = set()
        matched = []
        for text, meta, dist in zip(
            results.get("documents", [[]])[0],
            results.get("metadatas", [[]])[0],
            results.get("distances", [[]])[0],
        ):
            if meta.get("source") != NOTE_SOURCE:
                continue
            nid = meta.get("note_id")
            if nid in note_ids_seen:
                continue
            note_ids_seen.add(nid)
            note = self.get_note(nid)
            if note:
                matched.append({
                    "note": note,
                    "score": round(1 - dist, 3),
                    "matched_chunk": text[:200],
                })
            if len(matched) >= top_k:
                break

        return matched

    # ── RAG Sync ──────────────────────────────────────────

    def _sync_to_rag(self, note_id: str, content: str, task_id: str | None):
        """将笔记内容同步到 RAG（向量 + 图谱）。"""
        chunks = self.chunker.split_text(content)
        if not chunks:
            if task_id:
                self.task_tracker.update_task(
                    task_id, status=TaskStatus.COMPLETED,
                    result="笔记内容为空，未索引到 RAG",
                    progress="0 chunks",
                )
            return

        now = datetime.now(timezone.utc).isoformat()
        metadatas = [
            {
                "source": NOTE_SOURCE,
                "note_id": note_id,
                "page": 1,
                "chunk_index": i,
                "ingested_at": now,
            }
            for i in range(len(chunks))
        ]
        ids = [f"{NOTE_SOURCE}-{note_id}-{i}" for i in range(len(chunks))]

        total = len(chunks)
        if task_id:
            self.task_tracker.update_task(task_id, progress=f"向量化 {total} 个文本块")
        self.vector_store.add_documents(chunks, metadatas, ids)

        if self.graph_store and chunks:
            if task_id:
                self.task_tracker.update_task(task_id, progress=f"实体提取 1/{total}")
            self.graph_store.add_entities(chunks, metadatas)

        if task_id:
            self.task_tracker.update_task(
                task_id, status=TaskStatus.COMPLETED,
                result=f"成功索引 {total} 个文本块",
                progress=f"同步完成 ({total}/{total} chunks)",
            )

    def reindex_from_file(self, title: str) -> bool:
        """外部触发重建：按 title 定位 .md 文件，读取内容后重建 RAG。"""
        actual_id = self._resolve_id(title)
        if actual_id is None:
            logger.warning(f"[NoteStore] 笔记不存在：{title}")
            return False

        note_path = self._note_path(actual_id)
        if not note_path.exists():
            logger.warning(f"[NoteStore] 笔记文件不存在：{note_path}")
            return False

        try:
            content = note_path.read_text(encoding="utf-8")
            if not content.strip():
                logger.info(f"[NoteStore] 笔记 {actual_id} 内容为空，跳过重建")
                return True
            self._reindex_rag(actual_id, content, task_id=None)
            return True
        except Exception:
            logger.exception(f"[NoteStore] 重建笔记 {actual_id} 失败")
            return False

    def _reindex_rag(self, note_id: str, content: str, task_id: str):
        """先删除旧 RAG 数据，再重新索引。"""
        self._delete_from_rag(note_id)
        self._sync_to_rag(note_id, content, task_id)

    def _delete_from_rag(self, note_id: str):
        """删除笔记的所有 RAG 数据。"""
        prefix = f"{NOTE_SOURCE}-{note_id}"
        self.vector_store.delete_by_ids_prefix(prefix)
        if self.graph_store:
            self.graph_store.delete_by_note_id(note_id)

    # ── File I/O ──────────────────────────────────────────

    def _note_path(self, note_id: str) -> Path:
        return self.notes_dir / f"{note_id}.md"

    @staticmethod
    def _save_note_file(path: Path, content: str):
        """保存纯 Markdown 文件，无 frontmatter。"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _add_to_index(self, note_id: str, title: str, tags: list[str], created_at: str, updated_at: str):
        index = self._load_index()
        index[note_id] = {
            "title": title,
            "tags": tags,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        self._save_index(index)

    def _load_index(self) -> dict:
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_index(self, index: dict):
        tmp = self.index_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        tmp.replace(self.index_file)

    def _remove_from_index(self, note_id: str):
        index = self._load_index()
        index.pop(note_id, None)
        self._save_index(index)
