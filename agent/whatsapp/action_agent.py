"""ACTION Specialist — Trading and communication with allowlisted operations."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from agent.database import Database
from .cdp_client import WhatsAppCDPClient
from .models import ContactInfo

log = logging.getLogger(__name__)


class ActionSpecialist:
    """Specialist Agent 3: Trading & Communication (Allowlisted Operations).

    Rules:
      - Allowlisted business operations only.
      - Sending a message is not the same as completing a purchase.
      - High-impact operations (buying, payment, PO issuance) require explicit staff authorization.
    """

    def __init__(self, db: Database, cdp_client: Optional[WhatsAppCDPClient] = None):
        self.db = db
        self.cdp = cdp_client or WhatsAppCDPClient()

    def send_whatsapp_message(
        self,
        recipient_phone: str,
        text: str,
        idempotency_key: Optional[str] = None,
        recipient_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transactional outbox enqueue + WhatsApp CDP send."""
        idem_key = idempotency_key or f"out_{uuid.uuid4().hex[:12]}"
        clean_phone = "".join(c for c in recipient_phone if c.isdigit() or c == "+")

        # 1. Transactional outbox persistence
        out_msg = self.db.enqueue_outbox_message(
            idempotency_key=idem_key,
            recipient_phone=clean_phone,
            payload={"text": text},
            recipient_id=recipient_id,
        )

        # 2. Dispatch via WhatsApp CDP
        try:
            send_res = self.cdp.send_message(text=text, phone=clean_phone)
            if send_res.get("ok"):
                self.db.mark_outbox_sent(idem_key, provider_message_id=idem_key)
                self.db.record_audit_event(
                    actor_type="action_agent",
                    actor_id="system",
                    action="send_whatsapp_message",
                    resource_type="message_outbox",
                    resource_id=idem_key,
                    outcome="success",
                    metadata={"recipient": clean_phone, "text_preview": text[:50]},
                )
                return {"ok": True, "idempotency_key": idem_key, "delivered": True}
            else:
                log.warning("CDP send returned false for %s", clean_phone)
                return {"ok": False, "idempotency_key": idem_key, "error": "CDP send failed"}
        except Exception as exc:
            log.error("Exception during WhatsApp CDP send: %s", exc)
            return {"ok": False, "idempotency_key": idem_key, "error": str(exc)}

    def send_supplier_rfq(
        self,
        supplier_phone: str,
        supplier_name: str,
        product_name: str,
        quantity: float,
        pack_size: str,
    ) -> Dict[str, Any]:
        """Dispatch a standardized RFQ message to an approved supplier."""
        rfq_text = (
            f"Namaste {supplier_name},\n\n"
            f"We require a quotation for the following product:\n"
            f"• Product: {product_name}\n"
            f"• Pack Size: {pack_size}\n"
            f"• Required Quantity: {int(quantity)} packs\n\n"
            f"Please reply with:\n"
            f"1. Available quantity\n"
            f"2. Batch expiry date\n"
            f"3. Net rate per pack (before tax)\n"
            f"4. Applicable GST/taxes & scheme/discount\n"
            f"5. Delivery lead time (days)\n"
            f"6. Minimum Order Quantity (MOQ)\n\n"
            f"Note: This is a quotation request, not a purchase order."
        )

        idem_key = f"rfq_{uuid.uuid4().hex[:10]}"
        return self.send_whatsapp_message(
            recipient_phone=supplier_phone,
            text=rfq_text,
            idempotency_key=idem_key,
        )

    def send_order_confirmation(
        self,
        buyer_phone: str,
        order_id: str,
        details: str,
    ) -> Dict[str, Any]:
        """Send order confirmation or modification receipt."""
        msg = (
            f"✅ Order Update: {order_id}\n\n"
            f"{details}\n\n"
            f"Thank you for choosing our pharma trading network. For help, reply to this message."
        )
        return self.send_whatsapp_message(
            recipient_phone=buyer_phone,
            text=msg,
        )

    def escalate_human_handoff(
        self,
        contact: ContactInfo,
        reason: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Escalate sensitive cases to human staff."""
        self.db.record_audit_event(
            actor_type="action_agent",
            actor_id=contact.id,
            action="human_escalation",
            resource_type="contact",
            resource_id=contact.id,
            outcome="escalated",
            metadata={"reason": reason, "context": context},
        )
        log.warning("Case escalated for contact %s (%s): %s", contact.id, contact.whatsapp_id, reason)
        return {"ok": True, "escalated": True, "reason": reason}
