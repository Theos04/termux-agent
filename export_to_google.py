#!/usr/bin/env python3
"""
export_to_google.py — One-shot Google Workspace export for any Maps scrape run.

Usage
-----
# Export the latest agent_runs/*.json to a new Google Sheet + Calendar + Drive
python export_to_google.py

# Export a specific extract file
python export_to_google.py agent_runs/bars_bistros_pune_phones_20261025_092652.json

# Export and reuse an existing spreadsheet (won't create a new one)
python export_to_google.py --sheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms

# Skip calendar events
python export_to_google.py --no-calendar

# Use a specific credentials file
python export_to_google.py --creds /path/to/service_account.json

Environment (via .env or shell):
  GOOGLE_CREDS_JSON    Path to credentials JSON (service account or OAuth2)
  GOOGLE_CALENDAR_ID   Target calendar ID  (default: primary)
  GOOGLE_SHEET_ID      Reuse this sheet ID (optional)
  GOOGLE_DRIVE_FOLDER_ID  Drive folder for uploads (optional)
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys

# ── load .env if python-dotenv is available ───────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("export_to_google")


def find_latest_extract() -> str | None:
    pattern = os.path.join(os.path.dirname(__file__), "agent_runs", "*.json")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    for f in files:
        # skip cron stubs / non-place files
        try:
            with open(f) as fh:
                d = json.load(fh)
            if d.get("cards") or d.get("count"):
                return f
        except Exception:
            continue
    return None


def main() -> None:
    p = argparse.ArgumentParser(description="Export Maps scrape to Google Workspace")
    p.add_argument("extract", nargs="?", help="Path to extract JSON (default: latest)")
    p.add_argument("--creds", default=None, help="Path to credentials JSON")
    p.add_argument("--sheet-id", default=os.environ.get("GOOGLE_SHEET_ID"), help="Reuse this spreadsheet ID")
    p.add_argument("--calendar-id", default=os.environ.get("GOOGLE_CALENDAR_ID", "primary"))
    p.add_argument("--drive-folder", default=os.environ.get("GOOGLE_DRIVE_FOLDER_ID"))
    p.add_argument("--run-name", default="")
    p.add_argument("--no-calendar", action="store_true", help="Skip calendar events")
    p.add_argument("--followup-start", default="", help="ISO datetime for first follow-up slot")
    args = p.parse_args()

    # ── resolve extract file ─────────────────────────────────────────────────
    extract_path = args.extract
    if not extract_path:
        extract_path = find_latest_extract()
        if not extract_path:
            log.error("No extract file found in agent_runs/. Run a scrape first.")
            sys.exit(1)
        log.info("Using latest extract: %s", extract_path)

    with open(extract_path) as f:
        data = json.load(f)

    cards = data.get("cards") or []
    if not cards:
        log.error("Extract file has no 'cards' array: %s", extract_path)
        sys.exit(1)

    log.info("Loaded %d cards (%d with phone)", len(cards), sum(1 for c in cards if c.get("phone")))

    # ── build skill ──────────────────────────────────────────────────────────
    sys.path.insert(0, os.path.dirname(__file__))
    from agent.skills.google_workspace import GoogleWorkspaceSkill

    ws = GoogleWorkspaceSkill(creds_path=args.creds)
    if not ws.available():
        log.error(
            "No Google credentials found.\n"
            "  Set GOOGLE_CREDS_JSON=/path/to/service_account.json\n"
            "  or place credentials.json in the project root.\n"
            "  See README for setup instructions."
        )
        sys.exit(1)

    # ── export ───────────────────────────────────────────────────────────────
    run_name = args.run_name or os.path.splitext(os.path.basename(extract_path))[0]

    result = ws.export_maps_run(
        cards=cards,
        run_name=run_name,
        spreadsheet_id=args.sheet_id or None,
        calendar_id=args.calendar_id,
        drive_folder_id=args.drive_folder or None,
        schedule_followups=not args.no_calendar,
        followup_start=args.followup_start,
        create_sheet=not bool(args.sheet_id),
    )

    print("\n" + "─" * 60)
    print(f"  Run: {result['run_name']}")
    print(f"  Cards exported : {result['cards_total']}  ({result['cards_with_phone']} with phone)")
    if result.get("sheet_url"):
        print(f"  Google Sheet   : {result['sheet_url']}")
    if result.get("event_ids"):
        print(f"  Calendar events: {len(result['event_ids'])} follow-up(s) created")
    if result.get("drive_url"):
        print(f"  Drive backup   : {result['drive_url']}")
    for k in ("sheets_error", "calendar_error", "drive_error"):
        if result.get(k):
            print(f"  ⚠ {k}: {result[k]}")
    print("─" * 60 + "\n")


if __name__ == "__main__":
    main()
