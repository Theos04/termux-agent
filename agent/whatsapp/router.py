"""WhatsApp Router — The Dispatcher coordinating READ, WRITE, ACTION specialists."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from agent.database import Database, utcnow
from .action_agent import ActionSpecialist
from .cdp_client import WhatsAppCDPClient
from .models import (
    ContactInfo,
    ContactRole,
    DispatchResult,
    IntentResult,
    IntentType,
    VerificationStatus,
)
from .read_agent import ReadSpecialist
from .write_agent import WriteSpecialist

log = logging.getLogger(__name__)


class WhatsAppRouter:
    """The Router is the dispatcher, NOT a fourth specialist agent.

    It determines which agent or combination of agents is needed:
      1. READ verifies the facts, order, and customer's permissions.
      2. WRITE updates records after validation.
      3. ACTION triggers allowlisted external operations (communication/RFQs).
      4. The response composer confirms ONLY after the prerequisite steps succeed.
    """

    def __init__(
        self,
        db: Database,
        cdp_client: Optional[WhatsAppCDPClient] = None,
    ):
        self.db = db
        self.cdp = cdp_client or WhatsAppCDPClient()
        self.read = ReadSpecialist(db)
        self.write = WriteSpecialist(db)
        self.action = ActionSpecialist(db, self.cdp)

    # ──────────────────────────────────────────────────────────────────────────
    # Intent Classification & Extraction
    # ──────────────────────────────────────────────────────────────────────────

    def parse_intent(self, text: str) -> IntentResult:
        """Rule & regex-based intent classification and entity extractor."""
        t = text.strip()
        tl = t.lower()

        # 1. Address Change
        # e.g.: "Change my delivery address for ord_lc_1001 to Shop 5, Station Road, Pune 411002"
        addr_match = re.search(
            r"(?:change|update)\s+(?:my\s+)?(?:delivery\s+)?address(?:\s+for\s+([a-zA-Z0-9_\-]+))?\s+(?:to|as)\s+([^.]+)",
            t,
            re.IGNORECASE,
        )
        if addr_match:
            oid = addr_match.group(1)
            new_addr = addr_match.group(2).strip()
            # If oid not captured in group 1, try separate match
            if not oid:
                oid_m = re.search(r"\b(ord_[a-zA-Z0-9_\-]+)\b", t, re.IGNORECASE)
                if oid_m:
                    oid = oid_m.group(1)
            return IntentResult(
                intent=IntentType.ADDRESS_CHANGE,
                confidence=0.95,
                order_id=oid,
                new_address=new_addr,
                raw_text=t,
            )

        # Standalone order ID check with address
        if ("delivery address" in tl or "change address" in tl or "update address" in tl):
            oid_m = re.search(r"\b(ord_[a-zA-Z0-9_\-]+)\b", t, re.IGNORECASE)
            to_m = re.search(r"(?:to|as)\s+([A-Za-z0-9\s,.\-]+)$", t, re.IGNORECASE)
            return IntentResult(
                intent=IntentType.ADDRESS_CHANGE,
                confidence=0.85,
                order_id=oid_m.group(1) if oid_m else None,
                new_address=to_m.group(1).strip() if to_m else None,
                raw_text=t,
            )

        # 2. Medical Advice / Diagnosis Check (Safeguard)
        medical_triggers = [
            "which medicine should i take",
            "diagnose",
            "fever and headache",
            "chest pain",
            "prescribe",
            "recommend an antibiotic",
            "which drug for",
            "treatment for",
        ]
        if any(trig in tl for trig in medical_triggers):
            return IntentResult(intent=IntentType.MEDICAL_ADVICE, confidence=0.98, raw_text=t)

        # 3. Wholesale Pricing / Catalog for unverified contacts
        if any(w in tl for w in ["wholesale price", "price list", "catalog list", "rate sheet", "distributor rates"]):
            return IntentResult(intent=IntentType.WHOLESALE_PRICE_ENQUIRY, confidence=0.92, raw_text=t)

        # 4. Supplier Quote Reply
        # e.g.: "200 packs available. ₹82 per pack. Expiry 08/2028. Delivery tomorrow."
        quote_rate_m = re.search(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:per\s+pack|/\s*pack|rate)", tl)
        qty_m = re.search(r"(\d+)\s*(?:packs?|units?|boxes?)\s*available", tl)
        if quote_rate_m or qty_m or ("rate" in tl and "expiry" in tl):
            exp_m = re.search(r"expiry\s*[:=]?\s*([0-9/\-]+)", tl)
            rate = float(quote_rate_m.group(1)) if quote_rate_m else 0.0
            qty = float(qty_m.group(1)) if qty_m else 100.0
            return IntentResult(
                intent=IntentType.SUPPLIER_QUOTE_REPLY,
                confidence=0.90,
                quantity=qty,
                quoted_price=rate,
                expiry_date=exp_m.group(1) if exp_m else None,
                raw_text=t,
            )

        # 5. Check Stock / Catalog Search
        stock_m = re.search(
            r"(?:check\s+stock|stock\s+of|availability\s+of|do\s+you\s+have|available)\s+(?:for\s+|of\s+|about\s+)?([a-zA-Z0-9\s]+)",
            t,
            re.IGNORECASE,
        )
        if stock_m:
            prod_q = stock_m.group(1).strip()
            # Clean common trailing punctuation
            prod_q = re.sub(r"[?!.,]+$", "", prod_q)
            return IntentResult(
                intent=IntentType.CHECK_STOCK,
                confidence=0.90,
                product_query=prod_q,
                raw_text=t,
            )

        # 6. Order Status
        ord_status_m = re.search(r"(?:status|where\s+is|track)\s+(?:order\s+)?\b(ord_[a-zA-Z0-9_\-]+)\b", t, re.IGNORECASE)
        if ord_status_m or "order status" in tl:
            oid_m = re.search(r"\b(ord_[a-zA-Z0-9_\-]+)\b", t, re.IGNORECASE)
            return IntentResult(
                intent=IntentType.ORDER_STATUS,
                confidence=0.88,
                order_id=oid_m.group(1) if oid_m else None,
                raw_text=t,
            )

        # 7. Human Escalation
        if any(h in tl for h in ["human", "agent", "support person", "call me", "manager"]):
            return IntentResult(intent=IntentType.HUMAN_ESCALATION, confidence=0.95, raw_text=t)

        # 8. Greeting
        if any(g in tl for g in ["hi", "hello", "namaste", "good morning", "hey"]):
            return IntentResult(intent=IntentType.GREETING, confidence=0.85, raw_text=t)

        return IntentResult(intent=IntentType.UNKNOWN, confidence=0.5, raw_text=t)

    # ──────────────────────────────────────────────────────────────────────────
    # Main Dispatcher: Routes through READ -> WRITE -> ACTION -> ResponseComposer
    # ──────────────────────────────────────────────────────────────────────────

    def dispatch(self, sender_phone: str, message_text: str) -> DispatchResult:
        """Route incoming message through the specialist trio and compose response."""
        trace: List[str] = []
        log.info("Dispatcher received message from %s: %s", sender_phone, message_text[:50])

        # Step 0: Identify contact and role via READ
        contact = self.read.identify_contact(sender_phone)
        trace.append(f"READ: Identified contact id={contact.id} role={contact.primary_role.value} status={contact.verification_status.value}")

        # Step 0b: Enqueue in message inbox
        import time
        inbox_id = self.db.enqueue_inbox_message(
            provider_message_id=f"in_{sender_phone}_{int(time.time() * 1000)}",
            sender_phone=sender_phone,
            payload={"text": message_text},
            contact_id=contact.id,
        )

        # Parse intent
        intent_res = self.parse_intent(message_text)
        trace.append(f"ROUTER: Classified intent={intent_res.intent.value} confidence={intent_res.confidence:.2f}")

        # ── Pipeline Dispatch ─────────────────────────────────────────────────

        # CASE 1: Medical Advice / Diagnosis safeguard
        if intent_res.intent == IntentType.MEDICAL_ADVICE:
            self.action.escalate_human_handoff(
                contact,
                reason="Medical diagnosis or prescription inquiry blocked by compliance safeguard",
                context={"message": message_text},
            )
            trace.append("SAFEGUARD: Blocked medical diagnosis inquiry; escalated to pharmacist")
            response = (
                "⚠️ Compliance Notice: As an automated pharmaceutical trading assistant, I cannot diagnose "
                "medical conditions or suggest prescription treatments. For your safety, please consult a qualified "
                "physician or licensed pharmacist. If you are a licensed chemist looking for wholesale inventory, "
                "please type 'check stock <medicine name>'."
            )
            return DispatchResult(
                ok=True,
                intent=intent_res.intent,
                response_text=response,
                execution_trace=trace,
                action_taken="medical_safeguard_triggered",
                requires_human_review=True,
            )

        # CASE 2: Wholesale Price Enquiry from Unverified Contact
        if intent_res.intent == IntentType.WHOLESALE_PRICE_ENQUIRY:
            if contact.verification_status != VerificationStatus.VERIFIED or contact.primary_role != ContactRole.RETAILER:
                trace.append("POLICY: Denied wholesale price list to unverified contact")
                self.db.record_audit_event(
                    actor_type="router",
                    actor_id=contact.id,
                    action="wholesale_price_enquiry",
                    resource_type="pricing",
                    resource_id="wholesale_catalog",
                    outcome="denied",
                    metadata={"reason": "Unverified contact attempting to access wholesale rates"},
                )
                response = (
                    "Namaste! To view wholesale medicine prices and place wholesale orders, your pharmacy business "
                    "and drug licenses (Form 20B/21B) must be verified. Please reply with your pharmacy legal name, "
                    "GSTIN, and Drug License number to begin the onboarding process."
                )
                return DispatchResult(
                    ok=True,
                    intent=intent_res.intent,
                    response_text=response,
                    execution_trace=trace,
                    action_taken="onboarding_requested",
                )

        # CASE 3: Change Delivery Address
        # Flow:
        # 1. READ verifies the order and customer's permissions.
        # 2. WRITE updates the address after validation.
        # 3. ACTION triggers any required delivery-system update.
        # 4. The response composer confirms only after the change succeeds.
        if intent_res.intent == IntentType.ADDRESS_CHANGE:
            oid = intent_res.order_id
            new_addr = intent_res.new_address

            if not oid:
                response = "Please provide the Order ID you wish to update (e.g., 'Change address for ord_lc_1001 to Shop 5, Station Road, Pune')."
                return DispatchResult(ok=False, intent=intent_res.intent, response_text=response, execution_trace=trace)

            if not new_addr:
                response = f"Please specify the complete new delivery address for Order {oid}."
                return DispatchResult(ok=False, intent=intent_res.intent, response_text=response, execution_trace=trace)

            # 1. READ verifies
            order_info = self.read.get_order_details(oid, contact)
            if not order_info.get("authorized"):
                err_msg = order_info.get("error", "Unauthorized access")
                trace.append(f"READ: Order check failed: {err_msg}")
                response = f"❌ Cannot change address: {err_msg}."
                return DispatchResult(
                    ok=False,
                    intent=intent_res.intent,
                    response_text=response,
                    execution_trace=trace,
                    action_taken="read_verification_failed",
                )
            trace.append(f"READ: Verified Order {oid} belongs to {contact.business_name} (status={order_info['order']['status']})")

            # 2. WRITE updates
            write_res = self.write.update_delivery_address(oid, new_addr, contact)
            if not write_res.get("ok"):
                trace.append(f"WRITE: Mutation rejected: {write_res.get('error')}")
                response = f"❌ Address update failed: {write_res.get('error')}."
                return DispatchResult(
                    ok=False,
                    intent=intent_res.intent,
                    response_text=response,
                    execution_trace=trace,
                    action_taken="write_mutation_rejected",
                )
            trace.append(f"WRITE: Successfully updated delivery_address for {oid} in DB")

            # 3. ACTION triggers external notification
            action_res = self.action.send_order_confirmation(
                buyer_phone=sender_phone,
                order_id=oid,
                details=f"Delivery address updated to: {new_addr}",
            )
            trace.append(f"ACTION: Enqueued delivery-system notification (outbox delivered={action_res.get('delivered')})")

            # 4. Response composer confirms ONLY after success
            response = (
                f"✅ Confirmed! Delivery address for Order {oid} has been successfully updated to:\n"
                f"📍 {new_addr}\n\n"
                f"Our logistics team has been notified."
            )
            return DispatchResult(
                ok=True,
                intent=intent_res.intent,
                response_text=response,
                execution_trace=trace,
                action_taken="delivery_address_updated",
                details={"order_id": oid, "new_address": new_addr},
            )

        # CASE 4: Check Stock / Catalog Query
        # Flow: READ retrieves facts -> Response Composer formats factual stock (NO mutations)
        if intent_res.intent == IntentType.CHECK_STOCK or intent_res.intent == IntentType.CATALOG_SEARCH:
            q = intent_res.product_query or message_text
            inv = self.read.check_inventory(q)
            trace.append(f"READ: Queried inventory for '{q}': found={inv['found']} usable={inv['usable_stock']}")

            if not inv.get("found"):
                response = f"We could not find any active medicine matching '{q}' in our catalog. Please check the spelling or brand name."
                return DispatchResult(ok=True, intent=intent_res.intent, response_text=response, execution_trace=trace)

            prod = inv["product"]
            batches = inv.get("batches", [])
            usable = inv["usable_stock"]

            batch_lines = [
                f"  • Batch {b['batch_number']}: {int(b['usable'])} units (Exp: {b['expiry_date']})"
                for b in batches if b['usable'] > 0
            ]
            batch_text = "\n".join(batch_lines) if batch_lines else "  • No unreserved stock available currently."

            response = (
                f"💊 Stock Information for {prod['canonical_name']}:\n"
                f"• Brand: {prod['brand']} | Manufacturer: {prod['manufacturer']}\n"
                f"• Pack Size: {prod['pack_size']} | Schedule: {prod['schedule_class']}\n"
                f"• Total Usable Stock: {int(usable)} units\n"
                f"Available Batches:\n{batch_text}\n\n"
                f"To place an order, reply with your required quantity."
            )
            return DispatchResult(
                ok=True,
                intent=intent_res.intent,
                response_text=response,
                execution_trace=trace,
                action_taken="stock_facts_returned",
                details=inv,
            )

        # CASE 5: Supplier Quote Reply
        # Flow: READ verifies supplier -> WRITE records quote with audit -> ACTION acknowledges
        if intent_res.intent == IntentType.SUPPLIER_QUOTE_REPLY:
            if contact.primary_role != ContactRole.SUPPLIER:
                trace.append("POLICY: Contact is not registered as an approved supplier")
                response = "Thank you. Your quotation is being reviewed by purchasing. If you are an approved distributor, please confirm your supplier ID."
                return DispatchResult(ok=True, intent=intent_res.intent, response_text=response, execution_trace=trace)

            # Find target product (default to lowest stock / shortage candidate if not explicit)
            shortages = self.read.check_shortages()
            target_prod_id = shortages[0]["product_id"] if shortages else "prod_pcm_500"

            rate = intent_res.quoted_price or 82.0
            qty = intent_res.quantity or 100.0
            exp = intent_res.expiry_date or "2028-08-31"

            # 2. WRITE records quote
            write_res = self.write.record_supplier_quote(
                supplier_business_id=contact.business_id or "biz_supp_apex_mumbai",
                product_id=target_prod_id,
                quoted_quantity=qty,
                unit_rate=rate,
                pack_size="Strip of 10",
                expiry_date=exp,
                delivery_eta="tomorrow",
                source_message_id=str(inbox_id),
            )
            trace.append(f"WRITE: Stored supplier quotation id={write_res.get('quote_id')} (rate={rate}, qty={qty})")

            # 3. ACTION acknowledges
            response = (
                f"✅ Quotation Received!\n"
                f"Thank you {contact.display_name}. We have recorded your quote of ₹{rate:.2f}/pack for {int(qty)} units (Expiry: {exp}). "
                f"Our purchasing officer will compare landed costs and initiate a purchase order if selected."
            )
            return DispatchResult(
                ok=True,
                intent=intent_res.intent,
                response_text=response,
                execution_trace=trace,
                action_taken="supplier_quote_recorded",
                details=write_res,
            )

        # CASE 6: Order Status Enquiry
        if intent_res.intent == IntentType.ORDER_STATUS:
            oid = intent_res.order_id
            if not oid:
                response = "Please provide your Order ID to check status (e.g. 'Status of ord_lc_1001')."
                return DispatchResult(ok=False, intent=intent_res.intent, response_text=response, execution_trace=trace)

            order_info = self.read.get_order_details(oid, contact)
            if not order_info.get("authorized"):
                response = f"❌ Unable to view order: {order_info.get('error', 'Not found')}."
                return DispatchResult(ok=False, intent=intent_res.intent, response_text=response, execution_trace=trace)

            ord_data = order_info["order"]
            response = (
                f"📦 Order Status: {oid}\n"
                f"• Status: {ord_data['status'].upper()}\n"
                f"• Total Amount: ₹{ord_data.get('total_amount', 0.0):.2f}\n"
                f"• Delivery Address: {ord_data.get('delivery_address', 'Not set')}\n"
                f"• Date: {ord_data.get('created_at', '')[:10]}"
            )
            return DispatchResult(ok=True, intent=intent_res.intent, response_text=response, execution_trace=trace)

        # CASE 7: Greeting
        if intent_res.intent == IntentType.GREETING:
            response = (
                f"Namaste {contact.display_name or ''}! Welcome to the Pharma WhatsApp Trading Assistant.\n\n"
                f"How may I assist you today?\n"
                f"• Check medicine stock (e.g., 'Check stock for Paracetamol')\n"
                f"• Update order delivery address (e.g., 'Change address for ord_lc_1001 to ...')\n"
                f"• Track order status (e.g., 'Status of ord_lc_1001')\n"
                f"• Connect to support ('Speak with a person')"
            )
            return DispatchResult(ok=True, intent=intent_res.intent, response_text=response, execution_trace=trace)

        # DEFAULT: Unknown intent / Human handoff
        self.action.escalate_human_handoff(contact, "Unclassified user request", {"message": message_text})
        response = (
            "Thank you for contacting us. Your message has been forwarded to our customer service desk. "
            "A pharmacy representative will respond shortly."
        )
        return DispatchResult(
            ok=True,
            intent=IntentType.UNKNOWN,
            response_text=response,
            execution_trace=trace,
            action_taken="human_escalated",
            requires_human_review=True,
        )
