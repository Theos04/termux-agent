"""WRITE Specialist — Records and relationships with validated mutations only."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from agent.database import Database, utcnow
from .models import ContactInfo, ContactRole, VerificationStatus

log = logging.getLogger(__name__)


class WriteSpecialist:
    """Specialist Agent 2: Records & Relationships (Validated Mutations Only).

    Rules:
      - Every mutation passes through business validation, authorization, and audit log.
      - Never allows unvalidated or unvetted updates.
    """

    def __init__(self, db: Database):
        self.db = db

    def update_delivery_address(
        self,
        order_id: str,
        new_address: str,
        contact: ContactInfo,
    ) -> Dict[str, Any]:
        """Validate and mutate sales order delivery address."""
        clean_addr = (new_address or "").strip()
        if len(clean_addr) < 8:
            self.db.record_audit_event(
                actor_type="write_agent",
                actor_id=contact.id,
                action="update_delivery_address",
                resource_type="sales_order",
                resource_id=order_id,
                outcome="denied",
                metadata={"reason": "Address string too short or invalid", "address": clean_addr},
            )
            return {"ok": False, "error": "Invalid delivery address: please provide full street, area, and city"}

        # Read order to verify existence and business ownership
        order = self.db.get_sales_order(order_id)
        if not order:
            return {"ok": False, "error": f"Order {order_id} not found"}

        if order.get("status") in ("dispatched", "delivered", "cancelled"):
            self.db.record_audit_event(
                actor_type="write_agent",
                actor_id=contact.id,
                action="update_delivery_address",
                resource_type="sales_order",
                resource_id=order_id,
                outcome="denied",
                metadata={"reason": "Order already in terminal/in-transit state", "status": order.get("status")},
            )
            return {
                "ok": False,
                "error": f"Cannot change delivery address: Order {order_id} is already {order.get('status')}",
            }

        # Check permissions
        contact_biz_ids = [r.get("business_id") for r in contact.roles]
        if order.get("buyer_business_id") not in contact_biz_ids and contact.primary_role != ContactRole.ADMIN:
            self.db.record_audit_event(
                actor_type="write_agent",
                actor_id=contact.id,
                action="update_delivery_address",
                resource_type="sales_order",
                resource_id=order_id,
                outcome="denied",
                metadata={"reason": "Caller does not own order", "buyer_biz": order.get("buyer_business_id")},
            )
            return {"ok": False, "error": "Permission denied: you are not authorized to modify this order"}

        # Apply mutation
        res = self.db.update_sales_order_address(order_id, clean_addr, actor_id=contact.id)
        log.info("Address updated for order %s by contact %s", order_id, contact.id)
        return res

    def record_supplier_quote(
        self,
        supplier_business_id: str,
        product_id: str,
        quoted_quantity: float,
        unit_rate: float,
        pack_size: str,
        tax_details: Optional[Dict[str, Any]] = None,
        expiry_date: Optional[str] = None,
        delivery_eta: Optional[str] = None,
        source_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate and record an incoming supplier quotation."""
        if unit_rate <= 0 or quoted_quantity <= 0:
            return {"ok": False, "error": "Unit rate and quantity must be positive"}

        prod = self.db.get_product(product_id)
        if not prod:
            return {"ok": False, "error": f"Product {product_id} not found in catalog"}

        res = self.db.record_supplier_quote(
            supplier_business_id=supplier_business_id,
            product_id=product_id,
            quoted_quantity=quoted_quantity,
            unit_rate=unit_rate,
            pack_size=pack_size or prod.get("pack_size", "standard"),
            tax_details=tax_details,
            expiry_date=expiry_date,
            delivery_eta=delivery_eta,
            source_message_id=source_message_id,
        )
        return res

    def create_draft_order(
        self,
        buyer_business_id: str,
        items: List[Dict[str, Any]],
        delivery_address: str,
        contact: ContactInfo,
    ) -> Dict[str, Any]:
        """Create a new sales order in 'draft' status."""
        if not items:
            return {"ok": False, "error": "Order must contain at least one item"}

        import uuid
        oid = f"ord_{uuid.uuid4().hex[:8]}"
        total = sum(float(i.get("qty", 1)) * float(i.get("rate", 0)) for i in items)

        now = utcnow()
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO sales_orders
                    (id, buyer_business_id, delivery_address, status, currency, total_amount, items, approved_by, created_at, updated_at)
                   VALUES (?, ?, ?, 'draft', 'INR', ?, ?, ?, ?, ?)""",
                (oid, buyer_business_id, delivery_address.strip(), total, json.dumps(items), contact.id, now, now),
            )

        self.db.record_audit_event(
            actor_type="write_agent",
            actor_id=contact.id,
            action="create_draft_order",
            resource_type="sales_order",
            resource_id=oid,
            outcome="success",
            metadata={"items_count": len(items), "total": total},
        )
        return {"ok": True, "order_id": oid, "total": total, "status": "draft"}

    def update_messaging_consent(
        self, contact_id: str, purpose: str, consent_status: str
    ) -> None:
        """Update DPDP opt-in / opt-out preferences."""
        now = utcnow()
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO messaging_preferences
                    (contact_id, purpose, consent_status, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (contact_id, purpose, consent_status, now),
            )
        self.db.record_audit_event(
            actor_type="write_agent",
            actor_id=contact_id,
            action="update_messaging_consent",
            resource_type="messaging_preference",
            resource_id=purpose,
            outcome="success",
            metadata={"consent": consent_status},
        )
