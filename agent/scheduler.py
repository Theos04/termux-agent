import threading
import time
from datetime import datetime, timezone
from typing import Optional

from .config import AgentConfig
from .cron import CronExpression
from .database import Database
from .events import EventBus
from .task_queue import TaskQueue


class Scheduler:
    """Cron-like scheduler for periodic and future tasks."""

    def __init__(
        self,
        db: Database,
        queue: TaskQueue,
        event_bus: EventBus,
        config: AgentConfig,
    ):
        self._db = db
        self._queue = queue
        self._events = event_bus
        self._config = config
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def add_schedule(
        self,
        name: str,
        task_type: str,
        cron_expr: str,
        payload: Optional[dict] = None,
        priority: int = 5,
    ) -> int:
        cron = CronExpression(cron_expr)
        next_run = cron.next_run().isoformat()
        schedule_id = self._db.insert_schedule(
            name, task_type, cron_expr, payload or {}, priority, next_run
        )
        self._events.emit(
            "schedule.created",
            {
                "schedule_id": schedule_id,
                "name": name,
                "cron_expr": cron_expr,
                "next_run_at": next_run,
            },
            source="scheduler",
        )
        return schedule_id

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="scheduler", daemon=True
        )
        self._thread.start()
        self._events.emit("scheduler.started", {}, source="scheduler")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._events.emit("scheduler.stopped", {}, source="scheduler")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._process_due_schedules()
            except Exception as exc:
                self._events.emit(
                    "scheduler.error",
                    {"error": str(exc)},
                    source="scheduler",
                )
            self._stop.wait(30)

    def _process_due_schedules(self) -> None:
        for schedule in self._db.get_due_schedules():
            self._queue.enqueue(
                task_type=schedule["task_type"],
                payload=schedule.get("payload") or {},
                priority=schedule.get("priority", 5),
            )
            cron = CronExpression(schedule["cron_expr"])
            next_run = cron.next_run().isoformat()
            self._db.update_schedule_run(schedule["id"], next_run)
            self._events.emit(
                "schedule.triggered",
                {
                    "schedule_id": schedule["id"],
                    "name": schedule["name"],
                    "next_run_at": next_run,
                },
                source="scheduler",
            )

    def list_schedules(self) -> list[dict]:
        return self._db.get_schedules()

    def enable_schedule(self, name: str) -> None:
        self._db.set_schedule_enabled(name, True)
        self._events.emit(
            "schedule.enabled", {"name": name}, source="scheduler"
        )

    def disable_schedule(self, name: str) -> None:
        self._db.set_schedule_enabled(name, False)
        self._events.emit(
            "schedule.disabled", {"name": name}, source="scheduler"
        )
