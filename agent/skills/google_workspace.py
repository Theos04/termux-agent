"""
Google Workspace integration skill.

Provides free-tier access to:
  - Google Sheets  (read/write data via Sheets API v4)
  - Google Calendar (create/list events via Calendar API v3)
  - Google Drive    (list/upload small files via Drive API v3)

Authentication: service account JSON key file (100 % free, no OAuth browser flow).

Free quotas (as of 2024):
  Sheets  → 300 req/min, unlimited reads, 5M cells
  Calendar→ 1,000,000 req/day per project
  Drive   → 15 GB storage, 1,000 req/day upload

Usage
-----
from agent.skills.google_workspace import GoogleWorkspaceSkill

ws = GoogleWorkspaceSkill()          # reads GOOGLE_CREDS_JSON env var
ws = GoogleWorkspaceSkill("/path/to/service_account.json")

# Sheets
sheet_id = ws.sheets_create("My Leads")
ws.sheets_append(sheet_id, [["Name","Phone","City"],["Chai Corner","9876543210","Pune"]])
rows = ws.sheets_read(sheet_id)

# Calendar
event_id = ws.calendar_create_event(
    summary="Follow-up call",
    start="2026-10-26T10:00:00+05:30",
    end="2026-10-26T10:30:00+05:30",
    description="Call 9876543210 – Chai Corner",
)
events = ws.calendar_list_events(max_results=10)

# Drive
file_id = ws.drive_upload_json("leads_pune.json", {"cards": [...]})
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Scopes — read-only where possible, write where we genuinely need it
# ──────────────────────────────────────────────────────────────────────────────
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",          # Sheets R/W
    "https://www.googleapis.com/auth/calendar",              # Calendar R/W
    "https://www.googleapis.com/auth/drive.file",            # Drive (own files only)
]

# Default calendar ID — "primary" resolves to the service-account calendar;
# set GOOGLE_CALENDAR_ID env var to share a real user calendar with the SA.
DEFAULT_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")


class GoogleWorkspaceSkill:
    """
    Thin, dependency-light wrapper around three Google APIs.
    All methods raise on hard failure and return None / [] on soft miss.
    """

    name = "google_workspace"

    def __init__(self, creds_path: Optional[str] = None):
        """
        Parameters
        ----------
        creds_path : str, optional
            Path to a service-account JSON key file.
            Falls back to the GOOGLE_CREDS_JSON environment variable,
            then to credentials.json in the project root.
        """
        self._creds_path = (
            creds_path
            or os.environ.get("GOOGLE_CREDS_JSON")
            or self._default_creds_path()
        )
        self._creds = None
        self._sheets  = None
        self._calendar = None
        self._drive    = None

    # ── credential & client helpers ──────────────────────────────────────────

    @staticmethod
    def _default_creds_path() -> str:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(root, "credentials.json")

    def _load_creds(self):
        if self._creds is not None:
            return self._creds
        try:
            from google.oauth2.service_account import Credentials
        except ImportError as exc:
            raise RuntimeError(
                "google-auth not installed — run: pip install google-auth"
            ) from exc

        path = self._creds_path
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"Google credentials file not found: {path}\n"
                "Set GOOGLE_CREDS_JSON=/path/to/service_account.json"
            )

        with open(path) as f:
            key_data = json.load(f)

        cred_type = key_data.get("type", "")
        if cred_type == "service_account":
            self._creds = Credentials.from_service_account_file(path, scopes=_SCOPES)
        elif cred_type in ("authorized_user", ""):
            # OAuth2 user credentials (downloaded from GCP console as oauth_client.json)
            from google.oauth2.credentials import Credentials as UserCreds
            self._creds = UserCreds(
                token=key_data.get("access_token"),
                refresh_token=key_data.get("refresh_token"),
                token_uri=key_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=key_data.get("client_id"),
                client_secret=key_data.get("client_secret"),
                scopes=_SCOPES,
            )
        else:
            raise ValueError(f"Unsupported credential type: {cred_type!r}")

        log.info("Loaded Google credentials from %s (type=%s)", path, cred_type)
        return self._creds

    def _sheets_client(self):
        if self._sheets is None:
            from googleapiclient.discovery import build
            self._sheets = build("sheets", "v4", credentials=self._load_creds(), cache_discovery=False)
        return self._sheets

    def _calendar_client(self):
        if self._calendar is None:
            from googleapiclient.discovery import build
            self._calendar = build("calendar", "v3", credentials=self._load_creds(), cache_discovery=False)
        return self._calendar

    def _drive_client(self):
        if self._drive is None:
            from googleapiclient.discovery import build
            self._drive = build("drive", "v3", credentials=self._load_creds(), cache_discovery=False)
        return self._drive

    # ── availability check ───────────────────────────────────────────────────

    def available(self) -> bool:
        """Return True if credentials file exists and google-auth is installed."""
        if not os.path.isfile(self._creds_path):
            return False
        try:
            self._load_creds()
            return True
        except Exception as exc:
            log.warning("GoogleWorkspaceSkill not available: %s", exc)
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Google Sheets
    # ─────────────────────────────────────────────────────────────────────────

    def sheets_create(self, title: str) -> str:
        """
        Create a new Google Sheet and return its spreadsheet ID.
        Share the sheet with yourself via the Google Drive UI or set
        sharing from code if needed.
        """
        svc = self._sheets_client()
        body = {"properties": {"title": title}}
        resp = svc.spreadsheets().create(body=body, fields="spreadsheetId").execute()
        sid = resp["spreadsheetId"]
        log.info("Created spreadsheet '%s' → id=%s", title, sid)
        return sid

    def sheets_append(
        self,
        spreadsheet_id: str,
        rows: List[List[Any]],
        sheet: str = "Sheet1",
        value_input_option: str = "USER_ENTERED",
    ) -> int:
        """
        Append rows to a sheet.  Returns number of rows appended.

        Parameters
        ----------
        spreadsheet_id : str
            The spreadsheet ID from the URL or sheets_create().
        rows : list[list]
            List of rows; each row is a list of cell values.
        sheet : str
            Sheet/tab name (default Sheet1).
        value_input_option : str
            RAW or USER_ENTERED (allows dates/formulas).
        """
        svc = self._sheets_client()
        range_name = f"{sheet}!A1"
        body = {"values": rows}
        resp = (
            svc.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                insertDataOption="INSERT_ROWS",
                body=body,
            )
            .execute()
        )
        updates = resp.get("updates", {})
        n = updates.get("updatedRows", len(rows))
        log.info("Appended %d row(s) to %s", n, spreadsheet_id)
        return n

    def sheets_read(
        self,
        spreadsheet_id: str,
        range_name: str = "Sheet1",
    ) -> List[List[Any]]:
        """Read all values from a range (default: entire Sheet1)."""
        svc = self._sheets_client()
        resp = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        return resp.get("values", [])

    def sheets_clear(self, spreadsheet_id: str, range_name: str = "Sheet1") -> None:
        """Clear all values in range."""
        svc = self._sheets_client()
        svc.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id, range=range_name, body={}
        ).execute()
        log.info("Cleared %s in %s", range_name, spreadsheet_id)

    def sheets_write_places(
        self,
        spreadsheet_id: str,
        cards: List[Dict[str, Any]],
        sheet: str = "Sheet1",
        clear_first: bool = False,
        add_header: bool = True,
    ) -> int:
        """
        Write a list of place-cards (from MapsGeoSkill) to a Google Sheet.

        Columns: Name | Phone | Category | Rating | Reviews | Address | Maps URL | Scraped At
        """
        if clear_first:
            self.sheets_clear(spreadsheet_id, sheet)

        rows: List[List[Any]] = []
        if add_header:
            rows.append([
                "Name", "Phone", "Category", "Rating",
                "Reviews", "Address", "Maps URL", "Scraped At",
            ])

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        for c in cards:
            rows.append([
                c.get("name", ""),
                c.get("phone", ""),
                c.get("category", ""),
                c.get("rating", ""),
                c.get("reviews", ""),
                c.get("address", ""),
                c.get("maps_url", ""),
                ts,
            ])

        return self.sheets_append(spreadsheet_id, rows, sheet=sheet)

    # ─────────────────────────────────────────────────────────────────────────
    # Google Calendar
    # ─────────────────────────────────────────────────────────────────────────

    def calendar_create_event(
        self,
        summary: str,
        start: str,
        end: str,
        description: str = "",
        location: str = "",
        calendar_id: str = DEFAULT_CALENDAR_ID,
        timezone: str = "Asia/Kolkata",
    ) -> str:
        """
        Create a calendar event and return its event ID.

        Parameters
        ----------
        summary     : Event title
        start / end : ISO-8601 datetime strings, e.g. '2026-10-26T10:00:00+05:30'
        description : Optional body text
        location    : Optional location string
        calendar_id : 'primary' or shared calendar ID
        timezone    : IANA timezone name
        """
        svc = self._calendar_client()
        body = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start, "timeZone": timezone},
            "end":   {"dateTime": end,   "timeZone": timezone},
        }
        event = svc.events().insert(calendarId=calendar_id, body=body).execute()
        eid = event.get("id", "")
        log.info("Created calendar event '%s' → id=%s", summary, eid)
        return eid

    def calendar_list_events(
        self,
        calendar_id: str = DEFAULT_CALENDAR_ID,
        max_results: int = 25,
        time_min: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List upcoming calendar events.

        Parameters
        ----------
        time_min    : RFC3339 lower bound (default: now)
        max_results : Maximum events to return
        """
        svc = self._calendar_client()
        if time_min is None:
            time_min = datetime.now(tz=__import__("datetime").timezone.utc).isoformat()
        resp = (
            svc.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        items = resp.get("items", [])
        log.info("Listed %d calendar event(s)", len(items))
        return items

    def calendar_update_event(
        self,
        event_id: str,
        calendar_id: str = DEFAULT_CALENDAR_ID,
        **fields,
    ) -> Dict[str, Any]:
        """
        PATCH an existing calendar event with new field values.

        Parameters
        ----------
        event_id    : The event ID to update
        calendar_id : Calendar containing the event
        **fields    : Any event fields to update, e.g. summary=, description=,
                      start=, end= (ISO-8601 strings)

        Returns the updated event resource dict.
        """
        svc = self._calendar_client()
        body: Dict[str, Any] = {}

        if "summary" in fields:
            body["summary"] = fields["summary"]
        if "description" in fields:
            body["description"] = fields["description"]
        if "location" in fields:
            body["location"] = fields["location"]

        tz = fields.get("timezone", "Asia/Kolkata")
        if "start" in fields:
            body["start"] = {"dateTime": fields["start"], "timeZone": tz}
        if "end" in fields:
            body["end"] = {"dateTime": fields["end"], "timeZone": tz}

        event = (
            svc.events()
            .patch(calendarId=calendar_id, eventId=event_id, body=body)
            .execute()
        )
        log.info("Updated calendar event %s", event_id)
        return event

    def calendar_find_by_extended_property(
        self,
        key: str,
        value: str,
        calendar_id: str = DEFAULT_CALENDAR_ID,
    ) -> Optional[str]:
        """
        Search for a calendar event by its private extended property.

        Returns the event ID of the first matching event, or None.

        Parameters
        ----------
        key         : Extended property key name
        value       : Expected property value
        calendar_id : Calendar to search in
        """
        svc = self._calendar_client()
        try:
            resp = (
                svc.events()
                .list(
                    calendarId=calendar_id,
                    privateExtendedProperty=f"{key}={value}",
                    maxResults=5,
                    singleEvents=True,
                )
                .execute()
            )
            items = resp.get("items", [])
            if items:
                eid = items[0].get("id")
                log.debug(
                    "calendar_find_by_extended_property(%s=%s) → %s", key, value, eid
                )
                return eid
        except Exception as exc:
            log.warning("calendar_find_by_extended_property failed: %s", exc)
        return None

    def calendar_delete_event(
        self,
        event_id: str,
        calendar_id: str = DEFAULT_CALENDAR_ID,
    ) -> None:
        """
        Delete a calendar event by ID.

        Parameters
        ----------
        event_id    : The event ID to delete
        calendar_id : Calendar containing the event
        """
        svc = self._calendar_client()
        svc.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        log.info("Deleted calendar event %s from calendar %s", event_id, calendar_id)

    def calendar_get_recent_events(
        self,
        minutes_back: int = 5,
        calendar_id: str = DEFAULT_CALENDAR_ID,
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        List calendar events whose *updatedMin* falls within the last N minutes.

        This is the efficient way to scan for recently created/modified events
        without fetching the full calendar.

        Parameters
        ----------
        minutes_back : How many minutes back to look
        calendar_id  : Calendar to query
        max_results  : Maximum events to return

        Returns a list of event resource dicts.
        """
        from datetime import timedelta  # noqa: PLC0415

        svc = self._calendar_client()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes_back)
        updated_min = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        resp = (
            svc.events()
            .list(
                calendarId=calendar_id,
                updatedMin=updated_min,
                maxResults=max_results,
                singleEvents=True,
                orderBy="updated",
            )
            .execute()
        )
        items = resp.get("items", [])
        log.info(
            "calendar_get_recent_events(minutes_back=%d) → %d event(s)",
            minutes_back, len(items),
        )
        return items

    def calendar_schedule_followups(
        self,
        cards: List[Dict[str, Any]],
        calendar_id: str = DEFAULT_CALENDAR_ID,
        start_date: str = "",
        interval_minutes: int = 30,
    ) -> List[str]:
        """
        Create follow-up call events for a list of place-cards.

        One event per card that has a phone number.
        Events start at start_date (default: tomorrow 10:00 IST) and are spaced
        interval_minutes apart.

        Returns list of created event IDs.
        """
        from datetime import datetime, timedelta

        if not start_date:
            tomorrow = datetime.now() + timedelta(days=1)
            start_dt = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        else:
            start_dt = datetime.fromisoformat(start_date)

        event_ids: List[str] = []
        cards_with_phone = [c for c in cards if c.get("phone")]

        for i, card in enumerate(cards_with_phone):
            ev_start = start_dt + timedelta(minutes=i * interval_minutes)
            ev_end   = ev_start + timedelta(minutes=interval_minutes)
            summary  = f"📞 Call: {card.get('name', 'Unknown')}"
            desc_parts = [
                f"Phone: {card.get('phone', '')}",
                f"Category: {card.get('category', '')}",
                f"Address: {card.get('address', '')}",
                f"Rating: {card.get('rating', '')} ({card.get('reviews', '')} reviews)",
                f"Maps: {card.get('maps_url', '')}",
            ]
            desc = "\n".join(p for p in desc_parts if p.split(": ", 1)[-1])
            try:
                eid = self.calendar_create_event(
                    summary=summary,
                    start=ev_start.strftime("%Y-%m-%dT%H:%M:%S"),
                    end=ev_end.strftime("%Y-%m-%dT%H:%M:%S"),
                    description=desc,
                    calendar_id=calendar_id,
                )
                event_ids.append(eid)
            except Exception as exc:
                log.warning("Failed to create event for %s: %s", card.get("name"), exc)

        log.info("Scheduled %d follow-up event(s)", len(event_ids))
        return event_ids

    # ─────────────────────────────────────────────────────────────────────────
    # Google Drive
    # ─────────────────────────────────────────────────────────────────────────

    def drive_upload_json(
        self,
        filename: str,
        data: Any,
        folder_id: Optional[str] = None,
    ) -> str:
        """
        Upload a Python object as a JSON file to Google Drive.
        Returns the file ID.

        Parameters
        ----------
        filename  : e.g. 'leads_pune_20261025.json'
        data      : Any JSON-serialisable object
        folder_id : Optional Drive folder ID to place the file in
        """
        from googleapiclient.http import MediaInMemoryUpload

        svc = self._drive_client()
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        meta: Dict[str, Any] = {"name": filename, "mimeType": "application/json"}
        if folder_id:
            meta["parents"] = [folder_id]

        media = MediaInMemoryUpload(content, mimetype="application/json", resumable=False)
        resp = svc.files().create(body=meta, media_body=media, fields="id,name").execute()
        fid = resp.get("id", "")
        log.info("Uploaded %s to Drive → id=%s", filename, fid)
        return fid

    def drive_list_files(self, page_size: int = 20, query: str = "") -> List[Dict]:
        """List files visible to the service account."""
        svc = self._drive_client()
        params: Dict[str, Any] = {
            "pageSize": page_size,
            "fields": "files(id,name,mimeType,modifiedTime,size)",
        }
        if query:
            params["q"] = query
        resp = svc.files().list(**params).execute()
        return resp.get("files", [])

    # ─────────────────────────────────────────────────────────────────────────
    # Convenience: export a Maps scrape run to all three services at once
    # ─────────────────────────────────────────────────────────────────────────

    def export_maps_run(
        self,
        cards: List[Dict[str, Any]],
        run_name: str = "",
        spreadsheet_id: Optional[str] = None,
        calendar_id: str = DEFAULT_CALENDAR_ID,
        drive_folder_id: Optional[str] = None,
        schedule_followups: bool = True,
        followup_start: str = "",
        create_sheet: bool = True,
    ) -> Dict[str, Any]:
        """
        One-call export of a Maps scrape run:
          1. Write cards to Google Sheets (creates a new sheet if no ID given).
          2. Optionally schedule follow-up call events in Google Calendar.
          3. Upload the raw JSON to Google Drive.

        Returns a summary dict with sheet_id, event_ids, drive_file_id.
        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        name = run_name or f"Maps Leads {ts}"

        result: Dict[str, Any] = {
            "run_name": name,
            "cards_total": len(cards),
            "cards_with_phone": sum(1 for c in cards if c.get("phone")),
            "sheet_id": None,
            "sheet_url": None,
            "event_ids": [],
            "drive_file_id": None,
        }

        # ── 1. Sheets ────────────────────────────────────────────────────────
        try:
            sid = spreadsheet_id
            if not sid and create_sheet:
                sid = self.sheets_create(name)
            if sid:
                self.sheets_write_places(
                    sid, cards, sheet="Sheet1",
                    clear_first=bool(spreadsheet_id),  # clear only if reusing
                    add_header=True,
                )
                result["sheet_id"] = sid
                result["sheet_url"] = f"https://docs.google.com/spreadsheets/d/{sid}"
                log.info("Exported %d cards to Sheets: %s", len(cards), sid)
        except Exception as exc:
            log.warning("Sheets export failed: %s", exc)
            result["sheets_error"] = str(exc)

        # ── 2. Calendar ──────────────────────────────────────────────────────
        if schedule_followups:
            try:
                eids = self.calendar_schedule_followups(
                    cards,
                    calendar_id=calendar_id,
                    start_date=followup_start,
                    interval_minutes=30,
                )
                result["event_ids"] = eids
                log.info("Created %d follow-up events", len(eids))
            except Exception as exc:
                log.warning("Calendar export failed: %s", exc)
                result["calendar_error"] = str(exc)

        # ── 3. Drive ─────────────────────────────────────────────────────────
        try:
            fname = f"{name.replace(' ', '_')}.json"
            drive_data = {
                "run_name": name,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "cards": cards,
            }
            fid = self.drive_upload_json(
                fname, drive_data, folder_id=drive_folder_id
            )
            result["drive_file_id"] = fid
            result["drive_url"] = f"https://drive.google.com/file/d/{fid}/view"
        except Exception as exc:
            log.warning("Drive upload failed: %s", exc)
            result["drive_error"] = str(exc)

        return result
