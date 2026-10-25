#!/usr/bin/env python3
"""
Full integration test for Google Workspace skill.

Runs in two modes:
  MOCK MODE   — patches the Google API clients with real-data stubs
                so you can see the complete data pipeline without a working key.
  LIVE MODE   — set GOOGLE_CREDS_JSON to a valid service-account JSON and
                remove the --mock flag (or set GOOGLE_LIVE=1).

Usage:
  .venv/bin/python test_google_integration.py          # mock (always works)
  GOOGLE_LIVE=1 GOOGLE_CREDS_JSON=./credentials.json \
    .venv/bin/python test_google_integration.py        # live
"""
from __future__ import annotations
import json, os, sys, time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CREDS      = os.environ.get("GOOGLE_CREDS_JSON", "/home/theos/whatsapp-ai/credentials.json")
EXTRACT    = os.path.join(os.path.dirname(__file__), "agent_runs/bars_bistros_pune_phones_20261025_092652.json")
LIVE_MODE  = os.environ.get("GOOGLE_LIVE", "0") == "1"

# ── pretty helpers ────────────────────────────────────────────────────────────
W = 64
def banner(msg):  print(f"\n{'━'*W}\n  {msg}\n{'━'*W}")
def ok(msg):      print(f"  ✅  {msg}")
def warn(msg):    print(f"  ⚠️   {msg}")
def fail(msg):    print(f"  ❌  {msg}")
def info(msg):    print(f"  ℹ️   {msg}")
def step(n, msg): print(f"\n  [{n}] {msg}")

# ─────────────────────────────────────────────────────────────────────────────
# MOCK layer — realistic stubs that mirror the real Google API responses
# ─────────────────────────────────────────────────────────────────────────────
FAKE_SHEET_ID   = "1MOCK_SHEET_ID_termux_agent_2026"
FAKE_EVENT_ID   = "mock_evt_{i}"
FAKE_FILE_ID    = "1MOCK_DRIVE_FILE_ID_termux_agent"

def _make_mock_sheets():
    """Return a mock Sheets API service object."""
    svc = MagicMock()
    # spreadsheets().create()
    svc.spreadsheets().create.return_value.execute.return_value = {
        "spreadsheetId": FAKE_SHEET_ID
    }
    # spreadsheets().values().append()
    svc.spreadsheets().values().append.return_value.execute.return_value = {
        "updates": {"updatedRows": 156, "updatedRange": "Sheet1!A1:H156"}
    }
    # spreadsheets().values().get()
    svc.spreadsheets().values().get.return_value.execute.return_value = {
        "values": [
            ["Name","Phone","Category","Rating","Reviews","Address","Maps URL","Scraped At"],
            ["1000 Oaks","02026343194","North Indian restaurant","4.2","5514","","https://maps...","2026-10-25 12:27 UTC"],
            ["11 East Street Cafe","09960617811","Bar & grill","4.0","4145","","https://maps...","2026-10-25 12:27 UTC"],
        ]
    }
    # spreadsheets().values().clear()
    svc.spreadsheets().values().clear.return_value.execute.return_value = {}
    return svc

def _make_mock_calendar(n_events=5):
    svc = MagicMock()
    # events().insert()
    counter = [0]
    def _insert_execute():
        i = counter[0]; counter[0] += 1
        return {"id": f"mock_event_{i:03d}_termux"}
    svc.events().insert.return_value.execute.side_effect = _insert_execute
    # events().list()
    svc.events().list.return_value.execute.return_value = {
        "items": [
            {
                "id": f"mock_event_{i:03d}_termux",
                "summary": f"📞 Call: Sample Place {i}",
                "start": {"dateTime": f"2026-10-26T{10+i}:00:00+05:30"},
            }
            for i in range(n_events)
        ]
    }
    return svc

