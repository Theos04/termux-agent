"""WhatsApp background worker daemon — polls unread chats and drains outbox."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from agent.config import AgentConfig
from agent.database import Database
from .cdp_client import WhatsAppCDPClient
from .router import WhatsAppRouter

log = logging.getLogger(__name__)


class WhatsAppWorker:
    """Daemon worker running on dedicated CDP port.

    Responsibilities:
      - Polls unread WhatsApp chats via CDP.
      - Dispatches incoming messages to WhatsAppRouter.
      - Sends composed responses back via CDP.
      - Drains message_outbox for scheduled/retryable messages.
    """

    def __init__(
        self,
        db: Optional[Database] = None,
        cdp_client: Optional[WhatsAppCDPClient] = None,
        poll_interval: float = 5.0,
    ):
        cfg = AgentConfig()
        self.db = db or Database(cfg.db_path)
        self.cdp = cdp_client or WhatsAppCDPClient(port=cfg.whatsapp_cdp_port)
        self.router = WhatsAppRouter(self.db, self.cdp)
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start worker loop in a background daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="whatsapp-worker", daemon=True)
        self._thread.start()
        log.info("WhatsAppWorker started on CDP port %d (poll=%0.1fs)", self.cdp.port, self.poll_interval)

    def stop(self) -> None:
        """Stop worker loop."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        log.info("WhatsAppWorker stopped")

    def poll_once(self) -> dict:
        """Run a single polling cycle: check unread chats, dispatch, drain outbox."""
        status = self.cdp.get_status()
        if not status.get("logged_in") and not self.cdp.mock_mode:
            return {"ok": False, "status": status, "processed": 0}

        # 1. Drain pending outbox
        pending = self.db.get_pending_outbox_messages(limit=10)
        outbox_sent = 0
        for m in pending:
            payload = m.get("payload") or {}
            txt = payload.get("text", "")
            if txt:
                res = self.cdp.send_message(txt, phone=m["recipient_phone"])
                if res.get("ok"):
                    self.db.mark_outbox_sent(m["idempotency_key"])
                    outbox_sent += 1

        # 2. Check unread chats
        unread = self.cdp.list_unread_chats()
        processed = 0

        for chat in unread:
            name = chat.get("name", "")
            preview = chat.get("preview", "")
            if not preview:
                continue

            # Dispatch through router
            res = self.router.dispatch(sender_phone=name, message_text=preview)
            if res.ok and res.response_text:
                self.cdp.send_message(res.response_text, phone=name)
                processed += 1

        return {
            "ok": True,
            "unread_found": len(unread),
            "processed": processed,
            "outbox_drained": outbox_sent,
        }

    def _run_loop(self) -> None:
        while self._running:
            try:
                self.poll_once()
            except Exception as exc:
                log.error("Error in WhatsAppWorker loop: %s", exc)
            time.sleep(self.poll_interval)
