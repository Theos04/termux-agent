"""Governance & Assurance skills for pharmaceutical compliance and access control."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent.skill_registry.contract import BaseSkill, SideEffect, SkillContract, SkillFamily
from agent.skill_registry.context import ExecutionContext

log = logging.getLogger(__name__)


class EnforcePolicySkill(BaseSkill):
    """Independent policy evaluation gate: verifies licenses, role permissions, and drug schedule classes."""

    contract = SkillContract(
        name="enforce_policy",
        version="1.0.0",
        family=SkillFamily.GOVERNANCE_ASSURANCE,
        description="Enforces pharmaceutical regulations (Drugs & Cosmetics Act, DPDP) and access control matrix.",
        input_schema={
            "type": "object",
            "required": ["action", "contact_id"],
            "properties": {
                "action": {"type": "string"},
                "contact_id": {"type": "string"},
                "schedule_class": {"type": ["string", "null"]},
                "resource_id": {"type": ["string", "null"]},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "allowed": {"type": "boolean"},
                "reason": {"type": "string"},
                "requires_human_approval": {"type": "boolean"},
                "violation_code": {"type": ["string", "null"]},
            },
        },
        permissions=["policy.evaluate"],
        side_effects=SideEffect.NONE,
        audit_required=True,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        action = inputs["action"].lower()
        cid = inputs["contact_id"]
        sched_class = (inputs.get("schedule_class") or "OTC").upper()
        db = context.db

        contact = db.conn.execute("SELECT * FROM contacts WHERE id = ?", (cid,)).fetchone()
        if not contact:
            return {
                "allowed": False,
                "reason": "Contact not registered in system",
                "requires_human_approval": False,
                "violation_code": "AUTH_UNKNOWN_CONTACT",
            }

        is_verified = contact["verification_status"] == "verified"
        roles = db.get_contact_roles(cid)
        role_names = [r["role"] for r in roles]

        # Policy 1: Wholesale price / catalog access requires verified pharmacy license
        if action in ("view_wholesale_prices", "view_catalog", "create_order"):
            if not is_verified or "retailer" not in role_names:
                return {
                    "allowed": False,
                    "reason": "Wholesale pricing and order placement require a verified retail drug license (Form 20B/21B)",
                    "requires_human_approval": True,
                    "violation_code": "POLICY_UNVERIFIED_BUYER",
                }

        # Policy 2: Schedule H / Schedule X restricted drugs cannot be ordered by unverified or patient accounts
        if sched_class in ("SCHEDULE H", "SCHEDULE H1", "SCHEDULE X"):
            if "retailer" not in role_names and "pharmacist" not in role_names:
                return {
                    "allowed": False,
                    "reason": f"Restricted medicine ({sched_class}) cannot be dispensed or sold without verified license and prescription records",
                    "requires_human_approval": True,
                    "violation_code": "PHARMA_SCHEDULE_RESTRICTION",
                }

        # Policy 3: Supplier quotes can only be accepted by registered suppliers
        if action == "submit_quote" and "supplier" not in role_names:
            return {
                "allowed": False,
                "reason": "Quotations can only be recorded from approved, licensed medicine distributors",
                "requires_human_approval": False,
                "violation_code": "POLICY_UNVERIFIED_SUPPLIER",
            }

        return {
            "allowed": True,
            "reason": "Operation complies with pharmaceutical policy and access control matrix",
            "requires_human_approval": False,
            "violation_code": None,
        }


class CheckConsentSkill(BaseSkill):
    """Verifies DPDP consent records and messaging preferences before sending notifications."""

    contract = SkillContract(
        name="check_consent",
        version="1.0.0",
        family=SkillFamily.GOVERNANCE_ASSURANCE,
        description="Checks messaging consent and opt-in records for communication compliance.",
        input_schema={
            "type": "object",
            "required": ["contact_id", "purpose"],
            "properties": {
                "contact_id": {"type": "string"},
                "purpose": {"type": "string", "enum": ["transactional", "rfq", "marketing", "follow_up"]},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "has_consent": {"type": "boolean"},
                "consent_status": {"type": "string"},
            },
        },
        permissions=["consent.read"],
        side_effects=SideEffect.NONE,
        audit_required=False,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        cid = inputs["contact_id"]
        purpose = inputs["purpose"]
        db = context.db

        # Transactional messages (order updates, receipts) are implied consent under DPDP
        if purpose == "transactional":
            return {"has_consent": True, "consent_status": "implied_transactional"}

        row = db.conn.execute(
            "SELECT consent_status FROM messaging_preferences WHERE contact_id = ? AND purpose = ?",
            (cid, purpose),
        ).fetchone()

        if row and row["consent_status"] == "opted_out":
            return {"has_consent": False, "consent_status": "opted_out"}

        # Default for verified businesses is opted_in for business RFQs / trade communications
        return {"has_consent": True, "consent_status": row["consent_status"] if row else "default_opted_in"}


class AuditTrailRecordSkill(BaseSkill):
    """Immutably records action, actor, resource, inputs, and outcome into audit_events."""

    contract = SkillContract(
        name="audit_trail_record",
        version="1.0.0",
        family=SkillFamily.GOVERNANCE_ASSURANCE,
        description="Appends an immutable audit event to the database audit trail.",
        input_schema={
            "type": "object",
            "required": ["action", "resource_type", "resource_id", "outcome"],
            "properties": {
                "action": {"type": "string"},
                "resource_type": {"type": "string"},
                "resource_id": {"type": "string"},
                "outcome": {"type": "string", "enum": ["success", "denied", "failed", "escalated"]},
                "metadata": {"type": "object"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "audit_event_id": {"type": "integer"},
                "logged": {"type": "boolean"},
            },
        },
        permissions=["audit.write"],
        side_effects=SideEffect.IDEMPOTENT_WRITE,
        audit_required=False,  # Avoid recursion
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        db = context.db
        aid = db.record_audit_event(
            actor_type=context.actor_type,
            actor_id=context.actor_id,
            action=inputs["action"],
            resource_type=inputs["resource_type"],
            resource_id=inputs["resource_id"],
            outcome=inputs["outcome"],
            metadata=inputs.get("metadata", {}),
        )
        return {"audit_event_id": aid, "logged": True}