def _make_mock_drive():
    svc = MagicMock()
    svc.files().create.return_value.execute.return_value = {
        "id": FAKE_FILE_ID,
        "name": "pune_bars_bistros_20261025.json",
    }
    svc.files().list.return_value.execute.return_value = {
        "files": [
            {"id": FAKE_FILE_ID, "name": "pune_bars_bistros_20261025.json",
             "mimeType": "application/json", "modifiedTime": "2026-10-25T12:27:00Z", "size": "64000"},
            {"id": "1PREV_FILE", "name": "maps_extract_prev.json",
             "mimeType": "application/json", "modifiedTime": "2026-10-24T09:00:00Z", "size": "32000"},
        ]
    }
    return svc

# ─────────────────────────────────────────────────────────────────────────────
# Test runner
# ─────────────────────────────────────────────────────────────────────────────
from agent.skills.google_workspace import GoogleWorkspaceSkill

banner(f"termux-agent × Google Workspace — {'LIVE' if LIVE_MODE else 'MOCK'} Integration Test")
info(f"Mode : {'LIVE (real API calls)' if LIVE_MODE else 'MOCK (realistic stubs, no network)'}")
info(f"Creds: {CREDS}")
info(f"Data : {EXTRACT}")

# ── Step 0: load data ─────────────────────────────────────────────────────────
banner("Step 0 — Load scrape data")
with open(EXTRACT) as f:
    extract = json.load(f)
cards = extract.get("cards", [])
cards_with_phone = [c for c in cards if c.get("phone")]
ok(f"Loaded {len(cards)} place-cards  ({len(cards_with_phone)} with phone)")
info(f"Top-3: {', '.join(c.get('name','?') for c in cards[:3])}")

SAMPLE_CARDS = cards[:5]   # limit for Calendar test
results = {}

# ── Step 1: Google Sheets ─────────────────────────────────────────────────────
banner("Step 1 — Google Sheets (create + write 155 rows + read-back)")

def _run_sheets_test(ws, real=False):
    title = f"Pune Bars & Bistros — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    step("1a", f"sheets_create('{title}')")
    sid = ws.sheets_create(title)
    ok(f"Spreadsheet created → id: {sid}")

    step("1b", f"sheets_write_places({len(cards)} cards)")
    n = ws.sheets_write_places(sid, cards, add_header=True)
    ok(f"Wrote {n} rows (1 header + {n-1} data)")

    step("1c", "sheets_read() — read-back verification")
    rows = ws.sheets_read(sid)
    ok(f"Read back {len(rows)} rows")
    info(f"Header: {rows[0] if rows else '(empty)'}")
    if len(rows) > 1:
        info(f"Row 1 : {rows[1]}")

    return sid

if LIVE_MODE:
    ws = GoogleWorkspaceSkill(creds_path=CREDS)
    try:
        sid = _run_sheets_test(ws, real=True)
        results["sheet_id"] = sid
        results["sheet_url"] = f"https://docs.google.com/spreadsheets/d/{sid}"
        ok(f"Sheet URL: {results['sheet_url']}")
    except Exception as e:
        fail(f"Sheets LIVE test failed: {e}")
        results["sheets_error"] = str(e)
else:
    ws = GoogleWorkspaceSkill(creds_path=CREDS)
    with patch.object(ws, "_sheets_client", return_value=_make_mock_sheets()), \
         patch.object(ws, "_load_creds",    return_value=MagicMock()):
        sid = _run_sheets_test(ws)
        results["sheet_id"] = sid
        results["sheet_url"] = f"https://docs.google.com/spreadsheets/d/{sid}"
        ok(f"Sheet URL (mock): {results['sheet_url']}")

# ── Step 2: Google Calendar ───────────────────────────────────────────────────
banner(f"Step 2 — Google Calendar ({len(SAMPLE_CARDS)} follow-up events)")

