"""异步任务跟踪服务，持久化任务状态到磁盘，支持后台执行。"""
import json
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


from app.config import settings


class TaskTrackerService:
    def __init__(self, state_file: str | None = None):
        self.state_file = Path(state_file or f"{settings.data_dir}/tasks.json")
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.tasks: dict[str, dict] = {}
        self.lock = threading.Lock()
        self._load()

    def create_task(self, task_type: str, title: str) -> str:
        """创建任务，返回 task_id。"""
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        with self.lock:
            self.tasks[task_id] = {
                "type": task_type,
                "title": title,
                "status": TaskStatus.PENDING.value,
                "progress": None,
                "result": None,
                "error": None,
                "created_at": now,
                "updated_at": now,
            }
            self._save()
        return task_id

    def update_task(
        self,
        task_id: str,
        status: TaskStatus | None = None,
        result: str | None = None,
        error: str | None = None,
        progress: str | None = None,
    ):
        """更新任务状态，自动持久化。"""
        with self.lock:
            if task_id not in self.tasks:
                return
            task = self.tasks[task_id]
            if status is not None:
                task["status"] = status.value if isinstance(status, TaskStatus) else status
            if result is not None:
                task["result"] = result
            if error is not None:
                task["error"] = error
            if progress is not None:
                task["progress"] = progress
            task["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save()

    def get_task(self, task_id: str) -> dict | None:
        """查询单个任务状态。"""
        with self.lock:
            task = self.tasks.get(task_id)
            if task:
                return {"task_id": task_id, **dict(task)}
            return None

    def list_tasks(self, status: TaskStatus | None = None) -> list[dict]:
        """列出任务，可选按状态过滤。"""
        with self.lock:
            tasks = []
            for tid, t in self.tasks.items():
                if status is not None and t["status"] != status:
                    continue
                tasks.append({"task_id": tid, **dict(t)})
            tasks.sort(key=lambda t: t["created_at"], reverse=True)
            return tasks

    def run_background(self, task_id: str, fn: Callable):
        """在线程中执行 fn，自动捕获异常更新状态。"""

        def _wrapper():
            self.update_task(task_id, status=TaskStatus.RUNNING)
            try:
                fn(task_id)
            except Exception as e:
                self.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    error=str(e),
                )

        thread = threading.Thread(target=_wrapper, daemon=True)
        thread.start()

    def _load(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self.tasks = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.tasks = {}

    def _save(self):
        tmp = self.state_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.tasks, f, ensure_ascii=False, indent=2)
        tmp.replace(self.state_file)
