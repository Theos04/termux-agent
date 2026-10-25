"""
WhatsApp CDP Skill — Automate WhatsApp Web on an isolated browser port.

Architecture:
  - Browser CDP port: 9223 (distinct from Maps scraping on 9222).
  - Profile: preserves login cookies and session in data/chrome-whatsapp-profile.
  - Subsystem: WhatsAppRouter dispatching between READ, WRITE, and ACTION specialists.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

from agent.config import AgentConfig
from agent.database import Database
from agent.whatsapp import (
    WhatsAppCDPClient,
    WhatsAppRouter,
    WhatsAppWorker,
)

log = logging.getLogger(__name__)


class WhatsAppSkill:
    """Skill to manage WhatsApp Web using CDP on an isolated port."""

    def __init__(
        self,
        port: Optional[int] = None,
        db: Optional[Database] = None,
        mock_mode: bool = False,
    ):
        cfg = AgentConfig()
        self.port = port or cfg.whatsapp_cdp_port
        self.db = db or Database(cfg.db_path)
        self.cdp = WhatsAppCDPClient(port=self.port, mock_mode=mock_mode)
        self.router = WhatsAppRouter(self.db, self.cdp)
        self._worker: Optional[WhatsAppWorker] = None

    def can_handle(self, goal: str) -> bool:
        """Check if goal relates to WhatsApp."""
        gl = (goal or "").lower()
        keywords = [
            "whatsapp",
            "wa web",
            "wa message",
            "send wa",
            "whatsapp message",
            "unread whatsapp",
            "pharmacy chat",
            "supplier rfq",
        ]
        return any(k in gl for k in keywords)

    def get_status(self) -> Dict[str, Any]:
        """Check connection, QR code, and login status."""
        return self.cdp.get_status()

    def launch_browser(self, headless: Optional[bool] = None) -> Dict[str, Any]:
        """Launch Chrome on the dedicated WhatsApp CDP port."""
        return self.cdp.launch_browser(headless=headless)

    def send_message(self, recipient_phone: str, message_text: str) -> Dict[str, Any]:
        """Send an outbound WhatsApp message via CDP."""
        return self.router.action.send_whatsapp_message(
            recipient_phone=recipient_phone,
            text=message_text,
        )

    def dispatch_message(self, sender_phone: str, message_text: str) -> Dict[str, Any]:
        """Run message through the READ -> WRITE -> ACTION -> ResponseComposer pipeline."""
        res = self.router.dispatch(sender_phone=sender_phone, message_text=message_text)
        return {
            "ok": res.ok,
            "intent": res.intent.value,
            "response": res.response_text,
            "action_taken": res.action_taken,
            "trace": res.execution_trace,
            "details": res.details,
        }

    def poll_messages(self) -> Dict[str, Any]:
        """Poll unread messages and drain outbox once."""
        worker = WhatsAppWorker(db=self.db, cdp_client=self.cdp)
        return worker.poll_once()

    def run(self, goal: str, dry_run: bool = True) -> Dict[str, Any]:
        """Execute goal via WhatsApp skill."""
        gl = goal.lower()
        status = self.get_status()

        if dry_run or "dry" in gl:
            return {
                "ok": True,
                "dry_run": True,
                "goal": goal,
                "port": self.port,
                "status": status,
                "message": f"WhatsApp skill plan: target CDP port {self.port}, status={status.get('logged_in', False)}",
            }

        # Check for send command
        # e.g.: send whatsapp to +919876543210 message: Hello
        send_m = re.search(r"send\s+(?:whatsapp|wa)?\s*(?:to\s+)?(\+?\d+)\s*(?:message[:\s]+)?(.*)", goal, re.IGNORECASE)
        if send_m:
            phone = send_m.group(1).strip()
            msg = send_m.group(2).strip() or "Hello from agent"
            return self.send_message(phone, msg)

        # Check for poll command
        if "poll" in gl or "unread" in gl or "check" in gl:
            return self.poll_messages()

        return {
            "ok": True,
            "port": self.port,
            "status": status,
            "message": f"WhatsApp CDP skill ready on port {self.port}",
        }
