"""
Task handlers for WhatsApp CDP agent and Google Sheets synchronization.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from agent.config import AgentConfig
from agent.database import Database
from agent.registry import register_handler
from agent.whatsapp import WhatsAppCDPClient, WhatsAppRouter, WhatsAppWorker
from agent.whatsapp.google_sheet_sync import GoogleSheetPharmacySync

log = logging.getLogger(__name__)


def handle_whatsapp_dispatch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatch an incoming or simulated WhatsApp message through the Router pipeline.

    Payload keys:
      phone   : str (Sender's WhatsApp number)
      message : str (Message text)
      port    : int (Optional CDP port, default 9223)
    """
    sender_phone = payload.get("phone") or payload.get("from")
    if not sender_phone:
        return {"ok": False, "error": "sender phone is required in payload"}
    message_text = payload.get("message") or payload.get("text") or ""
    if not message_text:
        return {"ok": False, "error": "message text is required in payload"}

    cfg = AgentConfig()
    port = int(payload.get("port") or cfg.whatsapp_cdp_port)
    db = Database(cfg.db_path)
    cdp = WhatsAppCDPClient(port=port)
    router = WhatsAppRouter(db, cdp)

    res = router.dispatch(sender_phone=sender_phone, message_text=message_text)
    return {
        "ok": res.ok,
        "intent": res.intent.value,
        "response": res.response_text,
        "action_taken": res.action_taken,
        "trace": res.execution_trace,
        "requires_human_review": res.requires_human_review,
        "details": res.details,
    }


def handle_whatsapp_send(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send an outbound message via WhatsApp Web over CDP on port 9223.

    Payload keys:
      phone   : str (Recipient phone number)
      message : str (Message text)
      port    : int (Optional CDP port, default 9223)
    """
    phone = payload.get("phone") or payload.get("to")
    message = payload.get("message") or payload.get("text")
    if not phone or not message:
        return {"ok": False, "error": "phone and message are required"}

    cfg = AgentConfig()
    port = int(payload.get("port") or cfg.whatsapp_cdp_port)
    db = Database(cfg.db_path)
    cdp = WhatsAppCDPClient(port=port)
    router = WhatsAppRouter(db, cdp)

    return router.action.send_whatsapp_message(recipient_phone=phone, text=message)


def handle_whatsapp_poll(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run one cycle of WhatsApp polling for unread chats and outbox draining.
    """
    cfg = AgentConfig()
    port = int(payload.get("port") or cfg.whatsapp_cdp_port)
    db = Database(cfg.db_path)
    cdp = WhatsAppCDPClient(port=port)
    worker = WhatsAppWorker(db=db, cdp_client=cdp)

    return worker.poll_once()


def handle_whatsapp_sync_sheets(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synchronize products (gid: 1112889530), parties, suppliers, and purchases
    from the enterprise Google Spreadsheet into local SQLite database.
    """
    cfg = AgentConfig()
    db = Database(cfg.db_path)
    sheet_id = payload.get("spreadsheet_id")
    creds_path = payload.get("creds_path")
    p_limit = int(payload.get("product_limit", 1000))
    c_limit = int(payload.get("party_limit", 500))

    sync = GoogleSheetPharmacySync(db=db, creds_path=creds_path, spreadsheet_id=sheet_id)
    return sync.sync_all(product_limit=p_limit, party_limit=c_limit)


# Register task handlers in agent registry
register_handler("whatsapp_dispatch", handle_whatsapp_dispatch)
register_handler("whatsapp_send", handle_whatsapp_send)
register_handler("whatsapp_poll", handle_whatsapp_poll)
register_handler("whatsapp_sync_sheets", handle_whatsapp_sync_sheets)
