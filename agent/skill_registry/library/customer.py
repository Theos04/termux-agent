"""Customer Intelligence & Lifecycle skills for pharmaceutical trading."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agent.skill_registry.contract import BaseSkill, SideEffect, SkillContract, SkillFamily
from agent.skill_registry.context import ExecutionContext

log = logging.getLogger(__name__)


class CalculateNextBestActionSkill(BaseSkill):
    """Calculates the optimal, permitted next action for a contact based on lifecycle state."""

    contract = SkillContract(
        name="calculate_next_best_action",
        version="1.0.0",
        family=SkillFamily.CUSTOMER_INTELLIGENCE,
        description="Determines the next best business action for a customer or supplier relationship.",
        input_schema={
            "type": "object",
            "required": ["contact_id"],
            "properties": {
                "contact_id": {"type": "string"},
                "current_intent": {"type": ["string", "null"]},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "recommended_action": {"type": "string"},
                "reason": {"type": "string"},
                "action_parameters": {"type": "object"},
            },
        },
        permissions=["customer.read"],
        side_effects=SideEffect.NONE,
        audit_required=False,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        cid = inputs["contact_id"]
        intent = inputs.get("current_intent", "unknown")
        db = context.db

        contact = db.conn.execute("SELECT * FROM contacts WHERE id = ?", (cid,)).fetchone()
        if not contact:
            return {
                "recommended_action": "prompt_onboarding",
                "reason": "Unknown contact number",
                "action_parameters": {"flow": "business_verification"},
            }

        status = contact.get("verification_status", "unverified")
        if status != "verified":
            return {
                "recommended_action": "request_drug_license",
                "reason": "Unverified buyer attempting interaction; wholesale access restricted",
                "action_parameters": {"required_forms": ["Form 20B", "Form 21B", "GSTIN"]},
            }

        roles = db.get_contact_roles(cid)
        role_names = [r["role"] for r in roles]

        if "supplier" in role_names:
            return {
                "recommended_action": "request_updated_rates",
                "reason": "Active supplier; keep catalog quotation rates fresh",
                "action_parameters": {"frequency_days": 7},
            }

        if "retailer" in role_names:
            if intent == "address_change":
                return {
                    "recommended_action": "validate_and_mutate_order",
                    "reason": "Customer requesting order address modification",
                    "action_parameters": {"requires_audit": True},
                }
            if intent == "check_stock":
                return {
                    "recommended_action": "show_inventory_and_suggest_order",
                    "reason": "Customer enquiring about available medicine batches",
                    "action_parameters": {"suggest_moq": True},
                }

            return {
                "recommended_action": "check_reorder_prediction",
                "reason": "Verified retailer with no immediate query",
                "action_parameters": {"check_velocity": True},
            }

        return {
            "recommended_action": "general_greeting",
            "reason": "Default helpful response",
            "action_parameters": {},
        }


class DetectRelationshipDecaySkill(BaseSkill):
    """Detects retail pharmacy accounts whose order frequency has significantly dropped."""

    contract = SkillContract(
        name="detect_relationship_decay",
        version="1.0.0",
        family=SkillFamily.CUSTOMER_INTELLIGENCE,
        description="Identifies dormant retail pharmacy accounts at risk of churn based on order history.",
        input_schema={
            "type": "object",
            "properties": {
                "business_id": {"type": ["string", "null"]},
                "inactivity_days_threshold": {"type": "number", "default": 30.0},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "decay_detected": {"type": "boolean"},
                "days_since_last_order": {"type": "number"},
                "status": {"type": "string"},
                "suggested_reactivation": {"type": "string"},
            },
        },
        permissions=["customer.read"],
        side_effects=SideEffect.NONE,
        audit_required=True,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        biz_id = inputs.get("business_id")
        threshold = float(inputs.get("inactivity_days_threshold", 30.0))
        db = context.db

        order = db.conn.execute(
            """SELECT created_at FROM sales_orders
               WHERE (? IS NULL OR buyer_business_id = ?)
               ORDER BY created_at DESC LIMIT 1""",
            (biz_id, biz_id),
        ).fetchone()

        if not order:
            return {
                "decay_detected": False,
                "days_since_last_order": 999.0,
                "status": "NO_PREVIOUS_ORDERS",
                "suggested_reactivation": "Send initial introductory medicine catalog",
            }

        last_date_str = order["created_at"][:10]
        try:
            last_dt = datetime.strptime(last_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - last_dt).days
        except Exception:
            days = 45

        decay = days >= threshold
        status = "DORMANT" if days >= 60 else ("AT_RISK" if decay else "HEALTHY")
        reactivation = (
            "Send personalized WhatsApp re-engagement message with special scheme rates on top fast-moving SKUs"
            if decay else "Maintain standard service communication"
        )

        return {
            "decay_detected": decay,
            "days_since_last_order": float(days),
            "status": status,
            "suggested_reactivation": reactivation,
        }


class RecoverAbandonedOrderSkill(BaseSkill):
    """Detects stalled or draft sales orders and prepares compliant follow-up prompts."""

    contract = SkillContract(
        name="recover_abandoned_order",
        version="1.0.0",
        family=SkillFamily.CUSTOMER_INTELLIGENCE,
        description="Identifies stalled draft orders and produces consented recovery prompts.",
        input_schema={
            "type": "object",
            "properties": {
                "max_age_hours": {"type": "number", "default": 24.0},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "abandoned_orders": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
        permissions=["order.read"],
        side_effects=SideEffect.NONE,
        audit_required=True,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        db = context.db

        rows = db.conn.execute(
            """SELECT so.*, b.legal_name as buyer_name, c.whatsapp_id as buyer_phone
               FROM sales_orders so
               JOIN businesses b ON so.buyer_business_id = b.id
               LEFT JOIN contact_roles cr ON cr.business_id = b.id AND cr.role = 'retailer'
               LEFT JOIN contacts c ON c.id = cr.contact_id
               WHERE so.status = 'draft'
               ORDER BY so.created_at DESC LIMIT 10"""
        ).fetchall()

        abandoned = []
        for r in rows:
            abandoned.append({
                "order_id": r["id"],
                "buyer_name": r["buyer_name"],
                "buyer_phone": r["buyer_phone"],
                "total_amount": r["total_amount"],
                "created_at": r["created_at"],
                "recommended_prompt": f"Namaste {r['buyer_name']}, your draft order {r['id']} for ₹{r['total_amount']:.2f} is pending confirmation. Reply YES to confirm delivery.",
            })

        return {"abandoned_orders": abandoned, "count": len(abandoned)}
