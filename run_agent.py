#!/usr/bin/env python3
"""CLI entry point for the Chrome automation agent."""

import argparse
import json
import sys
from pathlib import Path

# Ensure chrome-agent root is on sys.path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import handlers.cdp_handlers  # noqa: F401 — register CDP handlers
import handlers.mcp_agent  # noqa: F401 — register MCP agent_act

from agent.agent import Agent
from agent.config import AgentConfig
from api.server import create_app


def cmd_run(args):
    config = AgentConfig()
    agent = Agent(config)
    if args.workers:
        config.worker_count = args.workers

    if args.api:
        agent.start()
        app = create_app(agent)
        print(f"Agent running with {config.worker_count} workers")
        print(f"Monitor: http://{config.api_host}:{config.api_port}/")
        app.run(host=config.api_host, port=config.api_port, threaded=True)
    else:
        print(f"Agent running with {config.worker_count} workers (Ctrl+C to stop)")
        agent.run_forever()


def cmd_submit(args):
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


def cmd_status(args):
    agent = Agent()
    if args.task_id:
        detail = agent.monitor.task_detail(args.task_id)
        print(json.dumps(detail, indent=2, default=str))
    else:
        print(json.dumps(agent.monitor.dashboard(), indent=2, default=str))


def cmd_schedule(args):
    agent = Agent()
    agent.setup()
    payload = json.loads(args.payload) if args.payload else {}
    sid = agent.add_schedule(args.name, args.type, args.cron, payload, args.priority)
    print(json.dumps({"schedule_id": sid, "name": args.name}))


def cmd_failed(args):
    agent = Agent()
    tasks = agent.monitor.failed_tasks(args.limit)
    print(json.dumps(tasks, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description="Chrome automation agent")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Start the agent")
    run_p.add_argument("--workers", type=int, help="Number of workers")
    run_p.add_argument("--api", action="store_true", help="Start monitoring API")
    run_p.set_defaults(func=cmd_run)

    sub_p = sub.add_parser("submit", help="Submit a task")
    sub_p.add_argument("type", help="Task type (fetch_page, launch_chrome, etc.)")
    sub_p.add_argument("--payload", "-p", help="JSON payload")
    sub_p.add_argument("--priority", type=int, default=5, help="Priority (1=highest)")
    sub_p.add_argument("--at", help="Schedule for future (ISO datetime)")
    sub_p.add_argument("--timeout", type=int, help="Timeout in seconds")
    sub_p.set_defaults(func=cmd_submit)

    stat_p = sub.add_parser("status", help="Show dashboard or task detail")
    stat_p.add_argument("--task-id", type=int, help="Specific task ID")
    stat_p.set_defaults(func=cmd_status)

    sched_p = sub.add_parser("schedule", help="Add a cron schedule")
    sched_p.add_argument("name", help="Schedule name")
    sched_p.add_argument("type", help="Task type")
    sched_p.add_argument("cron", help="Cron expression (min hour dom month dow)")
    sched_p.add_argument("--payload", "-p", help="JSON payload")
    sched_p.add_argument("--priority", type=int, default=5)
    sched_p.set_defaults(func=cmd_schedule)

    fail_p = sub.add_parser("failed", help="List failed tasks")
    fail_p.add_argument("--limit", type=int, default=20)
    fail_p.set_defaults(func=cmd_failed)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
