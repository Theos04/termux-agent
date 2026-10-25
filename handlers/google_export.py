"""
Google Workspace export handler.

Exports a maps-scrape result (or any list of place-cards) to:
  • Google Sheets   — tabular leads data
  • Google Calendar — follow-up call events
  • Google Drive    — raw JSON backup

Payload keys
------------
cards          : list[dict]  Place-cards from MapsGeoSkill (required OR extract_path)
extract_path   : str         Path to a JSON extract file written by MapsGeoSkill
run_name       : str         Human label for this run (auto-generated if omitted)
spreadsheet_id : str         Reuse an existing sheet; creates a new one if omitted
calendar_id    : str         Google Calendar ID (default: GOOGLE_CALENDAR_ID env / 'primary')
drive_folder_id: str         Drive folder ID (optional)
schedule_followups: bool     Create Calendar events (default: True)
followup_start : str         ISO-8601 datetime for first follow-up slot
creds_path     : str         Path to service-account JSON (overrides env var)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

from agent.registry import register_handler

log = logging.getLogger(__name__)


def handle_google_export(payload: dict) -> dict:
    from agent.skills.google_workspace import GoogleWorkspaceSkill

    # ── resolve cards ────────────────────────────────────────────────────────
    cards: List[Dict[str, Any]] = payload.get("cards") or []

    if not cards:
        extract_path = payload.get("extract_path") or ""
        if extract_path and os.path.isfile(extract_path):
            with open(extract_path) as f:
                data = json.load(f)
            cards = data.get("cards") or []
            log.info("Loaded %d cards from %s", len(cards), extract_path)

    if not cards:
        return {"ok": False, "error": "No cards provided and no extract_path found"}

    # ── build skill ──────────────────────────────────────────────────────────
    creds_path = payload.get("creds_path") or None
    ws = GoogleWorkspaceSkill(creds_path=creds_path)

    if not ws.available():
        return {
            "ok": False,
            "error": (
                "Google credentials not found. "
                "Set GOOGLE_CREDS_JSON=/path/to/service_account.json "
                "or place credentials.json in the project root."
            ),
        }

    result = ws.export_maps_run(
        cards=cards,
        run_name=payload.get("run_name") or "",
        spreadsheet_id=payload.get("spreadsheet_id") or None,
        calendar_id=payload.get("calendar_id") or "",
        drive_folder_id=payload.get("drive_folder_id") or None,
        schedule_followups=bool(payload.get("schedule_followups", True)),
        followup_start=payload.get("followup_start") or "",
        create_sheet=not bool(payload.get("spreadsheet_id")),
    )

    result["ok"] = (
        bool(result.get("sheet_id"))
        or bool(result.get("event_ids"))
        or bool(result.get("drive_file_id"))
    )
    return result


# Register the handler so the task-queue can dispatch to it
register_handler("google_export", handle_google_export)
