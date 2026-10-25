"""READ Specialist — Business intelligence with read-only permissions."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agent.database import Database
from .models import ContactInfo, ContactRole, VerificationStatus

log = logging.getLogger(__name__)


class ReadSpecialist:
    """Specialist Agent 1: Business Intelligence (Read-only).

    Rules:
      - Can retrieve facts from database (catalog, stock, orders, quotes).
      - Cannot modify records or make up stock availability.
      - Never performs mutations.
    """

    def __init__(self, db: Database):
        self.db = db

    def identify_contact(self, phone: str) -> ContactInfo:
        """Resolve contact, verification status, and business roles."""
        contact = self.db.get_contact_by_phone(phone)
        if not contact:
            # Create unverified record if brand new
            contact = self.db.create_or_update_contact(phone, verification_status="unverified")

        cid = contact["id"]
        v_status = VerificationStatus(contact.get("verification_status", "unverified"))
        roles = self.db.get_contact_roles(cid)

        return ContactInfo(
            id=cid,
            whatsapp_id=contact.get("whatsapp_id", phone),
            display_name=contact.get("display_name"),
            verification_status=v_status,
            roles=roles,
        )

    def search_catalog(self, query: str) -> List[Dict[str, Any]]:
        """Search medicine catalog by brand, generic name, or ingredient."""
        return self.db.search_products(query, active_only=True)

    def check_inventory(
        self, product_query: str, min_shelf_life_days: int = 90
    ) -> Dict[str, Any]:
        """Check inventory, batches, expiry dates, and usable stock."""
        products = self.search_catalog(product_query)
        if not products:
            return {"found": False, "product": None, "batches": [], "usable_stock": 0.0}

        prod = products[0]
        batches = self.db.get_product_batches(prod["id"], non_expired_only=True)

        cutoff = (datetime.now(timezone.utc) + timedelta(days=min_shelf_life_days)).strftime("%Y-%m-%d")
        valid_batches = []
        total_usable = 0.0

        for b in batches:
            q_usable = max(0.0, float(b["quantity_on_hand"]) - float(b["quantity_reserved"]))
            is_good_shelf_life = b["expiry_date"] >= cutoff
            valid_batches.append({
                "batch_number": b["batch_number"],
                "expiry_date": b["expiry_date"],
                "quantity_on_hand": b["quantity_on_hand"],
                "quantity_reserved": b["quantity_reserved"],
                "usable": q_usable,
                "good_shelf_life": is_good_shelf_life,
            })
            total_usable += q_usable

        return {
            "found": True,
            "product": prod,
            "usable_stock": total_usable,
            "batches": valid_batches,
        }

    def get_order_details(self, order_id: str, contact: ContactInfo) -> Dict[str, Any]:
        """Verify order exists and contact has permission to view/modify it."""
        order = self.db.get_sales_order(order_id)
        if not order:
            return {"authorized": False, "error": f"Order {order_id} not found", "order": None}

        # Check permissions: contact must be verified and associated with buyer_business_id
        if contact.verification_status != VerificationStatus.VERIFIED:
            return {"authorized": False, "error": "Contact is unverified", "order": None}

        buyer_biz = order.get("buyer_business_id")
        contact_biz_ids = [r.get("business_id") for r in contact.roles]

        if buyer_biz not in contact_biz_ids and contact.primary_role != ContactRole.ADMIN:
            return {
                "authorized": False,
                "error": f"Order {order_id} does not belong to your business account",
                "order": None,
            }

        return {"authorized": True, "error": None, "order": order}

    def get_supplier_quotes(self, product_id: str) -> List[Dict[str, Any]]:
        """Retrieve recent supplier quotes for a product."""
        rows = self.db.conn.execute(
            """SELECT sq.*, b.legal_name as supplier_name
               FROM supplier_quotes sq
               JOIN businesses b ON sq.supplier_business_id = b.id
               WHERE sq.product_id = ? AND sq.status = 'received'
               ORDER BY sq.unit_rate ASC LIMIT 10""",
            (product_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def check_shortages(self, reorder_threshold: float = 30.0) -> List[Dict[str, Any]]:
        """Identify products falling below reorder threshold."""
        products = self.db.conn.execute("SELECT * FROM products WHERE active = 1").fetchall()
        shortages = []

        for p in products:
            inv = self.check_inventory(p["canonical_name"])
            usable = inv["usable_stock"]
            if usable < reorder_threshold:
                # Find approved suppliers for this product or suppliers in general
                supp_rows = self.db.conn.execute(
                    """SELECT b.id, b.legal_name, c.whatsapp_id as phone
                       FROM businesses b
                       JOIN contact_roles cr ON cr.business_id = b.id AND cr.role = 'supplier'
                       JOIN contacts c ON c.id = cr.contact_id
                       WHERE b.status = 'active' AND b.license_status = 'verified'"""
                ).fetchall()

                shortages.append({
                    "product_id": p["id"],
                    "canonical_name": p["canonical_name"],
                    "brand": p["brand"],
                    "pack_size": p["pack_size"],
                    "usable_stock": usable,
                    "reorder_needed": max(50.0, 100.0 - usable),
                    "approved_suppliers": [dict(s) for s in supp_rows],
                })
        return shortages
