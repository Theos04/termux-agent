"""Scheduled Maps scrape via skills pipeline (no LLM)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from agent.registry import register_handler


def handle_maps_scrape(payload: dict) -> dict:
    """
    payload:
      goal: str (required)
      dry_run: bool (default False for cron — live when CDP up)
      pincode_csv: optional path
    """
    from agent_bridge import (
        PageFetcher,
        HarManager,
        OrchestratorAgent,
        AgentMemory,
        DEFAULT_PINCODE_CSV,
    )

    goal = (payload.get("goal") or "").strip()
    if not goal:
        raise ValueError("maps_scrape requires payload.goal")

    dry = payload.get("dry_run")
    if dry is None:
        dry = False  # cron jobs default to live attempt

    csv_path = payload.get("pincode_csv") or DEFAULT_PINCODE_CSV
    os.environ.setdefault("PINCODE_CSV", csv_path)

    fetcher = PageFetcher()
    har = HarManager()
    mem = AgentMemory()

    agent = OrchestratorAgent(
        llm_fn=lambda _p: "THOUGHT: cron\nACTION: finish cron stub",
        page_fetcher=fetcher,
        har_manager=har,
        memory=mem,
    )
    summary = agent.run_goal(goal, dry_run=bool(dry))
    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent_runs")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"cron_maps_{stamp}.json")

    cards = (agent.extracted or {}).get("maps_cards") or []
    phones = (agent.extracted or {}).get("phones") or []
    stop_reason = (agent.extracted or {}).get("stop_reason")
    extract_path = (agent.extracted or {}).get("extract_path")
    # Cron run is only "ok" when we persisted meaningful rows (or intentional dry_run)
    meaningful_ok = bool(dry) or bool(cards) or bool(phones)
    result = {
        "ok": meaningful_ok,
        "goal": goal,
        "summary": summary,
        "dry_run": bool(dry),
        "count": len(cards),
        "phone_count": len(phones),
        "stopped": bool(stop_reason),
        "stop_reason": stop_reason,
        "extract_path": extract_path,
        "selectors": (agent.extracted or {}).get("selectors"),
        "extracted": agent.extracted,
        "run_id": agent.run_id,
        "run_path": agent.run_path,
        "saved": out_path,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    if not meaningful_ok:
        # Keep cron artifacts, but surface failure so scheduler can see it
        result["error"] = stop_reason or "no meaningful maps data extracted"
    return result


register_handler("maps_scrape", handle_maps_scrape)
