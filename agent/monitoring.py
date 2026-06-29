from typing import Any, Optional

from .database import Database
from .events import EventBus
from .task_queue import TaskQueue


class Monitor:
    """Aggregates task status, event history, and statistics."""

    def __init__(self, db: Database, queue: TaskQueue, event_bus: EventBus):
        self._db = db
        self._queue = queue
        self._events = event_bus

    def dashboard(self) -> dict[str, Any]:
        task_counts = self._db.count_tasks_by_status()
        stats = self._db.get_stats()
        schedules = self._db.get_schedules()
        recent_events = self._events.get_history(limit=20)
        recent_failed = self._db.get_tasks(status="failed", limit=10)

        return {
            "tasks": {
                "by_status": task_counts,
                "total": sum(task_counts.values()),
            },
            "stats": stats,
            "schedules": {
                "total": len(schedules),
                "enabled": sum(1 for s in schedules if s.get("enabled")),
            },
            "recent_events": recent_events,
            "recent_failed": recent_failed,
        }

    def task_detail(self, task_id: int) -> Optional[dict]:
        task = self._db.get_task(task_id)
        if not task:
            return None
        events = self._db.get_events(limit=500)
        task_events = [
            e for e in events
            if (e.get("payload") or {}).get("task_id") == task_id
        ]
        return {"task": task, "events": task_events}

    def event_history(
        self,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        return self._events.get_history(event_type, limit, offset)

    def failed_tasks(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self._db.get_tasks(status="failed", limit=limit, offset=offset)

    def stats(self) -> dict:
        return self._queue.stats()
