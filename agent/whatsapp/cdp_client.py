"""WhatsApp Web CDP automation client on isolated port."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

import requests
import websocket

log = logging.getLogger(__name__)


class WhatsAppCDPClient:
    """Automates WhatsApp Web over Chrome DevTools Protocol on a dedicated port.

    Default port: 9223 (isolated from Maps scraping on 9222).
    Default profile: ./data/chrome-whatsapp-profile (preserves login session).
    """

    def __init__(
        self,
        port: int = 9223,
        profile_dir: Optional[str] = None,
        mock_mode: bool = False,
    ):
        self.port = port
        self.mock_mode = mock_mode
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.profile_dir = profile_dir or os.path.join(root, "data", "chrome-whatsapp-profile")
        self.ws: Optional[websocket.WebSocket] = None
        self.ws_url: Optional[str] = None
        self.active_tab_id: Optional[str] = None
        self._cmd_id = 0

    # ──────────────────────────────────────────────────────────────────────────
    # Browser Lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    def is_port_open(self) -> bool:
        if self.mock_mode:
            return True
        try:
            r = requests.get(f"http://127.0.0.1:{self.port}/json/version", timeout=1.5)
            return r.status_code == 200
        except Exception:
            return False

    def launch_browser(self, headless: Optional[bool] = None) -> Dict[str, Any]:
        """Launch Chrome on the dedicated WhatsApp CDP port."""
        if self.mock_mode:
            return {"ok": True, "port": self.port, "mock": True, "message": "Mock browser active"}

        if self.is_port_open():
            self.connect()
            return {"ok": True, "port": self.port, "message": f"Chrome already running on port {self.port}"}

        # Find chrome binary
        candidates = [
            "google-chrome",
            "google-chrome-stable",
            "chromium-browser",
            "chromium",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/data/data/com.termux/files/usr/bin/chromium-browser",
        ]
        binary = None
        for c in candidates:
            if shutil.which(c):
                binary = shutil.which(c)
                break
        if not binary:
            return {"ok": False, "error": "No Chrome/Chromium executable found"}

        os.makedirs(self.profile_dir, exist_ok=True)

        if headless is None:
            # WhatsApp Web requires display/headful mode to scan QR code unless running with virtual screen
            headless = not bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

        cmd = [
            binary,
            f"--remote-debugging-port={self.port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={self.profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1280,800",
            "https://web.whatsapp.com",
        ]
        if headless:
            cmd.insert(1, "--headless=new")
            cmd.insert(1, "--disable-gpu")

        log.info("Launching WhatsApp Chrome on port %d (headless=%s)...", self.port, headless)
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except Exception as exc:
            return {"ok": False, "error": f"Failed to spawn Chrome: {exc}"}

        # Wait for CDP to come up
        deadline = time.time() + 15.0
        while time.time() < deadline:
            if self.is_port_open() and self.connect():
                return {"ok": True, "port": self.port, "message": f"WhatsApp Chrome launched on port {self.port}"}
            time.sleep(0.5)

        return {"ok": False, "error": f"Chrome started but CDP did not become reachable on port {self.port}"}

    def connect(self) -> bool:
        """Connect WebSocket to the WhatsApp tab."""
        if self.mock_mode:
            return True
        try:
            r = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=3.0)
            tabs = r.json()
            whatsapp_tab = None
            for t in tabs:
                if t.get("type") == "page":
                    url = t.get("url", "")
                    if "web.whatsapp.com" in url:
                        whatsapp_tab = t
                        break
                    elif not whatsapp_tab:
                        whatsapp_tab = t

            if not whatsapp_tab:
                return False

            self.active_tab_id = whatsapp_tab.get("id")
            self.ws_url = whatsapp_tab.get("webSocketDebuggerUrl")
            if not self.ws_url:
                return False

            self.ws = websocket.create_connection(self.ws_url, timeout=5)
            self.ws.settimeout(30.0)
            self._send_cdp("Runtime.enable")
            self._send_cdp("Page.enable")
            return True
        except Exception as exc:
            log.debug("WhatsApp CDP connection failed: %s", exc)
            self.ws = None
            return False

    def is_connected(self) -> bool:
        return self.mock_mode or (self.ws is not None)

    # ──────────────────────────────────────────────────────────────────────────
    # CDP Protocol Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _send_cdp(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 20.0) -> Any:
        if self.mock_mode:
            return {}
        if not self.ws:
            if not self.connect():
                return None
        self._cmd_id += 1
        payload = {"id": self._cmd_id, "method": method, "params": params or {}}
        try:
            self.ws.send(json.dumps(payload))
            start_t = time.time()
            while time.time() - start_t < timeout:
                resp = json.loads(self.ws.recv())
                if resp.get("id") == self._cmd_id:
                    return resp
        except Exception as exc:
            log.debug("CDP send error: %s", exc)
            self.ws = None
        return None

    def evaluate_js(self, expression: str, timeout: float = 20.0) -> Any:
        """Evaluate JS in WhatsApp page context."""
        if self.mock_mode:
            return None
        res = self._send_cdp(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            timeout=timeout,
        )
        if res and "result" in res and res["result"].get("value") is not None:
            return res["result"]["value"]
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # WhatsApp Web State & Operations
    # ──────────────────────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Check WhatsApp Web connection and login state."""
        if self.mock_mode:
            return {
                "ok": True,
                "port": self.port,
                "browser_running": True,
                "logged_in": True,
                "qr_waiting": False,
                "unread_chats": 0,
                "mode": "mock",
            }

        browser_up = self.is_port_open()
        if not browser_up:
            return {
                "ok": False,
                "port": self.port,
                "browser_running": False,
                "logged_in": False,
                "qr_waiting": False,
                "message": f"Chrome is not running on port {self.port}. Run launch_browser() first.",
            }

        if not self.is_connected():
            self.connect()

        if not self.is_connected():
            return {
                "ok": False,
                "port": self.port,
                "browser_running": True,
                "connected": False,
                "message": "CDP reachable but could not attach to WhatsApp page",
            }

        # Check DOM state
        check_js = """
        (() => {
            const hasPane = !!document.querySelector('#pane-side');
            const hasQR = !!(document.querySelector('canvas[aria-label*="Scan"]') ||
                             document.querySelector('div[data-ref]') ||
                             document.querySelector('[data-testid="qrcode"]'));
            const unreadCount = document.querySelectorAll('span[aria-label*="unread"]').length;
            return {
                logged_in: hasPane,
                qr_waiting: hasQR,
                unread_chats: unreadCount,
                url: window.location.href,
                title: document.title
            };
        })()
        """
        state = self.evaluate_js(check_js) or {}
        return {
            "ok": True,
            "port": self.port,
            "browser_running": True,
            "connected": True,
            "logged_in": bool(state.get("logged_in")),
            "qr_waiting": bool(state.get("qr_waiting")),
            "unread_chats": state.get("unread_chats", 0),
            "url": state.get("url", ""),
            "title": state.get("title", ""),
        }

    def list_unread_chats(self) -> List[Dict[str, Any]]:
        """Extract contacts/chats that currently have unread badges."""
        if self.mock_mode:
            return []

        extract_js = """
        (() => {
            const results = [];
            const chatItems = document.querySelectorAll('#pane-side div[role="listitem"]');
            chatItems.forEach(item => {
                const unreadBadge = item.querySelector('span[aria-label*="unread"]') ||
                                    item.querySelector('span._ak8i');
                if (unreadBadge) {
                    const titleEl = item.querySelector('span[dir="auto"][title]') ||
                                    item.querySelector('span[title]');
                    const name = titleEl ? (titleEl.getAttribute('title') || titleEl.innerText) : "Unknown";
                    const count = parseInt(unreadBadge.innerText || "1", 10) || 1;
                    const previewEl = item.querySelector('span._ao3e') || item.querySelector('span[dir="ltr"]');
                    const preview = previewEl ? previewEl.innerText : "";
                    results.push({
                        name: name.trim(),
                        unread_count: count,
                        preview: preview.trim()
                    });
                }
            });
            return results;
        })()
        """
        res = self.evaluate_js(extract_js)
        return res if isinstance(res, list) else []

    def open_chat_by_phone(self, phone: str) -> bool:
        """Open chat with specific phone number via web.whatsapp.com/send?phone=..."""
        if self.mock_mode:
            return True

        clean = "".join(c for c in phone if c.isdigit() or c == "+")
        target_url = f"https://web.whatsapp.com/send?phone={clean}"
        log.info("Opening WhatsApp chat for %s...", clean)
        self.evaluate_js(f"window.location.href = '{target_url}'")
        time.sleep(3.0)
        return True

    def get_active_chat_messages(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Extract recent messages from the currently opened conversation."""
        if self.mock_mode:
            return []

        extract_js = f"""
        (() => {{
            const divs = Array.from(document.querySelectorAll('div[data-pre-plain-text]')).slice(-{limit});
            return divs.map(d => {{
                const meta = d.getAttribute('data-pre-plain-text') || '';
                const timeMatch = meta.match(/\\[(.*?)\\]/);
                const senderMatch = meta.match(/\\]\\s*(.*?):/);
                const textEl = d.querySelector('span.selectable-text');
                const text = textEl ? textEl.innerText.trim() : '';
                return {{
                    time: timeMatch ? timeMatch[1] : null,
                    sender: senderMatch ? senderMatch[1].trim() : 'Unknown',
                    text: text
                }};
            }}).filter(m => m.text);
        }})()
        """
        res = self.evaluate_js(extract_js)
        return res if isinstance(res, list) else []

    def send_message(self, text: str, phone: Optional[str] = None) -> Dict[str, Any]:
        """Type and send a message into the WhatsApp Web active conversation."""
        if self.mock_mode:
            log.info("[MOCK CDP] Sent to %s: %s", phone or "active_chat", text[:60])
            return {"ok": True, "phone": phone, "sent_text": text, "mock": True}

        if phone:
            self.open_chat_by_phone(phone)
            time.sleep(2.0)

        escaped = json.dumps(text, ensure_ascii=False)
        send_js = f"""
        (() => {{
            const input = document.querySelector('footer div[contenteditable="true"][role="textbox"]') ||
                          document.querySelector('footer div[contenteditable="true"]');
            if (!input) return {{ ok: false, error: "Message input box not found" }};

            input.focus();
            // Insert text using document.execCommand to trigger WhatsApp internal draft bindings
            document.execCommand('insertText', false, {escaped});

            setTimeout(() => {{
                const sendBtn = document.querySelector('footer button[data-tab="11"]') ||
                                document.querySelector('footer span[data-icon="send"]')?.closest('button') ||
                                document.querySelector('footer button[aria-label*="Send"]');
                if (sendBtn) {{
                    sendBtn.click();
                }} else {{
                    input.dispatchEvent(new KeyboardEvent('keydown', {{
                        key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
                    }}));
                }}
            }}, 300);

            return {{ ok: true }};
        }})()
        """
        res = self.evaluate_js(send_js) or {}
        time.sleep(0.5)
        return {"ok": bool(res.get("ok")), "phone": phone, "sent_text": text}
