#!/usr/bin/env python3
"""CLI entry point for the Chrome automation agent.

Usage
-----
  python run_agent.py run --api           # FastAPI + workers
  python run_agent.py run --api --port 9227
  python run_agent.py submit browser_navigate --payload '{"url":"https://example.com"}'
  python run_agent.py status
  python run_agent.py status --task-id 42
  python run_agent.py schedule daily_maps maps_scrape "0 9 * * *"
  python run_agent.py failed --limit 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import handlers.cdp_handlers   # noqa: F401 — register CDP handlers
import handlers.mcp_agent      # noqa: F401 — register MCP agent_act
import handlers.maps_scrape    # noqa: F401 — Maps skills cron handler
import handlers.whatsapp_handler  # noqa: F401 — register WhatsApp handlers

from agent.agent import Agent
from agent.config import AgentConfig


# ──────────────────────────────────────────────────────────────────────────────
# Sub-commands
# ──────────────────────────────────────────────────────────────────────────────


def cmd_run(args) -> None:
    config = AgentConfig()
    if args.workers:
        config.worker_count = args.workers
    if args.port:
        config.api_port = args.port
    if args.host:
        config.api_host = args.host

    agent = Agent(config)

    if args.api:
        import uvicorn  # noqa: PLC0415

        from api.server import create_app  # noqa: PLC0415

        app = create_app(agent)

        print(f"[agent] Workers: {config.worker_count}")
        print(f"[agent] Monitor: http://{config.api_host}:{config.api_port}/")
        print(f"[agent] WS stream: ws://{config.api_host}:{config.api_port}/ws/agent")

        uvicorn.run(
            app,
            host=config.api_host,
            port=config.api_port,
            log_level="info",
        )
    else:
        print(f"[agent] Running with {config.worker_count} workers (Ctrl+C to stop)")
        agent.run_forever()


def cmd_submit(args) -> None:
    agent = Agent()
    payload = json.loads(args.payload) if args.payload else {}
    task_id = agent.submit(
        task_type=args.type,
        payload=payload,
        priority=args.priority,
        scheduled_at=args.at,
        timeout_seconds=args.timeout,
    )
    agent.setup()
    print(json.dumps({"task_id": task_id}))


def cmd_status(args) -> None:
    agent = Agent()
    if args.task_id:
        detail = agent.monitor.task_detail(args.task_id)
        print(json.dumps(detail, indent=2, default=str))
    else:
        print(json.dumps(agent.monitor.dashboard(), indent=2, default=str))


def cmd_schedule(args) -> None:
    agent = Agent()
    agent.setup()
    payload = json.loads(args.payload) if args.payload else {}
    sid = agent.add_schedule(args.name, args.type, args.cron, payload, args.priority)
    print(json.dumps({"schedule_id": sid, "name": args.name}))


def cmd_failed(args) -> None:
    agent = Agent()
    tasks = agent.monitor.failed_tasks(args.limit)
    print(json.dumps(tasks, indent=2, default=str))


def cmd_gcal_sync(args) -> None:
    """Push all agent schedules to Google Calendar."""
    agent = Agent()
    agent.setup()
    try:
        from agent.skills.gcal_scheduler import GCalScheduler  # noqa: PLC0415
    except ImportError as exc:
        print(json.dumps({"ok": False, "error": f"gcal_scheduler not available: {exc}"}))
        return

    gcal = GCalScheduler(agent)
    if not gcal.available():
        print(json.dumps({
            "ok": False,
            "error": "Google credentials not available. Set GOOGLE_CREDS_JSON=",
        }))
        return

    schedules = agent.scheduler.list_schedules()
    result = gcal.sync_schedules_to_calendar(schedules)
    result["ok"] = result.get("failed", 0) == 0
    print(json.dumps(result, indent=2, default=str))


def cmd_gcal_poll(args) -> None:
    """Poll Google Calendar once for incoming agent commands."""
    agent = Agent()
    agent.setup()
    try:
        from agent.skills.gcal_scheduler import GCalScheduler  # noqa: PLC0415
    except ImportError as exc:
        print(json.dumps({"ok": False, "error": f"gcal_scheduler not available: {exc}"}))
        return

    since = getattr(args, "since_minutes", 5)
    gcal = GCalScheduler(agent)
    if not gcal.available():
        print(json.dumps({
            "ok": False,
            "error": "Google credentials not available. Set GOOGLE_CREDS_JSON=",
        }))
        return

    commands = gcal.poll_calendar_commands(since_minutes=since)
    print(json.dumps({"ok": True, "commands_processed": len(commands), "commands": commands}, indent=2, default=str))


def cmd_gcal_status(args) -> None:
    """Show GCal poller/integration status."""
    try:
        from handlers.gcal_sync import GCalPoller  # noqa: PLC0415
        from agent.skills.gcal_scheduler import GCalScheduler  # noqa: PLC0415
    except ImportError as exc:
        print(json.dumps({"ok": False, "error": f"GCal integration not available: {exc}"}))
        return

    agent = Agent()
    gcal = GCalScheduler(agent)
    status = {
        "available": gcal.available(),
        "poller_class": "GCalPoller",
        "poll_interval_env": "GCAL_POLL_INTERVAL",
        "sync_on_change_env": "GCAL_SYNC_ON_CHANGE",
        "calendar_id": gcal._calendar_id,
        "command_calendar_id": gcal._command_calendar_id,
    }
    print(json.dumps(status, indent=2, default=str))


def cmd_whatsapp_status(args) -> None:
    """Show WhatsApp CDP connection and login status."""
    from agent.whatsapp import WhatsAppCDPClient  # noqa: PLC0415
    cfg = AgentConfig()
    port = args.port or cfg.whatsapp_cdp_port
    cdp = WhatsAppCDPClient(port=port)
    print(json.dumps(cdp.get_status(), indent=2, default=str))


def cmd_whatsapp_launch(args) -> None:
    """Launch isolated Chrome session for WhatsApp Web."""
    from agent.whatsapp import WhatsAppCDPClient  # noqa: PLC0415
    cfg = AgentConfig()
    port = args.port or cfg.whatsapp_cdp_port
    cdp = WhatsAppCDPClient(port=port)
    print(json.dumps(cdp.launch_browser(headless=args.headless), indent=2, default=str))


def cmd_whatsapp_dispatch(args) -> None:
    """Dispatch a message through the READ -> WRITE -> ACTION -> ResponseComposer pipeline."""
    from agent.whatsapp import WhatsAppCDPClient, WhatsAppRouter  # noqa: PLC0415
    cfg = AgentConfig()
    port = args.port or cfg.whatsapp_cdp_port
    agent = Agent()
    cdp = WhatsAppCDPClient(port=port, mock_mode=args.mock)
    router = WhatsAppRouter(agent.db, cdp)
    res = router.dispatch(sender_phone=args.phone, message_text=args.message)
    print(json.dumps({
        "ok": res.ok,
        "intent": res.intent.value,
        "response": res.response_text,
        "action_taken": res.action_taken,
        "trace": res.execution_trace,
        "details": res.details,
    }, indent=2, default=str))


def cmd_whatsapp_send(args) -> None:
    """Send an outbound message via WhatsApp CDP."""
    from agent.whatsapp import WhatsAppCDPClient, WhatsAppRouter  # noqa: PLC0415
    cfg = AgentConfig()
    port = args.port or cfg.whatsapp_cdp_port
    agent = Agent()
    cdp = WhatsAppCDPClient(port=port, mock_mode=args.mock)
    router = WhatsAppRouter(agent.db, cdp)
    res = router.action.send_whatsapp_message(recipient_phone=args.phone, text=args.message)
    print(json.dumps(res, indent=2, default=str))


def cmd_whatsapp_sync(args) -> None:
    """Sync catalog and contacts from Google Sheets."""
    from agent.whatsapp.google_sheet_sync import GoogleSheetPharmacySync  # noqa: PLC0415
    agent = Agent()
    sync = GoogleSheetPharmacySync(agent.db)
    res = sync.sync_all(product_limit=args.products, party_limit=args.parties)
    print(json.dumps(res, indent=2, default=str))



# ──────────────────────────────────────────────────────────────────────────────
# Argument parser
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Termux CDP Agent — FastAPI + WebSocket + LLM planner"
    )
    sub = parser.add_subparsers(dest="command")

    # run
    run_p = sub.add_parser("run", help="Start the agent")
    run_p.add_argument("--workers", type=int, help="Number of workers")
    run_p.add_argument(
        "--api", action="store_true", help="Start FastAPI monitoring server"
    )
    run_p.add_argument("--host", default=None, help="API bind host")
    run_p.add_argument("--port", type=int, default=None, help="API bind port")
    run_p.set_defaults(func=cmd_run)

    # submit
    sub_p = sub.add_parser("submit", help="Submit a task")
    sub_p.add_argument("type", help="Task type")
    sub_p.add_argument("--payload", "-p", help="JSON payload")
    sub_p.add_argument("--priority", type=int, default=5)
    sub_p.add_argument("--at", help="Schedule for future (ISO datetime)")
    sub_p.add_argument("--timeout", type=int)
    sub_p.set_defaults(func=cmd_submit)

    # status
    stat_p = sub.add_parser("status", help="Show dashboard or task detail")
    stat_p.add_argument("--task-id", type=int)
    stat_p.set_defaults(func=cmd_status)

    # schedule
    sched_p = sub.add_parser("schedule", help="Add a cron schedule")
    sched_p.add_argument("name")
    sched_p.add_argument("type")
    sched_p.add_argument("cron")
    sched_p.add_argument("--payload", "-p")
    sched_p.add_argument("--priority", type=int, default=5)
    sched_p.set_defaults(func=cmd_schedule)

    # failed
    fail_p = sub.add_parser("failed", help="List failed tasks")
    fail_p.add_argument("--limit", type=int, default=20)
    fail_p.set_defaults(func=cmd_failed)

    # gcal-sync
    gcal_sync_p = sub.add_parser("gcal-sync", help="Push all schedules to Google Calendar")
    gcal_sync_p.set_defaults(func=cmd_gcal_sync)

    # gcal-poll
    gcal_poll_p = sub.add_parser("gcal-poll", help="Poll Google Calendar once for commands")
    gcal_poll_p.add_argument(
        "--since-minutes", type=int, default=5, dest="since_minutes",
        help="How many minutes back to look for events (default: 5)",
    )
    gcal_poll_p.set_defaults(func=cmd_gcal_poll)

    # gcal-status
    gcal_stat_p = sub.add_parser("gcal-status", help="Show GCal integration status")
    gcal_stat_p.set_defaults(func=cmd_gcal_status)

    # whatsapp-status
    wa_stat_p = sub.add_parser("whatsapp-status", help="Show WhatsApp CDP browser/login status")
    wa_stat_p.add_argument("--port", type=int, default=None)
    wa_stat_p.set_defaults(func=cmd_whatsapp_status)

    # whatsapp-launch
    wa_launch_p = sub.add_parser("whatsapp-launch", help="Launch isolated Chrome on WhatsApp CDP port")
    wa_launch_p.add_argument("--port", type=int, default=None)
    wa_launch_p.add_argument("--headless", action="store_true", default=None)
    wa_launch_p.set_defaults(func=cmd_whatsapp_launch)

    # whatsapp-dispatch
    wa_disp_p = sub.add_parser("whatsapp-dispatch", help="Run message through the Trio Router pipeline")
    wa_disp_p.add_argument("--phone", required=True, help="Sender phone number (e.g. +919876543210)")
    wa_disp_p.add_argument("--message", "-m", required=True, help="Incoming message text")
    wa_disp_p.add_argument("--port", type=int, default=None)
    wa_disp_p.add_argument("--mock", action="store_true")
    wa_disp_p.set_defaults(func=cmd_whatsapp_dispatch)

    # whatsapp-send
    wa_send_p = sub.add_parser("whatsapp-send", help="Send outbound WhatsApp message via CDP")
    wa_send_p.add_argument("--phone", required=True, help="Recipient phone number")
    wa_send_p.add_argument("--message", "-m", required=True, help="Message text to send")
    wa_send_p.add_argument("--port", type=int, default=None)
    wa_send_p.add_argument("--mock", action="store_true")
    wa_send_p.set_defaults(func=cmd_whatsapp_send)

    # whatsapp-sync
    wa_sync_p = sub.add_parser("whatsapp-sync", help="Sync products and contacts from Google Sheets")
    wa_sync_p.add_argument("--products", type=int, default=1000, help="Max products to sync")
    wa_sync_p.add_argument("--parties", type=int, default=500, help="Max retailers to sync")
    wa_sync_p.set_defaults(func=cmd_whatsapp_sync)


    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
