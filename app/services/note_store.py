"""笔记服务：持久化笔记并自动同步到 RAG。"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.services.vector_store import VectorStoreService
from app.services.graph_store import GraphStoreService
from app.services.task_tracker import TaskTrackerService, TaskStatus
from app.services.chunking import get_chinese_text_splitter
from app.config import settings

NOTE_SOURCE = "__notes__"
MAX_CONTENT_LENGTH = 5000


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

    # ── CRUD ──────────────────────────────────────────────

    def create_note(self, title: str, content: str, tags: list[str] | None = None) -> str:
        """创建笔记，返回 task_id。后台同步到 RAG。"""
        if len(content) > self.NOTE_MAX_LEN:
            raise ValueError(f"笔记内容过长，最大 {self.NOTE_MAX_LEN} 字，当前 {len(content)} 字")

        note_id = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc).isoformat()
        note = {
            "id": note_id,
            "title": title,
            "content": content,
            "tags": tags or [],
            "created_at": now,
            "updated_at": now,
        }

        # 持久化笔记
        self._save_note(note)
        self._add_to_index(note)

        if not content.strip():
            return None  # 空内容不需要同步

        # 提交后台同步任务
        task_id = self.task_tracker.create_task(
            "note_sync", f"创建笔记：{title}"
        )
        self.task_tracker.run_background(task_id, lambda tid: self._sync_to_rag(note_id, content, tid))
        return task_id

    def get_note(self, note_id: str) -> dict | None:
        """读取单条笔记。"""
        note_path = self._note_path(note_id)
        if not note_path.exists():
            return None
        with open(note_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_notes(self, tag: str | None = None) -> list[dict]:
        """列出笔记，可选按标签过滤。"""
        index = self._load_index()
        notes = []
        for nid, meta in index.items():
            if tag and tag not in meta.get("tags", []):
                continue
            # 验证文件存在
            if self._note_path(nid).exists():
                notes.append({"id": nid, **meta})
        notes.sort(key=lambda n: n.get("updated_at", ""), reverse=True)
        return notes

    def update_note(
        self,
        note_id: str,
        title: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> str | None:
        """更新笔记。内容变动时返回 task_id（后台重新同步），否则返回 None。"""
        note_path = self._note_path(note_id)
        if not note_path.exists():
            raise ValueError(f"笔记不存在：{note_id}")

        with open(note_path, "r", encoding="utf-8") as f:
            note = json.load(f)

        content_changed = content is not None and content != note["content"]

        if content is not None:
            if len(content) > self.NOTE_MAX_LEN:
                raise ValueError(f"笔记内容过长，最大 {self.NOTE_MAX_LEN} 字，当前 {len(content)} 字")
            note["content"] = content
        if title is not None:
            note["title"] = title
        if tags is not None:
            note["tags"] = tags
        note["updated_at"] = datetime.now(timezone.utc).isoformat()

        self._save_note(note)
        self._add_to_index(note)

        if not content_changed:
            return None  # 仅改了标题/标签，无需重建 RAG

        # 先删旧 RAG 数据，再建新的
        task_id = self.task_tracker.create_task(
            "note_sync", f"更新笔记：{note['title']}"
        )
        self.task_tracker.run_background(task_id, lambda tid: self._reindex_rag(note_id, content, tid))
        return task_id

    def delete_note(self, note_id: str) -> bool:
        """删除笔记及其 RAG 数据。"""
        note_path = self._note_path(note_id)
        if not note_path.exists():
            return False

        # 删除 RAG 数据
        self._delete_from_rag(note_id)

        # 删除文件和 index
        note_path.unlink(missing_ok=True)
        self._remove_from_index(note_id)
        return True

    def search_notes(self, query: str, top_k: int = 5) -> list[dict]:
        """通过向量搜索笔记内容。"""
        from app.services.embeddings import get_embeddings

        emb = get_embeddings()
        query_embedding = emb.embed_documents([query])[0]
        results = self.vector_store.query(query_embedding, top_k=top_k * 2)

        # 过滤笔记来源，按 note_id 去重
        note_ids_seen = set()
        matched = []
        for i, (text, meta, dist) in enumerate(
            zip(
                results.get("documents", [[]])[0],
                results.get("metadatas", [[]])[0],
                results.get("distances", [[]])[0],
            )
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

    def _sync_to_rag(self, note_id: str, content: str, task_id: str):
        """将笔记内容同步到 RAG（向量 + 图谱）。"""
        chunks = self.chunker.split_text(content)
        if not chunks:
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
        self.task_tracker.update_task(task_id, progress=f"向量化 {total} 个文本块")
        self.vector_store.add_documents(chunks, metadatas, ids)

        if self.graph_store and chunks:
            self.task_tracker.update_task(task_id, progress=f"实体提取 1/{total}")
            self.graph_store.add_entities(chunks, metadatas)

        self.task_tracker.update_task(
            task_id, status=TaskStatus.COMPLETED,
            result=f"成功索引 {total} 个文本块",
            progress=f"同步完成 ({total}/{total} chunks)",
        )

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
        return self.notes_dir / f"{note_id}.json"

    def _save_note(self, note: dict):
        with open(self._note_path(note["id"]), "w", encoding="utf-8") as f:
            json.dump(note, f, ensure_ascii=False, indent=2)

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

    def _add_to_index(self, note: dict):
        index = self._load_index()
        index[note["id"]] = {
            "title": note["title"],
            "tags": note["tags"],
            "created_at": note["created_at"],
            "updated_at": note["updated_at"],
        }
        self._save_index(index)

    def _remove_from_index(self, note_id: str):
        index = self._load_index()
        index.pop(note_id, None)
        self._save_index(index)
