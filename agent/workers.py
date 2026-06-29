import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .config import AgentConfig
from .events import EventBus
from .task_queue import TaskQueue

TaskHandler = Callable[[dict], Any]


class Worker:
    def __init__(
        self,
        worker_id: str,
        queue: TaskQueue,
        event_bus: EventBus,
        handlers: dict[str, TaskHandler],
        config: AgentConfig,
    ):
        self.worker_id = worker_id
        self._queue = queue
        self._events = event_bus
        self._handlers = handlers
        self._config = config
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name=f"worker-{self.worker_id}", daemon=True
        )
        self._thread.start()
        self._events.emit(
            "worker.started", {"worker_id": self.worker_id}, source="worker_pool"
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._events.emit(
            "worker.stopped", {"worker_id": self.worker_id}, source="worker_pool"
        )

    def _run(self) -> None:
        while not self._stop.is_set():
            task = self._queue.claim(self.worker_id)
            if not task:
                self._stop.wait(self._config.poll_interval)
                continue

            self._execute(task)

    def _execute(self, task: dict) -> None:
        task_id = task["id"]
        task_type = task["task_type"]
        handler = self._handlers.get(task_type)

        if not handler:
            self._queue.fail(
                task_id,
                f"No handler registered for task type: {task_type}",
                task["retry_count"],
                task["max_retries"],
            )
            return

        self._events.emit(
            "task.started",
            {"task_id": task_id, "worker_id": self.worker_id, "task_type": task_type},
            source="worker_pool",
        )

        result_holder: list[Any] = []
        error_holder: list[Exception] = []
        done = threading.Event()

        def run_handler() -> None:
            try:
                result_holder.append(handler(task.get("payload") or {}))
            except Exception as exc:
                error_holder.append(exc)
            finally:
                done.set()

        thread = threading.Thread(target=run_handler, daemon=True)
        thread.start()
        timeout = task.get("timeout_seconds", self._config.default_timeout)
        finished = done.wait(timeout=timeout)

        if not finished:
            self._queue.timeout(task_id)
            return

        if error_holder:
            self._queue.fail(
                task_id,
                str(error_holder[0]),
                task["retry_count"],
                task["max_retries"],
            )
            return

        self._queue.complete(task_id, result_holder[0] if result_holder else None)


class WorkerPool:
    """Pool of workers that process one task at a time each."""

    def __init__(
        self,
        queue: TaskQueue,
        event_bus: EventBus,
        handlers: dict[str, TaskHandler],
        config: AgentConfig,
    ):
        self._queue = queue
        self._events = event_bus
        self._handlers = handlers
        self._config = config
        self._workers: list[Worker] = []

    def start(self, count: Optional[int] = None) -> None:
        n = count or self._config.worker_count
        for _ in range(n):
            worker_id = uuid.uuid4().hex[:8]
            worker = Worker(
                worker_id, self._queue, self._events, self._handlers, self._config
            )
            worker.start()
            self._workers.append(worker)
        self._events.emit(
            "worker_pool.started",
            {"worker_count": n},
            source="worker_pool",
        )

    def stop(self) -> None:
        for worker in self._workers:
            worker.stop()
        self._workers.clear()
        self._events.emit("worker_pool.stopped", {}, source="worker_pool")

    @property
    def active_workers(self) -> int:
        return len(self._workers)
