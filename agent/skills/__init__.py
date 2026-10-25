"""Skill registry for deterministic (non-LLM) agent workflows."""

import os

from .decision import DecisionBuilderSkill, ScrapeDecision
from .pincodes import PincodeSkill, DEFAULT_PINCODE_CSV
from .maps_geo import MapsGeoSkill

__all__ = [
    "DecisionBuilderSkill",
    "ScrapeDecision",
    "PincodeSkill",
    "DEFAULT_PINCODE_CSV",
    "MapsGeoSkill",
    "SkillsPipeline",
]


class SkillsPipeline:
    """
    Run maps/geo scrapes via skills only — no LLM step loop.
    DecisionBuilder → Pincodes → MapsGeo (or dry plan).
    """

    def __init__(
        self,
        page_fetcher=None,
        har_manager=None,
        notify=None,
        pincode_csv: str = DEFAULT_PINCODE_CSV,
    ):
        self.fetcher = page_fetcher
        self.har = har_manager
        self.notify = notify or (lambda *_a, **_k: None)
        self.decision = DecisionBuilderSkill()
        self.pincodes = PincodeSkill(csv_path=pincode_csv)
        self.maps = MapsGeoSkill(
            page_fetcher=page_fetcher,
            har_manager=har_manager,
            notify=self.notify,
        )

    def can_handle(self, goal: str) -> bool:
        return self.decision.can_handle(goal)

    def run(self, goal: str, dry_run: bool = True) -> dict:
        decision = self.decision.build(goal, dry_run=dry_run)
        self.notify("agent_plan", {"tasks": decision.as_plan_tasks(), "decision": decision.to_dict()})

        self.notify(
            "task_progress",
            {
                "label": decision.query[:48] if decision.query else "maps",
                "step": 0,
                "total": 2,
                "phase": "pincodes",
                "cards": 0,
                "phones": 0,
            },
        )
        pin_result = self.pincodes.load_for_decision(decision)
        self.notify(
            "step_observation",
            {
                "step": 1,
                "observation": (
                    f"pincodes: loaded={pin_result.get('total')} "
                    f"filtered={pin_result.get('filtered')} "
                    f"sample={pin_result.get('sample_pins', [])[:5]}"
                ),
            },
        )
        self.notify(
            "task_progress",
            {
                "label": decision.query[:48] if decision.query else "maps",
                "step": 1,
                "total": 2,
                "phase": "maps scrape",
                "cards": 0,
                "phones": 0,
            },
        )

        maps_result = self.maps.execute(decision, pin_result, dry_run=dry_run)
        cards = maps_result.get("cards") or []
        phones = [
            {"name": c.get("name"), "phone": c.get("phone"), "address": c.get("address")}
            for c in cards
            if c.get("phone")
        ]
        scripts = maps_result.get("scripts") or []
        backup_urls = maps_result.get("backup_urls") or []
        stopped = bool(maps_result.get("stopped"))
        stop_reason = maps_result.get("stop_reason") or ""
        extract_path = maps_result.get("extract_path") or ""
        selectors = maps_result.get("selectors") or {}

        summary = (
            f"[{'DRY' if dry_run else 'LIVE'}] query={decision.query!r} "
            f"state={decision.state!r} city={decision.city!r} fields={decision.fields} "
            f"pins={pin_result.get('filtered', 0)} "
            f"searches={len(maps_result.get('planned_urls') or decision.search_urls)} "
            f"backup_pins={len(backup_urls)} "
            f"cards={len(cards)} phones={len(phones)}"
        )
        if scripts:
            summary += " | scripts=" + "→".join(s.split("/")[-1] for s in scripts)
        if selectors.get("name_css") or selectors.get("phone_css"):
            summary += (
                f" | sel name={selectors.get('name_css')!r} "
                f"phone={selectors.get('phone_css')!r}"
            )
        if extract_path:
            summary += f" | wrote={os.path.basename(extract_path)}"
        if stopped:
            summary += f" | STOPPED: {stop_reason}"
        if dry_run:
            summary += " | plan-only (start Chrome for live)"
        if decision.suggested_cron:
            summary += f" | cron_hint={decision.suggested_cron}"

        ok = bool(maps_result.get("ok", True)) and not (stopped and not cards and not dry_run)

        return {
            "ok": ok,
            "mode": "skills",
            "dry_run": dry_run,
            "summary": summary,
            "decision": decision.to_dict(),
            "pincodes": pin_result,
            "maps": maps_result,
            "stopped": stopped,
            "stop_reason": stop_reason or None,
            "extract_path": extract_path or None,
            "extracted": {
                "maps_cards": cards,
                "phones": phones,
                "pincodes_sample": pin_result.get("rows") or [],
                "scripts": scripts,
                "planned_urls": maps_result.get("planned_urls") or [],
                "backup_urls": backup_urls,
                "selectors": selectors,
                "extract_path": extract_path or None,
                "stop_reason": stop_reason or None,
            },
        }
