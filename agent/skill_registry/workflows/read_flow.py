"""Predefined READ workflow: Authenticate -> Resolve -> Disambiguate -> Policy -> Stock/Calculate."""

from __future__ import annotations

from typing import Any, Dict

from agent.skill_registry.context import ExecutionContext
from agent.skill_registry.workflow import WorkflowPipeline, WorkflowStep


def build_read_stock_workflow() -> WorkflowPipeline:
    """Compose the modular READ stock intelligence pipeline."""
    pipe = WorkflowPipeline(name="read_stock_pipeline")

    # Step 1: Resolve Entity (Find product / contact)
    pipe.add_step(
        name="resolve_entity",
        skill_name="resolve_entity",
        inputs_mapper=lambda state, ctx: {"query": state.get("query") or state.get("product_name", ""), "entity_type": "product"},
        on_failure="abort",
    )

    # Step 2: Disambiguate Product
    def map_disambiguation(state: Dict[str, Any], ctx: ExecutionContext) -> Dict[str, Any]:
        entity = state.get("entity") or {}
        raw = entity.get("canonical_name") or state.get("query", "")
        return {
            "raw_name": raw,
            "preferred_strength": state.get("strength"),
            "preferred_form": state.get("form"),
            "preferred_brand": state.get("brand"),
        }

    pipe.add_step(
        name="disambiguate_product",
        skill_name="disambiguate_product",
        inputs_mapper=map_disambiguation,
        on_failure="continue",
    )

    # Step 3: Policy check
    def map_policy(state: Dict[str, Any], ctx: ExecutionContext) -> Dict[str, Any]:
        match = state.get("exact_match") or state.get("entity") or {}
        cid = getattr(ctx.contact, "id", "unverified") if ctx.contact else "unverified"
        return {
            "action": "view_catalog",
            "contact_id": cid,
            "schedule_class": match.get("schedule_class", "OTC"),
        }

    pipe.add_step(
        name="enforce_policy",
        skill_name="enforce_policy",
        inputs_mapper=map_policy,
        on_failure="abort",
    )

    # Step 4: Predict Stockout & Check Usable Stock
    def map_stockout(state: Dict[str, Any], ctx: ExecutionContext) -> Dict[str, Any]:
        match = state.get("exact_match") or state.get("entity") or {}
        pid = match.get("id") or "prod_pcm_500"
        return {"product_id": pid, "daily_burn_rate": 5.0}

    pipe.add_step(
        name="predict_stockout",
        skill_name="predict_stockout",
        inputs_mapper=map_stockout,
        on_failure="continue",
    )

    return pipe
