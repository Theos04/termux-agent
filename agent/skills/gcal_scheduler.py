"""
Google Calendar ↔ Agent Scheduler integration.

Provides bi-directional sync between the agent's cron-like schedule DB
and Google Calendar events, plus a pull-based "calendar as command bus"
mechanism.

Push (Agent → Calendar):
  GCalScheduler.sync_schedules_to_calendar(schedules)
  GCalScheduler.push_schedule_to_calendar(schedule)
  GCalScheduler.delete_calendar_event_for_schedule(schedule_name)

Pull (Calendar → Agent):
  GCalScheduler.poll_calendar_commands(since_minutes=5)
    Scans recent events for ones tagged agent_command=true or title [CMD].
    Parses JSON/key=value from description, then either:
      • adds a schedule (if cron_expr present), or
      • enqueues a task (if task_type only)
    Marks processed events by appending "✅ Processed at <ts>" to description.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from agent.agent import Agent

log = logging.getLogger(__name__)

# ── Timezone ──────────────────────────────────────────────────────────────────
_TZ_NAME = os.environ.get("TZ", "Asia/Kolkata")

try:
    from zoneinfo import ZoneInfo
    _LOCAL_TZ = ZoneInfo(_TZ_NAME)
except ImportError:
    try:
        import pytz
        _LOCAL_TZ = pytz.timezone(_TZ_NAME)
    except ImportError:
        _LOCAL_TZ = timezone.utc

# ── Calendar IDs ──────────────────────────────────────────────────────────────
_DEFAULT_CALENDAR_ID = os.environ.get(
    "GOOGLE_CALENDAR_ID",
    "55f7c8303aa5acc23d6a484bd09a5f5966a02762a8933428f684183cd79635a9@group.calendar.google.com",
)
_COMMAND_CALENDAR_ID = os.environ.get("GCAL_COMMAND_CALENDAR_ID") or _DEFAULT_CALENDAR_ID


def _now_local() -> datetime:
    """Current time in the configured local timezone."""
    return datetime.now(tz=timezone.utc).astimezone(_LOCAL_TZ)


def _iso(dt: datetime) -> str:
    """Format datetime to ISO-8601 with UTC offset."""
    return dt.isoformat()


def _parse_payload_from_description(desc: str) -> dict:
    """
    Try to extract structured data from event description text.

    Tries JSON first; falls back to key=value line parsing.
    Returns dict with any of: task_type, payload, cron_expr, name.
    """
    if not desc:
        return {}

    # Strip leading/trailing whitespace
    text = desc.strip()

    # JSON parse — look for a JSON block
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

    # Try full-text JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Fall back to key=value parsing
    result: Dict[str, Any] = {}
    for line in text.splitlines():
        if "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if key in ("task_type", "cron_expr", "name"):
                result[key] = val
            elif key == "payload":
                try:
                    result["payload"] = json.loads(val)
                except json.JSONDecodeError:
                    result["payload"] = {"raw": val}
    return result


class GCalScheduler:
    """
    Bi-directional bridge between the agent's scheduler DB and Google Calendar.

    Parameters
    ----------
    agent : Agent
        The running agent instance — used to access scheduler, queue, db.
    calendar_id : str, optional
        Calendar to use for schedule events (default: GOOGLE_CALENDAR_ID env).
    command_calendar_id : str, optional
        Calendar to poll for incoming commands (default: same as calendar_id).
    """

    def __init__(
        self,
        agent: "Agent",
        calendar_id: Optional[str] = None,
        command_calendar_id: Optional[str] = None,
    ):
        self._agent = agent
        self._calendar_id = calendar_id or _DEFAULT_CALENDAR_ID
        self._command_calendar_id = command_calendar_id or _COMMAND_CALENDAR_ID
        self._ws: Optional[Any] = None  # lazy GoogleWorkspaceSkill

    # ── internals ─────────────────────────────────────────────────────────────

    def _workspace(self):
        """Lazily build GoogleWorkspaceSkill instance (import-guarded)."""
        if self._ws is None:
            try:
                from agent.skills.google_workspace import GoogleWorkspaceSkill  # noqa: PLC0415
                self._ws = GoogleWorkspaceSkill()
            except ImportError as exc:
                log.warning("google_workspace skill unavailable: %s", exc)
                raise
        return self._ws

    def available(self) -> bool:
        """Return True if Google credentials exist and libraries are installed."""
        try:
            ws = self._workspace()
            return ws.available()
        except Exception as exc:
            log.debug("GCalScheduler.available() → False: %s", exc)
            return False

    # ── Schedule → description text ───────────────────────────────────────────

    @staticmethod
    def _schedule_to_description(schedule: dict) -> str:
        payload_str = json.dumps(schedule.get("payload") or {}, ensure_ascii=False)
        enabled = "yes" if schedule.get("enabled", 1) else "no"
        lines = [
            f"cron_expr={schedule.get('cron_expr', '')}",
            f"task_type={schedule.get('task_type', '')}",
            f"next_run_at={schedule.get('next_run_at', '')}",
            f"payload={payload_str}",
            f"enabled={enabled}",
            "",
            "⚙️ Managed by Agent Scheduler — do not edit above this line.",
        ]
        return "\n".join(lines)

    # ── Push: Agent → Calendar ────────────────────────────────────────────────

    def push_schedule_to_calendar(self, schedule: dict) -> Optional[str]:
        """
        Create or update a Google Calendar event for a single schedule.

        Returns the calendar event ID, or None on failure.
        """
        try:
            ws = self._workspace()
            name = schedule.get("name", "")
            summary = f"🤖 [CRON] {name}"
            description = self._schedule_to_description(schedule)

            # Calculate start/end
            next_run_raw = schedule.get("next_run_at")
            if next_run_raw:
                try:
                    start_dt = datetime.fromisoformat(next_run_raw)
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    start_dt = _now_local() + timedelta(hours=1)
            else:
                start_dt = _now_local() + timedelta(hours=1)

            end_dt = start_dt + timedelta(minutes=15)

            # Extended properties to tag this as an agent schedule
            ext_props = {
                "private": {
                    "agent_schedule_name": name,
                    "agent_managed": "true",
                }
            }

            # Check if event already exists for this schedule
            existing_event_id = None

            # Check DB first for cached event ID
            try:
                existing_event_id = self._agent.db.get_schedule_gcal_event(name)
            except Exception:
                pass

            # Also search Google Calendar by extended property
            if not existing_event_id:
                try:
                    existing_event_id = ws.calendar_find_by_extended_property(
                        key="agent_schedule_name",
                        value=name,
                        calendar_id=self._calendar_id,
                    )
                except Exception as exc:
                    log.debug("Extended property search failed: %s", exc)

            start_str = _iso(start_dt)
            end_str = _iso(end_dt)

            if existing_event_id:
                # Update existing event
                try:
                    ws.calendar_update_event(
                        event_id=existing_event_id,
                        calendar_id=self._calendar_id,
                        summary=summary,
                        description=description,
                        start=start_str,
                        end=end_str,
                    )
                    log.info("Updated calendar event %s for schedule '%s'", existing_event_id, name)
                    return existing_event_id
                except Exception as exc:
                    log.warning(
                        "Update of event %s failed (%s); will create new", existing_event_id, exc
                    )
                    existing_event_id = None

            # Create new event with extended properties
            try:
                from googleapiclient.discovery import build as _gclient_build  # noqa
            except ImportError:
                pass

            svc = ws._calendar_client()
            body: Dict[str, Any] = {
                "summary": summary,
                "description": description,
                "start": {"dateTime": start_str, "timeZone": _TZ_NAME},
                "end": {"dateTime": end_str, "timeZone": _TZ_NAME},
                "extendedProperties": ext_props,
            }
            event = svc.events().insert(calendarId=self._calendar_id, body=body).execute()
            event_id: str = event.get("id", "")
            log.info("Created calendar event %s for schedule '%s'", event_id, name)

            # Persist mapping in DB
            try:
                self._agent.db.set_schedule_gcal_event(name, event_id)
            except Exception as exc:
                log.debug("set_schedule_gcal_event failed: %s", exc)

            return event_id

        except Exception as exc:
            log.warning("push_schedule_to_calendar failed for '%s': %s", schedule.get("name"), exc)
            return None

    def sync_schedules_to_calendar(self, schedules: List[dict]) -> Dict[str, Any]:
        """
        Push all schedules to Google Calendar (idempotent).

        Returns summary dict with pushed/failed counts.
        """
        pushed = 0
        failed = 0
        errors: List[str] = []

        for schedule in schedules:
            try:
                eid = self.push_schedule_to_calendar(schedule)
                if eid:
                    pushed += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{schedule.get('name')}: {exc}")

        result = {"pushed": pushed, "failed": failed, "total": len(schedules)}
        if errors:
            result["errors"] = errors
        log.info("sync_schedules_to_calendar: %d pushed, %d failed", pushed, failed)
        return result

    def delete_calendar_event_for_schedule(self, schedule_name: str) -> bool:
        """
        Delete the calendar event linked to a schedule by name.

        Returns True if deleted (or already gone), False on error.
        """
        try:
            ws = self._workspace()

            # Look up event ID from DB
            event_id = None
            try:
                event_id = self._agent.db.get_schedule_gcal_event(schedule_name)
            except Exception:
                pass

            # Fall back to extended property search
            if not event_id:
                try:
                    event_id = ws.calendar_find_by_extended_property(
                        key="agent_schedule_name",
                        value=schedule_name,
                        calendar_id=self._calendar_id,
                    )
                except Exception as exc:
                    log.debug("Extended property search in delete failed: %s", exc)

            if not event_id:
                log.info("No calendar event found for schedule '%s'", schedule_name)
                return True  # nothing to delete

            ws.calendar_delete_event(event_id=event_id, calendar_id=self._calendar_id)
            log.info("Deleted calendar event %s for schedule '%s'", event_id, schedule_name)
            return True

        except Exception as exc:
            log.warning(
                "delete_calendar_event_for_schedule failed for '%s': %s", schedule_name, exc
            )
            return False

    # ── Pull: Calendar → Agent ────────────────────────────────────────────────

    def poll_calendar_commands(self, since_minutes: int = 5) -> List[dict]:
        """
        Scan recent calendar events for agent commands and dispatch them.

        An event is treated as an agent command if:
          - Its extendedProperties.private contains agent_command=true, OR
          - Its title starts with "[CMD]"

        The event description is parsed as JSON or key=value pairs to extract:
          task_type, payload, cron_expr, name

        Then:
          - cron_expr present → agent.scheduler.add_schedule()
          - task_type only    → agent.queue.enqueue()

        The processed event's description is updated to append:
          "✅ Processed at <ISO timestamp>"

        Returns list of dicts describing each processed command.
        """
        processed: List[dict] = []

        try:
            ws = self._workspace()
            events = ws.calendar_get_recent_events(
                minutes_back=since_minutes,
                calendar_id=self._command_calendar_id,
            )
        except Exception as exc:
            log.warning("poll_calendar_commands: failed to fetch events: %s", exc)
            return processed

        for event in events:
            try:
                event_id = event.get("id", "")
                summary = event.get("summary", "")
                description = event.get("description", "") or ""

                # Check if this is a command event
                ext = (event.get("extendedProperties") or {}).get("private") or {}
                is_command = (
                    ext.get("agent_command") == "true"
                    or summary.startswith("[CMD]")
                )
                if not is_command:
                    continue

                # Skip already-processed events
                if "✅ Processed at" in description:
                    log.debug("Skipping already-processed event %s", event_id)
                    continue

                # Parse command from description
                cmd = _parse_payload_from_description(description)
                task_type = cmd.get("task_type", "")
                cron_expr = cmd.get("cron_expr", "")
                payload = cmd.get("payload") or {}
                cmd_name = cmd.get("name") or summary.replace("[CMD]", "").strip()

                if not task_type and not cron_expr:
                    log.debug("Event %s has no task_type or cron_expr — skipping", event_id)
                    continue

                # Dispatch the command
                dispatch_result: Dict[str, Any] = {
                    "event_id": event_id,
                    "summary": summary,
                    "task_type": task_type,
                    "cron_expr": cron_expr,
                    "name": cmd_name,
                }

                if cron_expr and task_type:
                    # Add a schedule
                    try:
                        sid = self._agent.scheduler.add_schedule(
                            name=cmd_name or task_type,
                            task_type=task_type,
                            cron_expr=cron_expr,
                            payload=payload,
                        )
                        dispatch_result["action"] = "schedule_created"
                        dispatch_result["schedule_id"] = sid
                        log.info(
                            "Created schedule '%s' from calendar event %s",
                            cmd_name, event_id,
                        )
                    except Exception as exc:
                        dispatch_result["action"] = "schedule_error"
                        dispatch_result["error"] = str(exc)
                        log.warning("Failed to add schedule from event %s: %s", event_id, exc)

                elif task_type:
                    # Enqueue a one-off task
                    try:
                        task_id = self._agent.queue.enqueue(
                            task_type=task_type,
                            payload=payload,
                        )
                        dispatch_result["action"] = "task_enqueued"
                        dispatch_result["task_id"] = task_id
                        log.info(
                            "Enqueued task '%s' from calendar event %s",
                            task_type, event_id,
                        )
                    except Exception as exc:
                        dispatch_result["action"] = "task_error"
                        dispatch_result["error"] = str(exc)
                        log.warning("Failed to enqueue task from event %s: %s", event_id, exc)

                # Mark event as processed
                try:
                    ts = _now_local().isoformat()
                    new_description = (
                        description.rstrip()
                        + f"\n\n✅ Processed at {ts}\n"
                        + f"action={dispatch_result.get('action', 'unknown')}"
                    )
                    ws.calendar_update_event(
                        event_id=event_id,
                        calendar_id=self._command_calendar_id,
                        description=new_description,
                    )
                except Exception as exc:
                    log.warning("Failed to mark event %s as processed: %s", event_id, exc)

                processed.append(dispatch_result)

            except Exception as exc:
                log.warning("Error processing calendar event %s: %s", event.get("id"), exc)

        log.info("poll_calendar_commands: processed %d command(s)", len(processed))
        return processed
