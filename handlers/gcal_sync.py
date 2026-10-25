"""
Google Calendar sync handler + background poller.

Registers two task handlers:
  "gcal_sync_push" — push all schedules to Google Calendar
  "gcal_poll"      — poll calendar for new commands and dispatch them

Also provides GCalPoller, a daemon thread that:
  - Polls calendar for commands every GCAL_POLL_INTERVAL seconds (default 60)
  - Listens for schedule.created / schedule.deleted events on the EventBus
    and syncs that individual schedule to/from the calendar automatically.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from agent.registry import register_handler

if TYPE_CHECKING:
    from agent.agent import Agent

log = logging.getLogger(__name__)

_POLL_INTERVAL = int(os.environ.get("GCAL_POLL_INTERVAL", "60"))
_SYNC_ON_CHANGE = os.environ.get("GCAL_SYNC_ON_CHANGE", "1") not in ("0", "false", "no")


# ──────────────────────────────────────────────────────────────────────────────
# Task handlers
# ──────────────────────────────────────────────────────────────────────────────


def handle_gcal_sync_push(payload: dict) -> dict:
    """
    Push all schedules in the DB to Google Calendar.

    Payload keys (all optional):
      calendar_id : str  Override target calendar ID
    """
    from agent.agent import Agent  # noqa: PLC0415
    from agent.skills.gcal_scheduler import GCalScheduler  # noqa: PLC0415

    agent = Agent()  # uses the global singleton db
    calendar_id = payload.get("calendar_id") or None

    gcal = GCalScheduler(agent, calendar_id=calendar_id)

    if not gcal.available():
        return {
            "ok": False,
            "error": (
                "Google credentials not available. "
                "Set GOOGLE_CREDS_JSON=/path/to/service_account.json"
            ),
        }

    schedules = agent.scheduler.list_schedules()
    result = gcal.sync_schedules_to_calendar(schedules)
    result["ok"] = result.get("failed", 0) == 0
    return result


def handle_gcal_poll(payload: dict) -> dict:
    """
    Poll Google Calendar for incoming agent commands and dispatch them.

    Payload keys (all optional):
      since_minutes      : int  How far back to look (default 5)
      command_calendar_id: str  Override command calendar ID
    """
    from agent.agent import Agent  # noqa: PLC0415
    from agent.skills.gcal_scheduler import GCalScheduler  # noqa: PLC0415

    agent = Agent()
    since_minutes = int(payload.get("since_minutes", 5))
    command_calendar_id = payload.get("command_calendar_id") or None

    gcal = GCalScheduler(agent, command_calendar_id=command_calendar_id)

    if not gcal.available():
        return {
            "ok": False,
            "error": "Google credentials not available.",
        }

    commands = gcal.poll_calendar_commands(since_minutes=since_minutes)
    return {"ok": True, "commands_processed": len(commands), "commands": commands}


# Register handlers
register_handler("gcal_sync_push", handle_gcal_sync_push)
register_handler("gcal_poll", handle_gcal_poll)


# ──────────────────────────────────────────────────────────────────────────────
# GCalPoller — background daemon thread
# ──────────────────────────────────────────────────────────────────────────────


class GCalPoller:
    """
    Background thread that periodically polls Google Calendar for commands
    and syncs schedule changes to the calendar.

    Usage
    -----
    poller = GCalPoller()
    poller.start(agent)   # call once during app startup
    poller.stop()         # call on shutdown
    """

    def __init__(self, poll_interval: int = _POLL_INTERVAL):
        self._interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._agent: Optional["Agent"] = None
        self._gcal: Optional[Any] = None
        self.last_poll: Optional[str] = None
        self.last_sync: Optional[str] = None
        self._running = False

    def start(self, agent: "Agent") -> None:
        """Start the poller daemon thread and subscribe to EventBus events."""
        if self._running:
            log.warning("GCalPoller.start() called but already running")
            return

        self._agent = agent
        self._running = True
        self._stop_event.clear()

        # Build GCalScheduler (will be lazily used)
        self._gcal = None  # will be created on first use in _get_gcal()

        # Subscribe to schedule events on the EventBus (if sync-on-change enabled)
        if _SYNC_ON_CHANGE:
            try:
                agent.event_bus.subscribe("schedule.created", self._on_schedule_created)
                agent.event_bus.subscribe("schedule.deleted", self._on_schedule_deleted)
                log.info("GCalPoller: subscribed to schedule.created / schedule.deleted events")
            except Exception as exc:
                log.warning("GCalPoller: EventBus subscription failed: %s", exc)

        self._thread = threading.Thread(
            target=self._run,
            name="gcal-poller",
            daemon=True,
        )
        self._thread.start()
        log.info("GCalPoller started (poll_interval=%ds)", self._interval)

    def stop(self) -> None:
        """Signal the poller thread to stop and wait for it."""
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        log.info("GCalPoller stopped")

    @property
    def is_running(self) -> bool:
        return self._running and bool(self._thread and self._thread.is_alive())

    def _get_gcal(self):
        """Lazily create GCalScheduler when first needed."""
        if self._gcal is None and self._agent is not None:
            from agent.skills.gcal_scheduler import GCalScheduler  # noqa: PLC0415
            self._gcal = GCalScheduler(self._agent)
        return self._gcal

    def _run(self) -> None:
        """Main polling loop."""
        while not self._stop_event.is_set():
            try:
                self._do_poll()
            except Exception as exc:
                log.warning("GCalPoller: poll error: %s", exc)

            self._stop_event.wait(self._interval)

    def _do_poll(self) -> None:
        """Perform one poll cycle."""
        gcal = self._get_gcal()
        if gcal is None or not gcal.available():
            log.debug("GCalPoller: Google Calendar not available, skipping poll")
            return

        try:
            commands = gcal.poll_calendar_commands(since_minutes=max(self._interval // 60 + 1, 2))
            self.last_poll = datetime.now(timezone.utc).isoformat()
            if commands:
                log.info("GCalPoller: dispatched %d command(s) from calendar", len(commands))
        except Exception as exc:
            log.warning("GCalPoller._do_poll error: %s", exc)

    def _on_schedule_created(self, event) -> None:
        """EventBus handler: push newly created schedule to calendar."""
        if not _SYNC_ON_CHANGE:
            return
        try:
            gcal = self._get_gcal()
            if gcal is None or not gcal.available():
                return

            # Fetch the full schedule from DB to get next_run_at, etc.
            name = (event.payload or {}).get("name", "")
            if not name or self._agent is None:
                return
            schedule = self._agent.db.get_schedule_by_name(name)
            if not schedule:
                return

            event_id = gcal.push_schedule_to_calendar(schedule)
            self.last_sync = datetime.now(timezone.utc).isoformat()
            log.info("GCalPoller: synced new schedule '%s' → event %s", name, event_id)
        except Exception as exc:
            log.warning("GCalPoller._on_schedule_created error: %s", exc)

    def _on_schedule_deleted(self, event) -> None:
        """EventBus handler: remove calendar event when schedule is deleted."""
        if not _SYNC_ON_CHANGE:
            return
        try:
            gcal = self._get_gcal()
            if gcal is None or not gcal.available():
                return

            name = (event.payload or {}).get("name", "")
            if not name:
                return

            gcal.delete_calendar_event_for_schedule(name)
            self.last_sync = datetime.now(timezone.utc).isoformat()
            log.info("GCalPoller: deleted calendar event for schedule '%s'", name)
        except Exception as exc:
            log.warning("GCalPoller._on_schedule_deleted error: %s", exc)

    def trigger_sync(self, agent: Optional["Agent"] = None) -> dict:
        """
        Manually trigger a full sync of all schedules to Google Calendar.
        Returns the sync result dict.
        """
        _agent = agent or self._agent
        if _agent is None:
            return {"ok": False, "error": "No agent attached"}

        try:
            gcal = self._get_gcal()
            if gcal is None:
                from agent.skills.gcal_scheduler import GCalScheduler  # noqa: PLC0415
                gcal = GCalScheduler(_agent)
            if not gcal.available():
                return {"ok": False, "error": "Google Calendar not available"}

            schedules = _agent.scheduler.list_schedules()
            result = gcal.sync_schedules_to_calendar(schedules)
            result["ok"] = result.get("failed", 0) == 0
            self.last_sync = datetime.now(timezone.utc).isoformat()
            return result
        except Exception as exc:
            log.warning("GCalPoller.trigger_sync error: %s", exc)
            return {"ok": False, "error": str(exc)}

    def trigger_poll(self, since_minutes: int = 5, agent: Optional["Agent"] = None) -> dict:
        """
        Manually trigger a single calendar command poll.
        Returns the poll result dict.
        """
        _agent = agent or self._agent
        if _agent is None:
            return {"ok": False, "error": "No agent attached"}

        try:
            gcal = self._get_gcal()
            if gcal is None:
                from agent.skills.gcal_scheduler import GCalScheduler  # noqa: PLC0415
                gcal = GCalScheduler(_agent)
            if not gcal.available():
                return {"ok": False, "error": "Google Calendar not available"}

            commands = gcal.poll_calendar_commands(since_minutes=since_minutes)
            self.last_poll = datetime.now(timezone.utc).isoformat()
            return {
                "ok": True,
                "commands_processed": len(commands),
                "commands": commands,
            }
        except Exception as exc:
            log.warning("GCalPoller.trigger_poll error: %s", exc)
            return {"ok": False, "error": str(exc)}

    def status(self) -> dict:
        """Return current poller status."""
        gcal = self._get_gcal()
        return {
            "available": gcal.available() if gcal else False,
            "poller_running": self.is_running,
            "last_poll": self.last_poll,
            "last_sync": self.last_sync,
            "poll_interval_seconds": self._interval,
            "sync_on_change": _SYNC_ON_CHANGE,
        }


# Type hint helper — avoid NameError at import time
from typing import Any  # noqa: E402
