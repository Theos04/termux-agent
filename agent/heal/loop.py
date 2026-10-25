"""Background heal loop: watches for failed/stuck tasks and orchestrates recovery."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .actions import HealActionResult, run_heal_action
from .classifier import HealClass, classify_error

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HealState:
    """Snapshot of heal-loop activity."""

    running: bool = False
    heal_attempt: int = 0
    last_heal_at: Optional[str] = None
    last_result: Optional[HealActionResult] = None
    consecutive_fails: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    def record(self, result: HealActionResult) -> None:
        self.last_heal_at = _utcnow()
        self.last_result = result
        self.heal_attempt += 1
        if result.ok:
            self.consecutive_fails = 0
        else:
            self.consecutive_fails += 1
        entry: dict[str, Any] = {
            "at": self.last_heal_at,
            "attempt": self.heal_attempt,
            "action": result.action,
            "ok": result.ok,
            "message": result.message,
        }
        if result.details:
            entry["details"] = result.details
        self.history.append(entry)
        # Keep history bounded
        if len(self.history) > 200:
            self.history = self.history[-200:]

    def as_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "heal_attempt": self.heal_attempt,
            "last_heal_at": self.last_heal_at,
            "last_result": (
                {
                    "ok": self.last_result.ok,
                    "action": self.last_result.action,
                    "message": self.last_result.message,
                }
                if self.last_result
                else None
            ),
            "consecutive_fails": self.consecutive_fails,
            "history_len": len(self.history),
        }


class HealLoop:
    """Periodically scans for failed/stuck tasks and runs recovery actions.

    Parameters
    ----------
    fetch_failed:
        Callable that returns a list of task dicts with at least
        ``{"id", "task_type", "error", "status"}`` fields.
    requeue:
        Callable invoked with a task dict to requeue it after a successful heal.
    poll_interval:
        Seconds between scans (default 30).
    max_consecutive_fails:
        Stop trying after this many back-to-back heal failures (default 5).
    notify:
        Optional callback for human-readable status messages.
    cdp_port:
        Override CDP port for Chrome heal actions.
    research_after:
        Pass through to ``run_heal_action`` — attempt research after N unknowns.
    """

    def __init__(
        self,
        fetch_failed: Callable[[], list[dict[str, Any]]],
        requeue: Callable[[dict[str, Any]], None],
        *,
        poll_interval: float = 30.0,
        max_consecutive_fails: int = 5,
        notify: Optional[Callable[[str], None]] = None,
        cdp_port: Optional[int] = None,
        research_after: int = 2,
    ) -> None:
        self._fetch_failed = fetch_failed
        self._requeue = requeue
        self._poll_interval = poll_interval
        self._max_consecutive_fails = max_consecutive_fails
        self._notify = notify or (lambda msg: None)
        self._cdp_port = cdp_port
        self._research_after = research_after

        self.state = HealState()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background heal loop thread."""
        if self.state.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="heal-loop", daemon=True
        )
        self._thread.start()
        self.state.running = True
        logger.info("HealLoop started (poll_interval=%.1fs)", self._poll_interval)
        self._notify(f"HealLoop started — scanning every {self._poll_interval}s")

    def stop(self) -> None:
        """Signal the loop to stop and wait for the thread to exit."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(self._poll_interval, 5))
        self.state.running = False
        logger.info("HealLoop stopped")

    def heal_once(self) -> list[HealActionResult]:
        """Run a single heal pass synchronously; returns results for each task."""
        tasks = self._fetch_failed()
        if not tasks:
            return []
        results: list[HealActionResult] = []
        seen_classes: set[HealClass] = set()

        for task in tasks:
            hclass = classify_error(
                error=task.get("error") or task.get("last_error") or "",
                status=task.get("status"),
                task_type=task.get("task_type"),
            )

            # Deduplicate actions for the same heal class in one pass
            if hclass in seen_classes and hclass not in (
                HealClass.UNKNOWN,
                HealClass.TASK_STUCK,
                HealClass.TIMEOUT,
            ):
                logger.debug(
                    "Skipping duplicate heal for class=%s task=%s",
                    hclass,
                    task.get("id"),
                )
                continue
            seen_classes.add(hclass)

            logger.info(
                "Healing task=%s class=%s attempt=%d",
                task.get("id"),
                hclass,
                self.state.heal_attempt,
            )

            result = run_heal_action(
                hclass,
                error=task.get("error") or task.get("last_error") or "",
                port=self._cdp_port,
                research_after=self._research_after,
                heal_attempt=self.state.heal_attempt,
            )
            self.state.record(result)
            results.append(result)

            if result.ok:
                self._notify(
                    f"✓ Healed task {task.get('id')} [{hclass.value}]: {result.action}"
                )
                try:
                    self._requeue(task)
                    logger.info("Requeued task %s after heal", task.get("id"))
                except Exception as exc:
                    logger.warning("Requeue failed for task %s: %s", task.get("id"), exc)
            else:
                self._notify(
                    f"✗ Heal failed task {task.get('id')} [{hclass.value}]: {result.message}"
                )
                logger.warning(
                    "Heal failed task=%s class=%s msg=%s",
                    task.get("id"),
                    hclass,
                    result.message,
                )

        return results

    @property
    def status(self) -> dict[str, Any]:
        """Return a JSON-serialisable status snapshot."""
        return self.state.as_dict()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                logger.exception("HealLoop tick error: %s", exc)
            self._stop.wait(self._poll_interval)

    def _tick(self) -> None:
        if self.state.consecutive_fails >= self._max_consecutive_fails:
            logger.error(
                "HealLoop suspended: %d consecutive failures — manual intervention needed",
                self.state.consecutive_fails,
            )
            self._notify(
                f"⚠ HealLoop suspended after {self.state.consecutive_fails} "
                "consecutive failures. Manual intervention may be needed."
            )
            self._stop.set()
            self.state.running = False
            return

        self.heal_once()
