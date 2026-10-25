import signal
import sys
from typing import Any, Optional

from .config import AgentConfig
from .database import Database
from .events import EventBus
from .monitoring import Monitor
from .registry import apply_subscribers, get_handlers, load_plugins
from .scheduler import Scheduler
from .task_queue import TaskQueue
from .workers import WorkerPool


class Agent:
    """Main orchestrator — wires together all subsystems."""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.db = Database(self.config.db_path)
        self.event_bus = EventBus(self.db)
        self.queue = TaskQueue(self.db, self.event_bus, self.config)
        self.scheduler = Scheduler(self.db, self.queue, self.event_bus, self.config)
        self.monitor = Monitor(self.db, self.queue, self.event_bus)
        self._pool: Optional[WorkerPool] = None
        self._running = False

    def setup(self) -> None:
        loaded = load_plugins()
        apply_subscribers(self.event_bus)
        self.event_bus.emit(
            "agent.setup",
            {"plugins_loaded": loaded},
            source="agent",
        )

    def start(self) -> None:
        if self._running:
            return
        self.setup()
        handlers = get_handlers()
        self._pool = WorkerPool(
            self.queue, self.event_bus, handlers, self.config
        )
        self._pool.start()
        self.scheduler.start()
        self._running = True
        self.event_bus.emit(
            "agent.started",
            {"workers": self.config.worker_count},
            source="agent",
        )

    def stop(self) -> None:
        if not self._running:
            return
        self.scheduler.stop()
        if self._pool:
            self._pool.stop()
        self._running = False
        self.event_bus.emit("agent.stopped", {}, source="agent")

    def submit(
        self,
        task_type: str,
        payload: Optional[dict] = None,
        priority: int = 5,
        scheduled_at: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> int:
        return self.queue.enqueue(
            task_type, payload, priority, scheduled_at, timeout_seconds
        )

    def add_schedule(
        self,
        name: str,
        task_type: str,
        cron_expr: str,
        payload: Optional[dict] = None,
        priority: int = 5,
    ) -> int:
        return self.scheduler.add_schedule(
            name, task_type, cron_expr, payload, priority
        )

    def run_forever(self) -> None:
        self.start()

        def _shutdown(signum, frame):
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        try:
            while self._running:
                signal.pause()
        except AttributeError:
            import time
            while self._running:
                time.sleep(1)
