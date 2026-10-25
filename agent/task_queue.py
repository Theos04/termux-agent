import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .config import AgentConfig
from .database import Database
from .events import EventBus


class TaskQueue:
    """Priority-based task queue with retry, timeout, and persistence."""

    def __init__(self, db: Database, event_bus: EventBus, config: AgentConfig):
        self._db = db
        self._events = event_bus
        self._config = config

    def enqueue(
        self,
        task_type: str,
        payload: Optional[dict] = None,
        priority: int = 5,
        scheduled_at: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> int:
        payload = payload or {}
        timeout = timeout_seconds or self._config.default_timeout
        retries = max_retries if max_retries is not None else self._config.max_retries

        task_id = self._db.insert_task(
            task_type=task_type,
            payload=payload,
            priority=priority,
            scheduled_at=scheduled_at,
            timeout_seconds=timeout,
            max_retries=retries,
        )

        self._events.emit(
            "task.enqueued",
            {
                "task_id": task_id,
                "task_type": task_type,
                "priority": priority,
                "scheduled_at": scheduled_at,
            },
            source="task_queue",
        )
        self._db.increment_stat("tasks_enqueued")
        return task_id

    def claim(self, worker_id: str) -> Optional[dict]:
        task = self._db.claim_next_task(worker_id)
        if task:
            self._events.emit(
                "task.claimed",
                {"task_id": task["id"], "worker_id": worker_id, "task_type": task["task_type"]},
                source="task_queue",
            )
        return task

    def complete(self, task_id: int, result: Any) -> None:
        self._db.complete_task(task_id, result)
        self._events.emit(
            "task.completed",
            {"task_id": task_id, "result": result},
            source="task_queue",
        )
        self._db.increment_stat("tasks_completed")

    def fail(self, task_id: int, error: str, retry_count: int, max_retries: int) -> bool:
        """Fail a task. Returns True if scheduled for retry."""
        if retry_count < max_retries:
            delay = self._config.retry_base_delay * math.pow(2, retry_count)
            next_retry = (
                datetime.now(timezone.utc) + timedelta(seconds=delay)
            ).isoformat()
            self._db.fail_task(task_id, error, retry=True, next_retry_at=next_retry)
            self._events.emit(
                "task.retry_scheduled",
                {
                    "task_id": task_id,
                    "retry_count": retry_count + 1,
                    "next_retry_at": next_retry,
                    "error": error,
                },
                source="task_queue",
            )
            self._db.increment_stat("tasks_retried")
            return True

        self._db.fail_task(task_id, error, retry=False)
        self._events.emit(
            "task.failed",
            {"task_id": task_id, "error": error},
            source="task_queue",
        )
        self._db.increment_stat("tasks_failed")
        return False

    def timeout(self, task_id: int) -> None:
        self._db.timeout_task(task_id)
        self._events.emit(
            "task.timeout",
            {"task_id": task_id},
            source="task_queue",
        )
        self._db.increment_stat("tasks_timeout")

    def get_task(self, task_id: int) -> Optional[dict]:
        return self._db.get_task(task_id)

    def list_tasks(
        self, status: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        return self._db.get_tasks(status, limit, offset)

    def stats(self) -> dict:
        counts = self._db.count_tasks_by_status()
        counts.update(self._db.get_stats())
        return counts
