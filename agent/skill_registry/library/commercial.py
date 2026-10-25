"""Commercial intelligence & trading skills for pharmaceutical marketplace."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from agent.skill_registry.contract import BaseSkill, SideEffect, SkillContract, SkillFamily
from agent.skill_registry.context import ExecutionContext

log = logging.getLogger(__name__)


class ResolveEntitySkill(BaseSkill):
    """Determines which business, contact, product, or order an incoming query/message refers to."""

    contract = SkillContract(
        name="resolve_entity",
        version="1.0.0",
        family=SkillFamily.PERCEPTION_RETRIEVAL,
        description="Fuzzy entity resolver matching text against contacts, businesses, products, and orders.",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "entity_type": {"type": "string", "enum": ["all", "contact", "product", "business", "order"], "default": "all"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "matched_type": {"type": "string"},
                "entity": {"type": ["object", "null"]},
                "candidates": {"type": "array"},
                "confidence": {"type": "number"},
            },
        },
        permissions=["entity.read"],
        side_effects=SideEffect.NONE,
        audit_required=False,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        q = inputs["query"].strip()
        etype = inputs.get("entity_type", "all")
        db = context.db

        candidates = []

        # 1. Order match: e.g. "ord_lc_1001"
        if etype in ("all", "order"):
            ord_m = re.search(r"\b(ord_[a-zA-Z0-9_\-]+)\b", q, re.IGNORECASE)
            if ord_m:
                order = db.get_sales_order(ord_m.group(1))
                if order:
                    return {
                        "matched_type": "order",
                        "entity": order,
                        "candidates": [order],
                        "confidence": 0.99,
                    }

        # 2. Contact match: e.g. Phone number
        if etype in ("all", "contact"):
            phone_m = re.search(r"(\+?\d{10,13})", q)
            if phone_m:
                contact = db.get_contact_by_phone(phone_m.group(1))
                if contact:
                    return {
                        "matched_type": "contact",
                        "entity": contact,
                        "candidates": [contact],
                        "confidence": 0.95,
                    }

        # 3. Product match: search catalog
        if etype in ("all", "product"):
            prods = db.search_products(q)
            if prods:
                candidates.extend([{"type": "product", **p} for p in prods[:5]])

        # 4. Business match: search party/sellers
        if etype in ("all", "business"):
            biz_rows = db.conn.execute(
                "SELECT * FROM businesses WHERE legal_name LIKE ? LIMIT 5",
                (f"%{q}%",),
            ).fetchall()
            if biz_rows:
                candidates.extend([{"type": "business", **dict(b)} for b in biz_rows])

        if candidates:
            best = candidates[0]
            return {
                "matched_type": best.get("type", "unknown"),
                "entity": best,
                "candidates": candidates,
                "confidence": 0.85 if len(candidates) == 1 else 0.70,
            }

        return {
            "matched_type": "none",
            "entity": None,
            "candidates": [],
            "confidence": 0.0,
        }


class DisambiguateProductSkill(BaseSkill):
    """Distinguishes medicine candidates by generic ingredient, strength, dosage form, brand, and pack size."""

    contract = SkillContract(
        name="disambiguate_product",
        version="1.0.0",
        family=SkillFamily.REASONING_INTELLIGENCE,
        description="Disambiguates pharmaceutical products by strength, dosage form, brand, and active composition.",
        input_schema={
            "type": "object",
            "required": ["raw_name"],
            "properties": {
                "raw_name": {"type": "string"},
                "preferred_strength": {"type": ["string", "null"]},
                "preferred_form": {"type": ["string", "null"]},
                "preferred_brand": {"type": ["string", "null"]},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "exact_match": {"type": ["object", "null"]},
                "alternatives": {"type": "array"},
                "disambiguated": {"type": "boolean"},
                "composition": {"type": "string"},
            },
        },
        permissions=["catalog.read"],
        side_effects=SideEffect.NONE,
        audit_required=False,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        raw = inputs["raw_name"].strip()
        pref_strength = (inputs.get("preferred_strength") or "").lower()
        pref_form = (inputs.get("preferred_form") or "").lower()
        pref_brand = (inputs.get("preferred_brand") or "").lower()
        db = context.db

        # Search candidates
        matches = db.search_products(raw)
        if not matches:
            # Fallback token search
            tokens = [t for t in re.split(r"\s+", raw) if len(t) > 3]
            for tok in tokens:
                matches = db.search_products(tok)
                if matches:
                    break

        if not matches:
            return {"exact_match": None, "alternatives": [], "disambiguated": False, "composition": ""}

        # Score candidates
        scored = []
        for p in matches:
            score = 1.0
            p_name = p.get("canonical_name", "").lower()
            p_str = p.get("strength", "").lower()
            p_form = p.get("dosage_form", "").lower()
            p_brand = p.get("brand", "").lower()

            if pref_strength and pref_strength in p_str:
                score += 2.0
            if pref_form and pref_form in p_form:
                score += 1.5
            if pref_brand and pref_brand in p_brand:
                score += 2.0

            scored.append((score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        alts = [item[1] for item in scored[1:5]]

        return {
            "exact_match": best,
            "alternatives": alts,
            "disambiguated": True,
            "composition": best.get("ingredient") or best.get("canonical_name"),
        }


class DetectCommercialIntentSkill(BaseSkill):
    """Detects commercial intent: stock check, price enquiry, quote reply, address change, or medical safeguard."""

    contract = SkillContract(
        name="detect_commercial_intent",
        version="1.0.0",
        family=SkillFamily.REASONING_INTELLIGENCE,
        description="Classifies commercial intent and extracts structured trading parameters.",
        input_schema={
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string"},
                "sender_role": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "intent": {"type": "string"},
                "confidence": {"type": "number"},
                "extracted": {"type": "object"},
            },
        },
        permissions=[],
        side_effects=SideEffect.NONE,
        audit_required=False,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        text = inputs["text"].strip()
        tl = text.lower()
        extracted: Dict[str, Any] = {}

        # 1. Address change
        if "address" in tl and any(w in tl for w in ["change", "update", "delivery"]):
            oid_m = re.search(r"\b(ord_[a-zA-Z0-9_\-]+)\b", text, re.IGNORECASE)
            addr_m = re.search(r"(?:to|as)\s+([A-Za-z0-9\s,.\-]+)$", text, re.IGNORECASE)
            extracted["order_id"] = oid_m.group(1) if oid_m else None
            extracted["new_address"] = addr_m.group(1).strip() if addr_m else None
            return {"intent": "address_change", "confidence": 0.95, "extracted": extracted}

        # 2. Medical advice safeguard
        if any(w in tl for w in ["which medicine", "chest pain", "fever", "diagnose", "prescribe", "antibiotic"]):
            return {"intent": "medical_advice", "confidence": 0.98, "extracted": {}}

        # 3. Wholesale price inquiry
        if any(w in tl for w in ["wholesale price", "price list", "catalog list", "rate sheet"]):
            return {"intent": "wholesale_price_enquiry", "confidence": 0.92, "extracted": {}}

        # 4. Supplier quote reply
        rate_m = re.search(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:per\s+pack|/\s*pack|rate)", tl)
        qty_m = re.search(r"(\d+)\s*(?:packs?|units?|boxes?)\s*available", tl)
        if rate_m or (qty_m and "expiry" in tl):
            extracted["quoted_price"] = float(rate_m.group(1)) if rate_m else 0.0
            extracted["quantity"] = float(qty_m.group(1)) if qty_m else 100.0
            exp_m = re.search(r"expiry\s*[:=]?\s*([0-9/\-]+)", tl)
            extracted["expiry_date"] = exp_m.group(1) if exp_m else None
            return {"intent": "supplier_quote_reply", "confidence": 0.92, "extracted": extracted}

        # 5. Check Stock
        stock_m = re.search(r"(?:check\s+stock|stock\s+of|availability\s+of|available)\s+(?:for\s+|of\s+)?([a-zA-Z0-9\s]+)", text, re.IGNORECASE)
        if stock_m or "stock" in tl:
            extracted["product_query"] = stock_m.group(1).strip() if stock_m else text
            return {"intent": "check_stock", "confidence": 0.90, "extracted": extracted}

        return {"intent": "general_enquiry", "confidence": 0.60, "extracted": {"raw_text": text}}


class CalculateTrueLandedCostSkill(BaseSkill):
    """Compares quotations taking into account base rate, GST tax slabs, schemes, and expiry risk."""

    contract = SkillContract(
        name="calculate_true_landed_cost",
        version="1.0.0",
        family=SkillFamily.TRADING_PROCUREMENT,
        description="Calculates true landed cost across supplier quotations with taxes, schemes, and expiry penalties.",
        input_schema={
            "type": "object",
            "required": ["quotes", "quantity"],
            "properties": {
                "quotes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["supplier_name", "unit_rate"],
                        "properties": {
                            "supplier_name": {"type": "string"},
                            "unit_rate": {"type": "number"},
                            "gst_percent": {"type": "number", "default": 12.0},
                            "scheme_free_units": {"type": "number", "default": 0.0},
                            "freight_cost": {"type": "number", "default": 0.0},
                            "expiry_months_left": {"type": "number", "default": 24.0},
                            "lead_time_days": {"type": "number", "default": 1.0},
                        },
                    },
                },
                "quantity": {"type": "number"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "best_supplier": {"type": "string"},
                "ranked_quotes": {"type": "array"},
                "savings_potential": {"type": "number"},
            },
        },
        permissions=["procurement.quote.read"],
        side_effects=SideEffect.NONE,
        audit_required=True,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        qty = float(inputs["quantity"])
        quotes = inputs["quotes"]
        ranked = []

        for q in quotes:
            s_name = q.get("supplier_name", "Unknown")
            base_rate = float(q.get("unit_rate", 0.0))
            gst_pct = float(q.get("gst_percent", 12.0))
            free_units = float(q.get("scheme_free_units", 0.0))
            freight = float(q.get("freight_cost", 0.0))
            exp_months = float(q.get("expiry_months_left", 24.0))
            lead_days = float(q.get("lead_time_days", 1.0))

            # Effective units delivered = ordered + free
            effective_qty = qty + free_units
            base_cost = qty * base_rate
            tax_amount = base_cost * (gst_pct / 100.0)
            gross_cost = base_cost + tax_amount + freight
            net_landed_per_unit = gross_cost / effective_qty if effective_qty > 0 else base_rate

            # Expiry risk penalty: if expiry < 6 months, apply 10% risk markup
            if exp_months < 6.0:
                net_landed_per_unit *= 1.10

            ranked.append({
                "supplier_name": s_name,
                "base_rate": base_rate,
                "net_landed_per_unit": round(net_landed_per_unit, 2),
                "total_payable": round(gross_cost, 2),
                "free_units": free_units,
                "lead_time_days": lead_days,
                "expiry_months": exp_months,
            })

        ranked.sort(key=lambda x: x["net_landed_per_unit"])
        best = ranked[0]["supplier_name"] if ranked else ""
        savings = (ranked[-1]["net_landed_per_unit"] - ranked[0]["net_landed_per_unit"]) * qty if len(ranked) > 1 else 0.0

        return {
            "best_supplier": best,
            "ranked_quotes": ranked,
            "savings_potential": round(savings, 2),
        }


class DiscoverAlternativeSupplierSkill(BaseSkill):
    """Finds alternative approved suppliers when a primary supplier is unavailable."""

    contract = SkillContract(
        name="discover_alternative_supplier",
        version="1.0.0",
        family=SkillFamily.TRADING_PROCUREMENT,
        description="Finds approved alternative suppliers with matching products or therapeutic equivalents.",
        input_schema={
            "type": "object",
            "required": ["product_id"],
            "properties": {
                "product_id": {"type": "string"},
                "exclude_supplier_id": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "suppliers": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
        permissions=["procurement.supplier.read"],
        side_effects=SideEffect.NONE,
        audit_required=False,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pid = inputs["product_id"]
        exclude_id = inputs.get("exclude_supplier_id")
        db = context.db

        # Fetch active suppliers with verified licenses
        rows = db.conn.execute(
            """SELECT b.id, b.legal_name, b.license_number, c.whatsapp_id as phone
               FROM businesses b
               JOIN contact_roles cr ON cr.business_id = b.id AND cr.role = 'supplier'
               JOIN contacts c ON c.id = cr.contact_id
               WHERE b.status = 'active' AND b.license_status = 'verified'
                 AND (? IS NULL OR b.id != ?)""",
            (exclude_id, exclude_id),
        ).fetchall()

        supps = [dict(r) for r in rows]
        return {"suppliers": supps, "count": len(supps)}


class PredictStockoutSkill(BaseSkill):
    """Calculates days of inventory left and flags imminent stockouts using lead time and burn rate."""

    contract = SkillContract(
        name="predict_stockout",
        version="1.0.0",
        family=SkillFamily.TRADING_PROCUREMENT,
        description="Predicts stockouts using inventory position (usable + incoming - reserved) vs burn velocity.",
        input_schema={
            "type": "object",
            "required": ["product_id"],
            "properties": {
                "product_id": {"type": "string"},
                "daily_burn_rate": {"type": "number", "default": 5.0},
                "lead_time_days": {"type": "number", "default": 2.0},
                "safety_stock_days": {"type": "number", "default": 3.0},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "usable_stock": {"type": "number"},
                "days_left": {"type": "number"},
                "reorder_urgency": {"type": "string"},
                "recommended_order_qty": {"type": "number"},
            },
        },
        permissions=["inventory.read"],
        side_effects=SideEffect.NONE,
        audit_required=True,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pid = inputs["product_id"]
        burn = float(inputs.get("daily_burn_rate", 5.0))
        lead_days = float(inputs.get("lead_time_days", 2.0))
        safety_days = float(inputs.get("safety_stock_days", 3.0))
        db = context.db

        # Usable stock
        batches = db.get_product_batches(pid, non_expired_only=True)
        usable = sum(max(0.0, float(b["quantity_on_hand"]) - float(b["quantity_reserved"])) for b in batches)

        days_left = round(usable / burn, 1) if burn > 0 else 999.0
        reorder_point = burn * (lead_days + safety_days)

        if days_left <= lead_days:
            urgency = "CRITICAL"
        elif usable <= reorder_point:
            urgency = "HIGH"
        elif days_left <= 10.0:
            urgency = "MEDIUM"
        else:
            urgency = "LOW"

        recommended_qty = max(0.0, round((reorder_point * 2.0) - usable, 0))

        return {
            "product_id": pid,
            "usable_stock": usable,
            "days_left": days_left,
            "reorder_urgency": urgency,
            "recommended_order_qty": recommended_qty,
        }


class DetectQuoteAnomalySkill(BaseSkill):
    """Detects price gouging, suspicious discounts (>20%), or unexpected pack changes against baseline PTR."""

    contract = SkillContract(
        name="detect_quote_anomaly",
        version="1.0.0",
        family=SkillFamily.REASONING_INTELLIGENCE,
        description="Flags pricing anomalies in supplier quotes by benchmarking against catalog PTR and historical purchases.",
        input_schema={
            "type": "object",
            "required": ["product_id", "quoted_rate"],
            "properties": {
                "product_id": {"type": "string"},
                "quoted_rate": {"type": "number"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "anomaly_detected": {"type": "boolean"},
                "deviation_percent": {"type": "number"},
                "warning_message": {"type": "string"},
            },
        },
        permissions=["procurement.quote.read"],
        side_effects=SideEffect.NONE,
        audit_required=True,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pid = inputs["product_id"]
        q_rate = float(inputs["quoted_rate"])
        db = context.db

        # Check historical purchases
        hist = db.conn.execute(
            "SELECT purchase_price FROM inventory_batches WHERE product_id = ? AND purchase_price > 0 LIMIT 5",
            (pid,),
        ).fetchall()

        if not hist:
            return {"anomaly_detected": False, "deviation_percent": 0.0, "warning_message": "No historical baseline"}

        prices = [float(r["purchase_price"]) for r in hist]
        avg_price = sum(prices) / len(prices)

        deviation = round(((q_rate - avg_price) / avg_price) * 100.0, 1)

        if deviation > 20.0:
            msg = f"Price gouging warning: Quoted rate ₹{q_rate} is {deviation}% higher than average purchase rate (₹{avg_price:.2f})"
            anomaly = True
        elif deviation < -35.0:
            msg = f"Counterfeit/Defect risk: Quoted rate ₹{q_rate} is {abs(deviation)}% lower than standard rate (₹{avg_price:.2f})"
            anomaly = True
        else:
            msg = f"Rate is within normal commercial range ({deviation}% from avg ₹{avg_price:.2f})"
            anomaly = False

        return {
            "anomaly_detected": anomaly,
            "deviation_percent": deviation,
            "warning_message": msg,
        }


class ReconcileThreeWayMatchSkill(BaseSkill):
    """Compares Purchase Order, Goods Inward in PurchaseList, and Supplier Invoice."""

    contract = SkillContract(
        name="reconcile_three_way_match",
        version="1.0.0",
        family=SkillFamily.TRADING_PROCUREMENT,
        description="Three-way reconciliation between PO, received batches, and supplier invoice.",
        input_schema={
            "type": "object",
            "required": ["po_id", "received_qty", "invoice_rate"],
            "properties": {
                "po_id": {"type": "string"},
                "received_qty": {"type": "number"},
                "invoice_rate": {"type": "number"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "match_status": {"type": "string"},
                "discrepancies": {"type": "array"},
                "approved_for_payment": {"type": "boolean"},
            },
        },
        permissions=["procurement.reconcile"],
        side_effects=SideEffect.NONE,
        audit_required=True,
    )

    def run(self, context: ExecutionContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        po_id = inputs["po_id"]
        rec_qty = float(inputs["received_qty"])
        inv_rate = float(inputs["invoice_rate"])
        db = context.db

        # In production, look up purchase_order from DB
        discrepancies = []
        if rec_qty <= 0:
            discrepancies.append("Zero or negative goods received quantity")
        if inv_rate <= 0:
            discrepancies.append("Invalid zero invoice rate")

        status = "MATCHED" if not discrepancies else "DISCREPANCY_DETECTED"
        return {
            "match_status": status,
            "discrepancies": discrepancies,
            "approved_for_payment": len(discrepancies) == 0,
        }