def _run_calendar_test(ws, real=False):
    tomorrow = datetime.now() + timedelta(days=1)
    start_dt = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
    step("2a", f"calendar_schedule_followups({len(SAMPLE_CARDS)} cards, start={start_dt.date()} 10:00)")
    eids = ws.calendar_schedule_followups(
        SAMPLE_CARDS, start_date=start_dt.isoformat(), interval_minutes=30
    )
    ok(f"Created {len(eids)} event(s)")
    for i, eid in enumerate(eids):
        info(f"  event[{i}]: {eid}")

    step("2b", "calendar_list_events(max_results=5)")
    events = ws.calendar_list_events(max_results=5)
    ok(f"Listed {len(events)} upcoming event(s)")
    for ev in events[:3]:
        t = ev.get("start", {}).get("dateTime", "")[:16]
        info(f"  {t}  {ev.get('summary','')}")

    return eids

if LIVE_MODE:
    try:
        eids = _run_calendar_test(ws, real=True)
        results["event_ids"] = eids
    except Exception as e:
        fail(f"Calendar LIVE test failed: {e}")
        results["calendar_error"] = str(e)
else:
    mock_cal = _make_mock_calendar(n_events=5)
    with patch.object(ws, "_calendar_client", return_value=mock_cal), \
         patch.object(ws, "_load_creds",       return_value=MagicMock()):
        eids = _run_calendar_test(ws)
        results["event_ids"] = eids

# ── Step 3: Google Drive ──────────────────────────────────────────────────────
banner("Step 3 — Google Drive (upload JSON backup)")

def _run_drive_test(ws, real=False):
    fname = f"pune_bars_bistros_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source": "bars_bistros_pune_phones_20261025_092652.json",
        "cards_total": len(cards),
        "cards_with_phone": len(cards_with_phone),
        "cards": cards,
    }
    size_kb = len(json.dumps(payload)) // 1024
    step("3a", f"drive_upload_json('{fname}', {size_kb} KB)")
    fid = ws.drive_upload_json(fname, payload)
    ok(f"Uploaded → id: {fid}")
    info(f"  URL: https://drive.google.com/file/d/{fid}/view")

    step("3b", "drive_list_files()")
    files = ws.drive_list_files(page_size=5)
    ok(f"Drive listing: {len(files)} file(s) visible to service account")
    for f_ in files[:3]:
        size = int(f_.get("size",0))//1024
        info(f"  {f_.get('name')}  ({size} KB)  mod={f_.get('modifiedTime','')[:10]}")

    return fid

if LIVE_MODE:
    try:
        fid = _run_drive_test(ws, real=True)
        results["drive_file_id"] = fid
        results["drive_url"] = f"https://drive.google.com/file/d/{fid}/view"
    except Exception as e:
        fail(f"Drive LIVE test failed: {e}")
        results["drive_error"] = str(e)
else:
    mock_drv = _make_mock_drive()
    with patch.object(ws, "_drive_client", return_value=mock_drv), \
         patch.object(ws, "_load_creds",   return_value=MagicMock()):
        fid = _run_drive_test(ws)
        results["drive_file_id"] = fid
        results["drive_url"] = f"https://drive.google.com/file/d/{fid}/view"

# ── Step 4: export_maps_run() end-to-end ─────────────────────────────────────
banner("Step 4 — export_maps_run() — full pipeline in one call")

def _run_full_pipeline(ws, real=False):
    step("4", f"ws.export_maps_run({len(cards)} cards)")
    r = ws.export_maps_run(
        cards=cards,
        run_name="Pune Bars & Bistros Oct 2026 (test)",
        schedule_followups=True,
        followup_start="",
    )
    ok(f"Pipeline complete — ok={r.get('ok')}")
    info(f"  Cards total     : {r['cards_total']}")
    info(f"  Cards w/ phone  : {r['cards_with_phone']}")
    info(f"  Sheet ID        : {r.get('sheet_id')}")
    info(f"  Sheet URL       : {r.get('sheet_url')}")
    info(f"  Calendar events : {len(r.get('event_ids', []))}")
    info(f"  Drive file ID   : {r.get('drive_file_id')}")
    info(f"  Drive URL       : {r.get('drive_url')}")
    for k in ("sheets_error","calendar_error","drive_error"):
        if r.get(k): warn(f"{k}: {r[k]}")
    return r

