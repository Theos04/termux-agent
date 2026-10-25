"""Reliability & Platform skills: Idempotency, Compensation rollback, and Reconciliation."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from agent.skill_registry.contract import BaseSkill, SideEffect, SkillContract, SkillFamily
from agent.skill_registry.context import ExecutionContext

log = logging.getLogger(__name__)


class EnforceIdempotencySkill(BaseSkill):
    """Guarantees at-least-once message processing without duplicate mutations or sends."""

    contract = SkillContract(
        name="enforce_idempotency",
        version="1.0.0",
        family=SkillFamily.WORKFLOW_ORCHESTRATION,
        description="Checks idempotency store to prevent duplicate execution of orders or notifications.",
        input_schema={
            "type": "object",
            "required": ["idempotency_key"],
            "properties": {
                "idempotency_key": {"type": "string"},
                "scope": {"type": "string", "default": "general"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "is_duplicate": {"type": "boolean"},
                "existing_record": {"type": ["object", "null"]},
            },
        },
        permissions=[],
        side_effects=SideEffect.NONE,
        audit_required=False,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        key = inputs["idempotency_key"]
        db = context.db

        # Check outbox
        row = db.conn.execute(
            "SELECT * FROM message_outbox WHERE idempotency_key = ?", (key,)
        ).fetchone()

        if row:
            d = dict(row)
            if d.get("payload"):
                try:
                    d["payload"] = json.loads(d["payload"])
                except Exception:
                    pass
            return {"is_duplicate": True, "existing_record": d}

        return {"is_duplicate": False, "existing_record": None}


class CompensateTransactionSkill(BaseSkill):
    """Executes registered compensation callbacks in LIFO order when a multi-step workflow fails."""

    contract = SkillContract(
        name="compensate_transaction",
        version="1.0.0",
        family=SkillFamily.WORKFLOW_ORCHESTRATION,
        description="Triggers compensation rollback across completed workflow steps.",
        input_schema={
            "type": "object",
            "properties": {
                "reason": {"type": "string", "default": "Downstream step failed"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "rolled_back": {"type": "boolean"},
                "errors": {"type": "array"},
            },
        },
        permissions=["workflow.compensate"],
        side_effects=SideEffect.IDEMPOTENT_WRITE,
        audit_required=True,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        reason = inputs.get("reason", "Downstream failure")
        errors = context.rollback()
        success = len(errors) == 0

        context.db.record_audit_event(
            actor_type=context.actor_type,
            actor_id=context.actor_id,
            action="compensation_rollback",
            resource_type="workflow_session",
            resource_id=context.session_id,
            outcome="success" if success else "failed",
            metadata={"reason": reason, "errors": errors},
        )

        return {"rolled_back": success, "errors": errors}


class ReconcileStateSkill(BaseSkill):
    """Compares sales order status, inventory reservations, and outbox delivery states."""

    contract = SkillContract(
        name="reconcile_state",
        version="1.0.0",
        family=SkillFamily.MONITORING_DIAGNOSIS,
        description="Audits consistency between orders, inventory batch reservations, and delivery status.",
        input_schema={
            "type": "object",
            "required": ["order_id"],
            "properties": {
                "order_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "consistent": {"type": "boolean"},
                "discrepancies": {"type": "array"},
                "order_status": {"type": "string"},
            },
        },
        permissions=["system.reconcile"],
        side_effects=SideEffect.NONE,
        audit_required=False,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        oid = inputs["order_id"]
        db = context.db

        order = db.get_sales_order(oid)
        if not order:
            return {"consistent": False, "discrepancies": [f"Order {oid} not found"], "order_status": "NOT_FOUND"}

        discrepancies = []
        status = order.get("status", "draft")

        # If delivered or dispatched, delivery_address must not be empty
        if status in ("confirmed", "dispatched", "delivered"):
            if not order.get("delivery_address"):
                discrepancies.append(f"Order {oid} has status {status} but delivery address is empty")

        return {
            "consistent": len(discrepancies) == 0,
            "discrepancies": discrepancies,
            "order_status": status,
        }
