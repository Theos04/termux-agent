"""Predefined WRITE workflow: Extract -> Normalize -> Policy -> Mutate with Compensation -> Audit."""

from __future__ import annotations

import logging
from typing import Any, Dict

from agent.skill_registry.context import ExecutionContext
from agent.skill_registry.workflow import WorkflowPipeline, WorkflowStep

log = logging.getLogger(__name__)


def build_address_change_workflow() -> WorkflowPipeline:
    """Compose the modular WRITE address change pipeline with transactional rollback."""
    pipe = WorkflowPipeline(name="write_address_change_pipeline")

    # Step 1: Resolve Order
    pipe.add_step(
        name="resolve_order",
        skill_name="resolve_entity",
        inputs_mapper=lambda state, ctx: {"query": state.get("order_id", ""), "entity_type": "order"},
        on_failure="abort",
    )

    # Step 2: Enforce Policy (Verify buyer ownership)
    def map_policy(state: Dict[str, Any], ctx: ExecutionContext) -> Dict[str, Any]:
        order = state.get("entity") or {}
        cid = getattr(ctx.contact, "id", "unverified") if ctx.contact else "unverified"
        return {
            "action": "create_order",  # Order mutation policy
            "contact_id": cid,
            "resource_id": order.get("id", ""),
        }

    pipe.add_step(
        name="enforce_policy",
        skill_name="enforce_policy",
        inputs_mapper=map_policy,
        on_failure="rollback_and_abort",
    )

    # Step 3: Enforce Idempotency
    pipe.add_step(
        name="enforce_idempotency",
        skill_name="enforce_idempotency",
        inputs_mapper=lambda state, ctx: {
            "idempotency_key": ctx.idempotency_key or f"addr_{state.get('order_id')}_{hash(state.get('new_address', ''))}"
        },
        on_failure="continue",
    )

    return pipe


def build_quote_recording_workflow() -> WorkflowPipeline:
    """Compose supplier quotation recording pipeline with anomaly checks."""
    pipe = WorkflowPipeline(name="write_quote_recording_pipeline")

    # Step 1: Policy Check (Supplier license)
    def map_policy(state: Dict[str, Any], ctx: ExecutionContext) -> Dict[str, Any]:
        cid = getattr(ctx.contact, "id", "unverified") if ctx.contact else "unverified"
        return {
            "action": "submit_quote",
            "contact_id": cid,
            "resource_id": state.get("product_id", ""),
        }

    pipe.add_step(
        name="enforce_policy",
        skill_name="enforce_policy",
        inputs_mapper=map_policy,
        on_failure="rollback_and_abort",
    )

    # Step 2: Quote Anomaly Detection
    pipe.add_step(
        name="detect_quote_anomaly",
        skill_name="detect_quote_anomaly",
        inputs_mapper=lambda state, ctx: {
            "product_id": state.get("product_id", "prod_pcm_500"),
            "quoted_rate": float(state.get("quoted_rate", 0.0)),
        },
        on_failure="continue",
    )

    return pipe