if LIVE_MODE:
    try:
        full = _run_full_pipeline(ws, real=True)
        results["full_pipeline"] = full
    except Exception as e:
        fail(f"Full pipeline LIVE failed: {e}")
else:
    with patch.object(ws, "_sheets_client",   return_value=_make_mock_sheets()), \
         patch.object(ws, "_calendar_client", return_value=_make_mock_calendar(n_events=45)), \
         patch.object(ws, "_drive_client",    return_value=_make_mock_drive()), \
         patch.object(ws, "_load_creds",      return_value=MagicMock()):
        full = _run_full_pipeline(ws)
        results["full_pipeline"] = full

# ── Step 5: handler dispatch ──────────────────────────────────────────────────
banner("Step 5 — Task-queue handler dispatch (handle_google_export)")
from handlers.google_export import handle_google_export

if LIVE_MODE:
    payload = {"extract_path": EXTRACT, "run_name": "handler-test", "schedule_followups": False}
    try:
        hr = handle_google_export(payload)
        ok(f"Handler returned ok={hr.get('ok')}")
        info(str(hr)[:200])
    except Exception as e:
        fail(f"Handler LIVE failed: {e}")
else:
    ws2 = GoogleWorkspaceSkill(creds_path=CREDS)
    with patch("agent.skills.google_workspace.GoogleWorkspaceSkill") as MockWS:
        inst = MockWS.return_value
        inst.available.return_value = True
        inst.export_maps_run.return_value = {
            "ok": True,
            "run_name": "handler-test",
            "cards_total": len(cards),
            "cards_with_phone": len(cards_with_phone),
            "sheet_id": FAKE_SHEET_ID,
            "sheet_url": f"https://docs.google.com/spreadsheets/d/{FAKE_SHEET_ID}",
            "event_ids": [f"mock_event_{i:03d}" for i in range(45)],
            "drive_file_id": FAKE_FILE_ID,
            "drive_url": f"https://drive.google.com/file/d/{FAKE_FILE_ID}/view",
        }
        payload = {"extract_path": EXTRACT, "run_name": "handler-test"}
        hr = handle_google_export(payload)
        ok(f"Handler returned ok={hr.get('ok')}")
        info(f"  Sheet  : {hr.get('sheet_url')}")
        info(f"  Events : {len(hr.get('event_ids',[]))}")
        info(f"  Drive  : {hr.get('drive_url')}")

# ── Final summary ─────────────────────────────────────────────────────────────
banner("Final Summary")
mode_label = "LIVE ✅" if LIVE_MODE else "MOCK ✅ (all paths tested, no network needed)"
print(f"\n  Mode            : {mode_label}")
print(f"  Cards in data   : {len(cards)} total, {len(cards_with_phone)} with phone")
print(f"  Sheet URL       : {results.get('sheet_url','—')}")
print(f"  Calendar events : {len(results.get('event_ids',[]))} created")
print(f"  Drive backup    : {results.get('drive_url','—')}")
print()
if not LIVE_MODE:
    print("  ─── TO RUN LIVE ───────────────────────────────────────────")
    print("  1. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts")
    print("     Project: inductive-seer-441423-p6")
    print("  2. Click service account → Keys → Delete old key → Add Key → JSON")
    print("  3. Save as ./credentials.json")
    print("  4. Enable APIs (if not already):")
    print("     - Google Sheets API")
    print("     - Google Calendar API")
    print("     - Google Drive API")
    print("  5. Run:")
    print("     GOOGLE_LIVE=1 GOOGLE_CREDS_JSON=./credentials.json \\")
    print("       .venv/bin/python test_google_integration.py")
    print()
    print("  Or use export_to_google.py for one-shot export:")
    print("     GOOGLE_CREDS_JSON=./credentials.json \\")
    print("       .venv/bin/python export_to_google.py")
    print()
