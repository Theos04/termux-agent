"""Predefined ACTION workflow: Policy -> Consent -> Idempotency -> Dispatch -> Audit."""

from __future__ import annotations

import logging
from typing import Any, Dict

from agent.skill_registry.context import ExecutionContext
from agent.skill_registry.workflow import WorkflowPipeline, WorkflowStep

log = logging.getLogger(__name__)


def build_action_rfq_workflow() -> WorkflowPipeline:
    """Compose the modular ACTION RFQ dispatch pipeline."""
    pipe = WorkflowPipeline(name="action_rfq_pipeline")

    # Step 1: Policy Check
    pipe.add_step(
        name="enforce_policy",
        skill_name="enforce_policy",
        inputs_mapper=lambda state, ctx: {
            "action": "submit_quote",
            "contact_id": getattr(ctx.contact, "id", "system") if ctx.contact else "system",
        },
        on_failure="abort",
    )

    # Step 2: Consent Check
    pipe.add_step(
        name="check_consent",
        skill_name="check_consent",
        inputs_mapper=lambda state, ctx: {
            "contact_id": getattr(ctx.contact, "id", "system") if ctx.contact else "system",
            "purpose": "rfq",
        },
        on_failure="abort",
    )

    # Step 3: Idempotency Check
    pipe.add_step(
        name="enforce_idempotency",
        skill_name="enforce_idempotency",
        inputs_mapper=lambda state, ctx: {
            "idempotency_key": ctx.idempotency_key or f"rfq_{state.get('supplier_id')}_{state.get('product_id')}",
        },
        on_failure="abort",
    )

    # Step 4: Audit Event
    pipe.add_step(
        name="audit_trail_record",
        skill_name="audit_trail_record",
        inputs_mapper=lambda state, ctx: {
            "action": "dispatch_supplier_rfq",
            "resource_type": "rfq",
            "resource_id": state.get("product_id", "rfq"),
            "outcome": "success",
            "metadata": {"supplier": state.get("supplier_name")},
        },
        on_failure="continue",
    )

    return pipe
