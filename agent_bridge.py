#!/usr/bin/env python3
"""
agent_bridge.py - Unified integration bridge for:
1. fetch_page (CDP DOM inspection & HTTP fallback)
2. quick_capture_har_ (CDP background HAR network recorder)
3. orchestrator_agent (Autonomous reasoning & tool execution loop)
4. llama_tui (TUI integration layer)
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urlparse, quote_plus

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts-library")
AGENT_RUNS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_runs")
MEMORY_PATH = os.path.join(
    os.path.expanduser("~"), ".llama-tui", "agent_memory.json"
)
_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PINCODE_CSV = os.environ.get(
    "PINCODE_CSV",
    os.path.join(_REPO_ROOT, "data", "pincodes.csv"),
)

# Skills package (deterministic scrape path — no LLM)
try:
    from agent.skills import SkillsPipeline, DEFAULT_PINCODE_CSV as _SKILL_PIN_CSV
    DEFAULT_PINCODE_CSV = os.environ.get("PINCODE_CSV", _SKILL_PIN_CSV)
    HAS_SKILLS = True
except ImportError:
    SkillsPipeline = None  # type: ignore
    HAS_SKILLS = False

try:
    import requests
except ImportError:
    requests = None

try:
    import websocket
except ImportError:
    websocket = None

# Prefer websocket-client; fall back to debian python3-websockets sync API
if websocket is None:
    try:
        from websockets.sync.client import connect as _ws_sync_connect

        class _WebSocketTimeoutException(TimeoutError):
            pass

        class _SyncWebSocketShim:
            """Minimal websocket-client compatible wrapper around websockets.sync."""

            def __init__(self, url: str, timeout: float = 5.0):
                self._ws = _ws_sync_connect(url, open_timeout=timeout, close_timeout=2)
                self._timeout = timeout

            def settimeout(self, timeout: float) -> None:
                self._timeout = timeout

            def send(self, data: str) -> None:
                self._ws.send(data)

            def recv(self) -> str:
                try:
                    return self._ws.recv(timeout=self._timeout)
                except TimeoutError as e:
                    raise _WebSocketTimeoutException(str(e)) from e
                except Exception as e:
                    # websockets raises its own timeout types on some versions
                    if "timeout" in type(e).__name__.lower() or "timed out" in str(e).lower():
                        raise _WebSocketTimeoutException(str(e)) from e
                    raise

            def close(self) -> None:
                try:
                    self._ws.close()
                except Exception:
                    pass

        class _WebsocketModule:
            WebSocketTimeoutException = _WebSocketTimeoutException

            @staticmethod
            def create_connection(url: str, timeout: float = 5.0):
                return _SyncWebSocketShim(url, timeout=timeout)

        websocket = _WebsocketModule()  # type: ignore
    except Exception:
        websocket = None

# Multi-Model Context Protocol (LangGraph / MMDeploy / production HAR)
try:
    from mmcp import get_router, MultiModelWorkflow, load_config as load_mmcp_config
    from mmcp.har import ProductionHARCapturer, analyze_har as mmcp_analyze_har
    from mmcp.graph.workflow import langgraph_available as mmcp_langgraph_available

    HAS_MMCP = True
except ImportError:
    get_router = None  # type: ignore
    MultiModelWorkflow = None  # type: ignore
    load_mmcp_config = None  # type: ignore
    ProductionHARCapturer = None  # type: ignore
    mmcp_analyze_har = None  # type: ignore
    mmcp_langgraph_available = lambda: False  # type: ignore
    HAS_MMCP = False


logger = logging.getLogger("agent_bridge")


def create_mmcp_llm_fn(role: str = "chat") -> Optional[Callable[[str], str]]:
    """Build an OrchestratorAgent-compatible llm_fn from the mmcp router."""
    if not HAS_MMCP or get_router is None:
        return None
    return get_router().as_llm_fn(role=role)


def _clip_for_log(obj: Any, max_chars: int = 800) -> Any:
    """Shrink CDP payloads for durable logs without dumping huge trees."""
    try:
        s = json.dumps(obj, default=str)
    except Exception:
        s = str(obj)
    if len(s) <= max_chars:
        return obj
    return {"_truncated": s[:max_chars] + f"…(+{len(s) - max_chars} chars)"}


# ============================================================================
# 1. HTML PARSER / TEXT EXTRACTOR (HTTP Fallback)
# ============================================================================

class HTMLTextExtractor(HTMLParser):
    """Clean text extractor from HTML using standard library."""
    def __init__(self):
        super().__init__()
        self.text_parts: List[str] = []
        self.skip_depth = 0
        self.skip_containers = {"script", "style", "noscript", "head", "svg"}
        self.links: List[Dict[str, str]] = []

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        if tag_lower in self.skip_containers:
            self.skip_depth += 1
        elif tag_lower == "a" and self.skip_depth == 0:
            attr_dict = dict(attrs)
            href = attr_dict.get("href", "")
            if href and not href.startswith("javascript:") and not href.startswith("#"):
                self.links.append({"href": href, "text": ""})

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in self.skip_containers and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.skip_depth == 0:
            cleaned = data.strip()
            if cleaned:
                self.text_parts.append(cleaned)
                if self.links and not self.links[-1]["text"]:
                    self.links[-1]["text"] = cleaned

    def get_text(self) -> str:
        return " ".join(self.text_parts)


@dataclass
class PageSnapshot:
    url: str = ""
    title: str = ""
    text: str = ""
    interactives: List[Dict[str, Any]] = field(default_factory=list)
    form_inputs: List[Dict[str, Any]] = field(default_factory=list)
    status_code: int = 200
    source: str = "cdp"  # 'cdp' or 'http'
    timestamp: float = field(default_factory=time.time)

    def summary(self, max_text_chars: int = 1000) -> str:
        lines = [
            f"URL: {self.url or '(none)'}",
            f"Title: {self.title or '(no title)'}",
            f"Source: {self.source.upper()}",
        ]
        if self.interactives:
            lines.append(f"\nInteractive Elements ({len(self.interactives)} found):")
            for item in self.interactives[:15]:
                idx = item.get("idx", "?")
                tag = item.get("tag", "").upper()
                text = item.get("text", "") or item.get("href", "") or "[Element]"
                selector = item.get("selector", "")
                lines.append(f"  [{idx}] {tag} \"{text[:40]}\" -> {selector}")
            if len(self.interactives) > 15:
                lines.append(f"  ... and {len(self.interactives) - 15} more")

        clean_snippet = re.sub(r"\s+", " ", self.text).strip()
        if len(clean_snippet) > max_text_chars:
            clean_snippet = clean_snippet[:max_text_chars] + "..."
        lines.append(f"\nPage Content:\n{clean_snippet or '(empty text)'}")
        return "\n".join(lines)


# ============================================================================
# 2. PAGE FETCHER (CDP + HTTP Fallback)
# ============================================================================

class PageFetcher:
    """
    Unified page fetcher supporting:
    - Chrome DevTools Protocol (CDP) WebSocket inspection & interaction
    - Direct HTTP scraping fallback via urllib
    """

    def __init__(self, port: int = 9222):
        self.port = port
        self.ws: Optional[Any] = None
        self.ws_url: Optional[str] = None
        self.active_tab_id: Optional[str] = None
        self.active_url: str = ""
        self.active_title: str = ""
        self.last_snapshot: Optional[PageSnapshot] = None
        self._cmd_counter = 0
        self._lock = threading.Lock()
        # Durable CDP I/O trail (AI + tooling can inspect)
        self.cdp_log: List[Dict[str, Any]] = []
        self._log_limit = 200

    def find_available_port(self) -> Optional[int]:
        """Check common debugging ports."""
        if not requests:
            return None
        candidate_ports = [self.port, 9222, 9226, 9228, 9236]
        for p in candidate_ports:
            try:
                r = requests.get(f"http://127.0.0.1:{p}/json", timeout=1)
                if r.status_code == 200:
                    self.port = p
                    return p
            except Exception:
                continue
        return None

    def connect(self, port: Optional[int] = None) -> bool:
        """Connect to Chrome CDP WebSocket."""
        if port:
            self.port = port
        if not requests or not websocket:
            return False

        try:
            resp = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=3)
            tabs = resp.json()
            page_tab = None
            for t in tabs:
                if t.get("type") == "page":
                    page_tab = t
                    break
            if not page_tab:
                return False

            self.active_tab_id = page_tab.get("id")
            self.active_title = page_tab.get("title", "")
            self.active_url = page_tab.get("url", "")
            self.ws_url = page_tab.get("webSocketDebuggerUrl")
            if not self.ws_url:
                return False

            # Connect with a short open timeout, then raise recv timeout —
            # long Runtime.evaluate (Maps scroll/phone enrich) needs headroom.
            self.ws = websocket.create_connection(self.ws_url, timeout=5)
            try:
                self.ws.settimeout(120)
            except Exception:
                pass
            self._send_cdp("Runtime.enable")
            self._send_cdp("Page.enable")
            self._send_cdp("Accessibility.enable")
            return True
        except Exception as e:
            logger.debug(f"CDP connection failed on port {self.port}: {e}")
            self.ws = None
            return False

    def is_connected(self) -> bool:
        return self.ws is not None

    @staticmethod
    def find_chrome_binary() -> Optional[str]:
        for name in (
            "google-chrome-stable",
            "google-chrome",
            "chromium-browser",
            "chromium",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ):
            if os.path.isabs(name) and os.path.isfile(name) and os.access(name, os.X_OK):
                return name
            found = shutil.which(name)
            if found:
                return found
        return None

    def cdp_reachable(self, port: Optional[int] = None) -> bool:
        """True if Chrome DevTools HTTP endpoint answers (even if we are not WS-connected)."""
        if not requests:
            return False
        p = port or self.port
        try:
            r = requests.get(f"http://127.0.0.1:{p}/json", timeout=1.5)
            return r.status_code == 200
        except Exception:
            return False

    def ensure_chrome(
        self,
        *,
        timeout_s: float = 20.0,
        headless: Optional[bool] = None,
        notify: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Make sure Chrome is listening on the debug port, then attach CDP.

        Launches a persistent-profile Chrome (same idea as launch-chrome.py)
        when nothing is listening. Returns {ok, port, launched, message}.
        """
        log = notify or (lambda _m: None)

        found = self.find_available_port()
        if found:
            connected = self.is_connected() or self.connect(found)
            if connected or self.cdp_reachable(found):
                return {
                    "ok": True,
                    "port": self.port,
                    "launched": False,
                    "message": f"Chrome CDP already up on {self.port}",
                }

        binary = self.find_chrome_binary()
        if not binary:
            return {
                "ok": False,
                "port": self.port,
                "launched": False,
                "message": "No Chrome/Chromium binary found",
            }

        if headless is None:
            env_h = os.environ.get("CHROME_HEADLESS", "").strip().lower()
            if env_h in ("1", "true", "yes", "on"):
                headless = True
            elif env_h in ("0", "false", "no", "off"):
                headless = False
            else:
                headless = not bool(
                    os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
                )

        profile = os.environ.get(
            "CHROME_PROFILE_DIR",
            os.path.expanduser("~/chrome-persistent-profile"),
        )
        os.makedirs(profile, exist_ok=True)

        cmd = [
            binary,
            f"--remote-debugging-port={self.port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1366,768",
            "about:blank",
        ]
        if headless:
            cmd.insert(1, "--disable-gpu")
            cmd.insert(1, "--headless=new")

        log(f"Starting Chrome ({'headless' if headless else 'GUI'}) on port {self.port}…")
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as e:
            return {
                "ok": False,
                "port": self.port,
                "launched": False,
                "message": f"Failed to launch Chrome: {e}",
            }

        deadline = time.time() + max(3.0, timeout_s)
        http_up = False
        while time.time() < deadline:
            if self.cdp_reachable():
                http_up = True
                # Wait until a real page target exists (extensions-only is not enough)
                if self._ensure_page_target() and self.connect(self.port):
                    return {
                        "ok": True,
                        "port": self.port,
                        "launched": True,
                        "headless": headless,
                        "message": f"Chrome launched; CDP connected on {self.port}",
                    }
            time.sleep(0.4)

        if http_up:
            # Last attempt — maps skill can still use HTTP CDP even if WS attach failed
            self._ensure_page_target()
            self.connect(self.port)
            return {
                "ok": bool(self.is_connected() or self.cdp_reachable()),
                "port": self.port,
                "launched": True,
                "headless": headless,
                "message": (
                    f"Chrome HTTP up on {self.port}"
                    + ("; WS connected" if self.is_connected() else "; WS attach pending")
                ),
            }

        return {
            "ok": False,
            "port": self.port,
            "launched": True,
            "headless": headless,
            "message": (
                f"Chrome launch timed out waiting for port {self.port}. "
                "Try: python launch-chrome.py"
            ),
        }

    def _ensure_page_target(self) -> bool:
        """Return True if a type=page target exists; create about:blank if needed."""
        if not requests:
            return False
        try:
            tabs = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=2).json()
            if any(t.get("type") == "page" for t in tabs):
                return True
            # Open a blank page via CDP HTTP endpoint
            try:
                requests.put(
                    f"http://127.0.0.1:{self.port}/json/new?about:blank",
                    timeout=3,
                )
            except Exception:
                requests.get(
                    f"http://127.0.0.1:{self.port}/json/new?about:blank",
                    timeout=3,
                )
            tabs = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=2).json()
            return any(t.get("type") == "page" for t in tabs)
        except Exception as e:
            logger.debug("ensure page target failed: %s", e)
            return False

    def disconnect(self) -> None:
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None

    def _next_cmd_id(self) -> int:
        with self._lock:
            self._cmd_counter += 1
            return self._cmd_counter

    def _record_cdp(self, method: str, params: Optional[Dict], result: Any, error: str = "") -> None:
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "tab": self.active_tab_id,
            "method": method,
            "params": _clip_for_log(params or {}),
            "result": _clip_for_log(result),
            "error": error,
        }
        self.cdp_log.append(entry)
        if len(self.cdp_log) > self._log_limit:
            self.cdp_log = self.cdp_log[-self._log_limit :]

    def _send_cdp(self, method: str, params: Optional[Dict] = None, timeout: float = 8.0) -> Optional[Dict]:
        """Send CDP command and await response."""
        if not self.ws:
            return None
        cmd_id = self._next_cmd_id()
        payload = {"id": cmd_id, "method": method, "params": params or {}}
        # Socket recv timeout defaults to 5s on connect — far too short for
        # awaitPromise Maps scripts (scroll/enrich). Align sock timeout with
        # the command deadline so quiet periods during JS sleep don't kill WS.
        prev_sock_timeout = None
        try:
            prev_sock_timeout = self.ws.gettimeout()
            self.ws.settimeout(max(float(timeout), 5.0) + 2.0)
        except Exception:
            pass
        try:
            self.ws.send(json.dumps(payload))
            start_t = time.time()
            while time.time() - start_t < timeout:
                raw = self.ws.recv()
                data = json.loads(raw)
                if data.get("id") == cmd_id:
                    if "error" in data:
                        self._record_cdp(method, params, None, str(data["error"]))
                        return None
                    result = data.get("result")
                    self._record_cdp(method, params, result)
                    return result
        except Exception as e:
            logger.debug(f"CDP send error: {e}")
            self._record_cdp(method, params, None, str(e))
            self.disconnect()
        finally:
            if prev_sock_timeout is not None and self.ws is not None:
                try:
                    self.ws.settimeout(prev_sock_timeout)
                except Exception:
                    pass
        return None

    def list_tabs(self) -> List[Dict[str, Any]]:
        """List page tabs on the debug port."""
        if not requests:
            return []
        try:
            tabs = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=3).json()
            out = []
            for i, t in enumerate(tabs):
                if t.get("type") != "page":
                    continue
                out.append({
                    "index": len(out),
                    "id": t.get("id"),
                    "title": t.get("title", ""),
                    "url": t.get("url", ""),
                    "ws": t.get("webSocketDebuggerUrl", ""),
                })
            return out
        except Exception as e:
            logger.debug(f"list_tabs failed: {e}")
            return []

    def create_tab(self, url: str = "about:blank") -> Optional[Dict[str, Any]]:
        """Open a new tab via CDP HTTP endpoint and optionally attach."""
        if not requests:
            return None
        if url and not url.startswith("http") and url != "about:blank":
            url = "https://" + url
        try:
            # Prefer /json/new?{url} (Chromium)
            r = requests.put(f"http://127.0.0.1:{self.port}/json/new?{url}", timeout=5)
            if r.status_code >= 400:
                r = requests.get(f"http://127.0.0.1:{self.port}/json/new?{url}", timeout=5)
            tab = r.json()
            if isinstance(tab, dict) and tab.get("id"):
                return {
                    "id": tab.get("id"),
                    "title": tab.get("title", ""),
                    "url": tab.get("url", url),
                    "ws": tab.get("webSocketDebuggerUrl", ""),
                }
        except Exception as e:
            logger.debug(f"create_tab failed: {e}")
        return None

    def attach_tab(self, tab: Union[int, str]) -> bool:
        """Attach WS to a tab by index or id. Disconnects current first."""
        if not requests or not websocket:
            return False
        tabs = self.list_tabs()
        target = None
        if isinstance(tab, int) or (isinstance(tab, str) and tab.isdigit()):
            idx = int(tab)
            for t in tabs:
                if t["index"] == idx:
                    target = t
                    break
        else:
            for t in tabs:
                if t["id"] == tab or (tab and tab in (t.get("url") or "")):
                    target = t
                    break
        if not target or not target.get("ws"):
            return False
        self.disconnect()
        try:
            self.active_tab_id = target["id"]
            self.active_title = target.get("title", "")
            self.active_url = target.get("url", "")
            self.ws_url = target["ws"]
            self.ws = websocket.create_connection(self.ws_url, timeout=5)
            try:
                self.ws.settimeout(120)
            except Exception:
                pass
            self._send_cdp("Runtime.enable")
            self._send_cdp("Page.enable")
            self._send_cdp("Accessibility.enable")
            return True
        except Exception as e:
            logger.debug(f"attach_tab failed: {e}")
            self.ws = None
            return False

    def evaluate_js(self, script: str, timeout: float = 30.0) -> Any:
        """Run JavaScript in current tab and return value."""
        res = self._send_cdp(
            "Runtime.evaluate",
            {"expression": script, "returnByValue": True, "awaitPromise": True},
            timeout=timeout,
        )
        if res and "exceptionDetails" in res:
            return None
        if res and "result" in res:
            return res["result"].get("value")
        return None

    def navigate(self, url: str) -> bool:
        """Navigate Chrome to URL."""
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        if self.is_connected():
            res = self._send_cdp("Page.navigate", {"url": url})
            time.sleep(1.5)
            return res is not None
        return False

    def fetch(self, url: Optional[str] = None) -> PageSnapshot:
        """Fetch current page or navigate to URL."""
        if url and self.is_connected():
            self.navigate(url)

        if self.is_connected():
            return self._fetch_cdp()
        elif url:
            return self._fetch_http(url)
        else:
            return PageSnapshot(
                url="",
                title="Browser Not Connected",
                text="Chrome CDP is not connected and no URL was provided.",
                source="cdp",
            )

    def _fetch_cdp(self) -> PageSnapshot:
        """Extract DOM structure, text, and interactive elements via CDP."""
        script = """
        (() => {
            const interactives = [];
            let idx = 1;
            const els = document.querySelectorAll('button, a[href], input, textarea, select, [role="button"]');
            els.forEach(el => {
                const rect = el.getBoundingClientRect();
                const visible = rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).display !== 'none';
                if (!visible) return;

                let selector = el.tagName.toLowerCase();
                if (el.id) {
                    selector += '#' + el.id;
                } else if (el.name) {
                    selector += `[name="${el.name}"]`;
                } else if (el.className && typeof el.className === 'string') {
                    const firstClass = el.className.trim().split(/\\s+/)[0];
                    if (firstClass) selector += '.' + firstClass;
                }

                const text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim();
                const href = el.getAttribute('href') || '';

                interactives.push({
                    idx: idx++,
                    tag: el.tagName.toLowerCase(),
                    text: text.slice(0, 60),
                    href: href.slice(0, 80),
                    selector: selector,
                    id: el.id || '',
                    type: el.type || ''
                });
            });

            return {
                url: window.location.href,
                title: document.title,
                text: (document.body ? document.body.innerText : '').slice(0, 4000),
                interactives: interactives.slice(0, 30)
            };
        })()
        """
        data = self.evaluate_js(script) or {}
        snapshot = PageSnapshot(
            url=data.get("url", self.active_url),
            title=data.get("title", self.active_title),
            text=data.get("text", ""),
            interactives=data.get("interactives", []),
            source="cdp",
        )
        self.last_snapshot = snapshot
        return snapshot

    def _fetch_http(self, url: str) -> PageSnapshot:
        """Direct HTTP scrape using urllib."""
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Linux; Android 10) Termux/Agent 1.0"},
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                html_data = response.read().decode(charset, errors="replace")
                code = response.getcode()

            parser = HTMLTextExtractor()
            parser.feed(html_data)

            title_match = re.search(r"<title[^>]*>(.*?)</title>", html_data, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else url

            interactives = []
            for i, link in enumerate(parser.links[:25], 1):
                interactives.append({
                    "idx": i,
                    "tag": "a",
                    "text": link["text"][:50],
                    "href": link["href"],
                    "selector": f"a[href='{link['href']}']",
                })

            snapshot = PageSnapshot(
                url=url,
                title=title,
                text=parser.get_text(),
                interactives=interactives,
                status_code=code,
                source="http",
            )
            self.last_snapshot = snapshot
            return snapshot
        except Exception as e:
            return PageSnapshot(
                url=url,
                title="Fetch Error",
                text=f"Failed to fetch {url}: {e}",
                status_code=500,
                source="http",
            )

    def click(self, target: Union[int, str]) -> Dict[str, Any]:
        """Click element by index, selector, or text."""
        if not self.is_connected():
            return {"success": False, "error": "Chrome CDP not connected"}

        # If target is integer index from last snapshot
        selector = None
        if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
            idx = int(target)
            if self.last_snapshot and self.last_snapshot.interactives:
                for el in self.last_snapshot.interactives:
                    if el.get("idx") == idx:
                        selector = el.get("selector")
                        break
            if not selector:
                return {"success": False, "error": f"No interactive element at index {idx}"}

        if not selector and isinstance(target, str):
            selector = target

        if not selector:
            return {"success": False, "error": "No click target resolved"}

        script = f"""
        (() => {{
            let target = '{selector.replace("'", "\\'")}';
            let el = document.querySelector(target);
            if (!el) {{
                // Search by text
                const buttons = document.querySelectorAll('button, a, [role="button"]');
                for (let b of buttons) {{
                    if ((b.innerText || '').trim().toLowerCase().includes(target.toLowerCase())) {{
                        el = b;
                        break;
                    }}
                }}
            }}
            if (el) {{
                el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                el.click();
                return {{ success: true, text: (el.innerText || '').slice(0, 40) }};
            }}
            return {{ success: false, error: 'Element not found: ' + target }};
        }})()
        """
        res = self.evaluate_js(script) or {"success": False, "error": "Evaluation failed"}
        time.sleep(1.0)
        return res

    def type_text(self, selector: str, text: str) -> Dict[str, Any]:
        """Type text into input field."""
        if not self.is_connected():
            return {"success": False, "error": "Chrome CDP not connected"}

        escaped_text = text.replace("'", "\\'").replace("\n", "\\n")
        escaped_sel = selector.replace("'", "\\'")
        script = f"""
        (() => {{
            let el = document.querySelector('{escaped_sel}');
            if (!el) {{
                const inputs = document.querySelectorAll('input, textarea');
                for (let inp of inputs) {{
                    if ((inp.placeholder || '').toLowerCase().includes('{escaped_sel.lower()}') ||
                        (inp.name || '').toLowerCase().includes('{escaped_sel.lower()}')) {{
                        el = inp;
                        break;
                    }}
                }}
            }}
            if (el) {{
                el.focus();
                el.value = '{escaped_text}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return {{ success: true }};
            }}
            return {{ success: false, error: 'Input field not found: {escaped_sel}' }};
        }})()
        """
        return self.evaluate_js(script) or {"success": False, "error": "Evaluation failed"}

    def get_ax_tree(self, max_nodes: int = 80) -> Dict[str, Any]:
        """Fetch Accessibility.getFullAXTree and return a compact role/name index."""
        if not self.is_connected():
            return {"ok": False, "error": "Chrome CDP not connected"}
        self._send_cdp("Accessibility.enable")
        raw = self._send_cdp("Accessibility.getFullAXTree", timeout=15.0)
        if not raw:
            return {"ok": False, "error": "Accessibility.getFullAXTree failed"}
        nodes = raw.get("nodes") or []
        compact = []
        role_counts: Dict[str, int] = {}
        for n in nodes:
            role = (n.get("role") or {}).get("value") or "unknown"
            name = (n.get("name") or {}).get("value") or ""
            role_counts[role] = role_counts.get(role, 0) + 1
            # Keep interactive / named landmarks useful for Maps & forms
            if role in (
                "button", "link", "textbox", "searchbox", "combobox",
                "list", "listitem", "article", "feed", "heading",
                "menuitem", "tab", "option",
            ) or (name and role in ("generic", "StaticText", "text")):
                compact.append({
                    "role": role,
                    "name": str(name)[:80],
                    "backendDOMNodeId": n.get("backendDOMNodeId"),
                    "ignored": bool(n.get("ignored")),
                })
            if len(compact) >= max_nodes:
                break
        return {
            "ok": True,
            "total_nodes": len(nodes),
            "role_counts": dict(sorted(role_counts.items(), key=lambda x: -x[1])[:20]),
            "interesting": compact,
        }

    def find_ax(self, query: str, limit: int = 15) -> Dict[str, Any]:
        """Filter AX nodes by role or name substring (case-insensitive)."""
        tree = self.get_ax_tree(max_nodes=200)
        if not tree.get("ok"):
            return tree
        q = (query or "").strip().lower()
        hits = []
        for n in tree.get("interesting", []):
            blob = f"{n.get('role', '')} {n.get('name', '')}".lower()
            if not q or q in blob:
                hits.append(n)
            if len(hits) >= limit:
                break
        return {"ok": True, "query": query, "count": len(hits), "nodes": hits}

    def test_css(self, selector: str, limit: int = 8) -> Dict[str, Any]:
        """Probe a CSS selector in-page (count + sample text/attrs)."""
        if not self.is_connected():
            return {"ok": False, "error": "Chrome CDP not connected"}
        if not selector or not selector.strip():
            return {"ok": False, "error": "selector required"}
        escaped = json.dumps(selector)
        script = f"""
        (() => {{
            const sel = {escaped};
            let els;
            try {{ els = document.querySelectorAll(sel); }}
            catch (e) {{ return {{ ok: false, error: String(e), selector: sel }}; }}
            const samples = [];
            for (let i = 0; i < Math.min(els.length, {int(limit)}); i++) {{
                const el = els[i];
                samples.push({{
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    className: (typeof el.className === 'string' ? el.className : '').slice(0, 80),
                    text: (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 80),
                    href: (el.getAttribute && el.getAttribute('href')) || '',
                    role: el.getAttribute('role') || '',
                }});
            }}
            return {{ ok: true, selector: sel, match_count: els.length, samples }};
        }})()
        """
        return self.evaluate_js(script) or {"ok": False, "error": "evaluate failed"}

    def run_jev(self, schema: Dict[str, Any], extractor_js: str) -> Dict[str, Any]:
        """
        Typesafe JEV: run extractor JS, then validate result against a simple schema.

        Schema format (JSON-like):
          {"type":"object","required":["ok","data"],"properties":{
             "ok":{"type":"boolean"},
             "data":{"type":"array","items":{"type":"object","required":["name"]}}
          }}
        extractor_js must be an expression returning a value (or IIFE).
        """
        if not self.is_connected():
            return {"ok": False, "errors": ["Chrome CDP not connected"], "data": None}
        raw = self.evaluate_js(extractor_js)
        errors = _validate_against_schema(raw, schema, path="$")
        return {
            "ok": len(errors) == 0,
            "errors": errors,
            "data": raw,
            "schema_keys": list((schema or {}).get("properties", {}).keys()),
        }

    def run_library_script(
        self,
        relative_path: str,
        args: Optional[Dict[str, Any]] = None,
        timeout: float = 120.0,
    ) -> Any:
        """Execute a JS file from scripts-library/ via Runtime.evaluate.

        Injects ``%%ARGS%%`` as JSON (api_sop style) so scripts can take params.
        """
        if not self.is_connected():
            return {"ok": False, "error": "Chrome CDP not connected"}
        rel = relative_path.strip().lstrip("/")
        if not rel.endswith(".js"):
            rel = rel + ".js"
        path = os.path.join(SCRIPTS_DIR, rel)
        if not os.path.isfile(path):
            alt = os.path.join(SCRIPTS_DIR, relative_path)
            if os.path.isfile(alt):
                path = alt
            else:
                return {"ok": False, "error": f"script not found: {rel}"}
        with open(path, encoding="utf-8") as f:
            code = f.read()
        if "%%ARGS%%" in code:
            code = code.replace("%%ARGS%%", json.dumps(args or {}))
        # Scripts are often async IIFEs — awaitPromise handles them
        res = self._send_cdp(
            "Runtime.evaluate",
            {"expression": code, "returnByValue": True, "awaitPromise": True},
            timeout=timeout,
        )
        if res and "exceptionDetails" in res:
            ed = res.get("exceptionDetails") or {}
            exc = (ed.get("exception") or {}).get("description") or ed.get("text") or "JS exception"
            return {"ok": False, "error": f"script exception: {exc}", "raw": _clip_for_log(res)}
        if res and "result" in res:
            val = res["result"].get("value")
            if val is not None:
                return val
            # subtype error / undefined with no value
            desc = res["result"].get("description") or res["result"].get("type")
            return {"ok": False, "error": f"script returned no value ({desc})", "raw": _clip_for_log(res)}
        return {"ok": False, "error": "script evaluation failed", "raw": _clip_for_log(res)}


def _validate_against_schema(value: Any, schema: Optional[Dict], path: str) -> List[str]:
    """Minimal JSON-schema subset validator for typesafe JEV."""
    if not schema:
        return []
    errors: List[str] = []
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected object, got {type(value).__name__}"]
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}: missing required '{req}'")
        props = schema.get("properties") or {}
        for key, sub in props.items():
            if key in value:
                errors.extend(_validate_against_schema(value[key], sub, f"{path}.{key}"))
    elif expected == "array":
        if not isinstance(value, list):
            return [f"{path}: expected array, got {type(value).__name__}"]
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value[:50]):
                errors.extend(_validate_against_schema(item, item_schema, f"{path}[{i}]"))
    elif expected == "string":
        if not isinstance(value, str):
            errors.append(f"{path}: expected string")
    elif expected == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{path}: expected number")
    elif expected == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{path}: expected boolean")
    elif expected == "null":
        if value is not None:
            errors.append(f"{path}: expected null")
    return errors


# Default schema for Maps card extracts
MAPS_CARD_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["ok", "data"],
    "properties": {
        "ok": {"type": "boolean"},
        "count": {"type": "number"},
        "data": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "address": {"type": "string"},
                    "maps_url": {"type": "string"},
                    "phone": {"type": "string"},
                    "rating": {"type": "number"},
                },
            },
        },
    },
}


# ============================================================================
# 3. HAR MANAGER (CDP Network Capture Engine)
# ============================================================================

class HarManager:
    """
    Background HAR network capture based on quick_capture_har_1.py.
    Intercepts CDP Network domain events and compiles them into standard HAR 1.2 format.
    """

    def __init__(self, port: int = 9222):
        self.port = port
        self.is_capturing: bool = False
        self.entries: List[Dict[str, Any]] = []
        self.pending_requests: Dict[str, Dict[str, Any]] = {}
        self.start_time: Optional[datetime] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ws: Optional[Any] = None
        self._lock = threading.Lock()
        self.domains_seen: Set[str] = set()

    def start_capture(self, port: Optional[int] = None) -> bool:
        """Start capturing network requests in a background thread."""
        if self.is_capturing:
            return True
        if port:
            self.port = port
        if not requests or not websocket:
            return False

        try:
            r = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=2)
            tabs = [t for t in r.json() if t.get("type") == "page"]
            if not tabs:
                return False
            ws_url = tabs[0].get("webSocketDebuggerUrl")
            if not ws_url:
                return False

            self.entries.clear()
            self.pending_requests.clear()
            self.domains_seen.clear()
            self.start_time = datetime.now()
            self._stop_event.clear()
            self.is_capturing = True

            self._thread = threading.Thread(
                target=self._capture_loop,
                args=(ws_url,),
                daemon=True,
                name="HarCaptureThread",
            )
            self._thread.start()
            return True
        except Exception as e:
            logger.debug(f"Failed to start HAR capture: {e}")
            self.is_capturing = False
            return False

    def _capture_loop(self, ws_url: str) -> None:
        """Background listener reading Network.* CDP messages."""
        try:
            self._ws = websocket.create_connection(ws_url, timeout=5)
            self._ws.send(json.dumps({"id": 100, "method": "Network.enable"}))

            while not self._stop_event.is_set():
                try:
                    self._ws.settimeout(1.0)
                    raw = self._ws.recv()
                    data = json.loads(raw)
                    method = data.get("method", "")
                    params = data.get("params", {})
                    self._process_event(method, params)
                except websocket.WebSocketTimeoutException:
                    continue
                except Exception:
                    break
        except Exception as e:
            logger.debug(f"HAR capture socket error: {e}")
        finally:
            if self._ws:
                try:
                    self._ws.close()
                except Exception:
                    pass
                self._ws = None
            self.is_capturing = False

    def _process_event(self, method: str, params: Dict[str, Any]) -> None:
        """Record network event details."""
        req_id = params.get("requestId")
        if not req_id:
            return

        with self._lock:
            if method == "Network.requestWillBeSent":
                req = params.get("request", {})
                url = req.get("url", "")
                if url.startswith("data:") or url.startswith("blob:"):
                    return
                domain = urlparse(url).netloc
                if domain:
                    self.domains_seen.add(domain)

                self.pending_requests[req_id] = {
                    "startedDateTime": datetime.now().isoformat(),
                    "request": {
                        "method": req.get("method", "GET"),
                        "url": url,
                        "headers": [{"name": k, "value": str(v)} for k, v in req.get("headers", {}).items()],
                        "postData": {"text": req.get("postData", "")} if req.get("postData") else None,
                    },
                    "response": None,
                    "time": 0,
                    "_timestamp": params.get("timestamp", time.time()),
                }

            elif method == "Network.responseReceived":
                if req_id in self.pending_requests:
                    resp = params.get("response", {})
                    self.pending_requests[req_id]["response"] = {
                        "status": resp.get("status", 0),
                        "statusText": resp.get("statusText", ""),
                        "mimeType": resp.get("mimeType", ""),
                        "headers": [{"name": k, "value": str(v)} for k, v in resp.get("headers", {}).items()],
                    }

            elif method == "Network.loadingFinished":
                if req_id in self.pending_requests:
                    entry = self.pending_requests.pop(req_id)
                    end_ts = params.get("timestamp", time.time())
                    dur_ms = max(1.0, (end_ts - entry["_timestamp"]) * 1000)
                    entry["time"] = round(dur_ms, 2)
                    entry.pop("_timestamp", None)
                    if entry.get("response"):
                        self.entries.append(entry)

    def stop_capture(self) -> Dict[str, Any]:
        """Stop capturing and return summary."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self.is_capturing = False
        return self.get_summary()

    def get_summary(self) -> Dict[str, Any]:
        """Return captured stats."""
        with self._lock:
            total_reqs = len(self.entries)
            api_reqs = sum(1 for e in self.entries if "json" in e.get("response", {}).get("mimeType", "").lower())
            domains = list(self.domains_seen)
            dur = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0.0

            return {
                "is_capturing": self.is_capturing,
                "total_requests": total_reqs,
                "api_requests": api_reqs,
                "domains": domains[:8],
                "total_domains": len(domains),
                "duration_seconds": round(dur, 1),
            }

    def save_har(self, filepath: Optional[str] = None) -> Tuple[str, int]:
        """Export captured traffic to standard HAR file."""
        with self._lock:
            if not filepath:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = os.path.join(os.getcwd(), f"capture_{ts}.har")

            har_doc = {
                "log": {
                    "version": "1.2",
                    "creator": {"name": "Termux-Agent HAR Engine", "version": "2.0"},
                    "entries": self.entries,
                }
            }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(har_doc, f, indent=2)

            return filepath, len(self.entries)

    def recent_apis(self, limit: int = 12, url_substr: str = "") -> List[Dict[str, Any]]:
        """Return recent JSON/XHR-like entries for agent prompting / scrape leverage."""
        with self._lock:
            rows = []
            needle = (url_substr or "").lower()
            for e in reversed(self.entries):
                resp = e.get("response") or {}
                mime = (resp.get("mimeType") or "").lower()
                url = (e.get("request") or {}).get("url", "")
                method = (e.get("request") or {}).get("method", "")
                is_api = (
                    "json" in mime
                    or "/api" in url.lower()
                    or "maps.googleapis" in url.lower()
                    or "search?" in url.lower()
                    or "batchexecute" in url.lower()
                )
                if not is_api:
                    continue
                if needle and needle not in url.lower():
                    continue
                rows.append({
                    "method": method,
                    "status": resp.get("status"),
                    "mime": mime,
                    "url": url[:220],
                    "time_ms": e.get("time"),
                })
                if len(rows) >= limit:
                    break
            return rows

    def summary_for_prompt(self, limit: int = 8) -> str:
        stats = self.get_summary()
        lines = [
            f"HAR capturing={stats['is_capturing']} reqs={stats['total_requests']} "
            f"apis={stats['api_requests']} domains={stats['total_domains']}"
        ]
        apis = self.recent_apis(limit=limit)
        if apis:
            lines.append("Recent API-like requests:")
            for a in apis:
                lines.append(f"  [{a.get('status')}] {a.get('method')} {a.get('url')}")
        else:
            lines.append("Recent API-like requests: (none yet — start HAR before Maps search)")
        return "\n".join(lines)


# Prefer production multi-tab / redact / body-aware HAR when mmcp is present.
_LegacyHarManager = HarManager
if HAS_MMCP and ProductionHARCapturer is not None:
    HarManager = ProductionHARCapturer  # type: ignore[misc, assignment]


# ============================================================================
# 4. AGENT MEMORY (user + goals + tasks across runs)
# ============================================================================

class AgentMemory:
    """
    Persistent memory for who the user is, active/past goals, and task outcomes.
    Stored at ~/.llama-tui/agent_memory.json and injected into agent prompts.
    """

    def __init__(self, path: str = MEMORY_PATH):
        self.path = path
        self.data: Dict[str, Any] = {
            "user": {"name": "", "notes": [], "preferences": {}},
            "active_goals": [],
            "goal_history": [],
            "tasks": {},
            "facts": [],
            "run_summaries": [],
            "updated_at": "",
        }
        self.load()

    def load(self) -> None:
        try:
            if os.path.isfile(self.path):
                with open(self.path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    for k, v in loaded.items():
                        self.data[k] = v
        except Exception as e:
            logger.debug(f"memory load failed: {e}")

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            self.data["updated_at"] = datetime.now().isoformat(timespec="seconds")
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, default=str)
        except Exception as e:
            logger.debug(f"memory save failed: {e}")

    def set_user(self, name: str = "", **prefs: Any) -> None:
        if name:
            self.data["user"]["name"] = name.strip()
        if prefs:
            self.data["user"].setdefault("preferences", {}).update(prefs)
        self.save()

    def remember(self, fact: str, kind: str = "fact") -> None:
        fact = (fact or "").strip()
        if not fact:
            return
        entry = {
            "text": fact,
            "kind": kind,
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
        if kind == "note":
            notes = self.data["user"].setdefault("notes", [])
            notes.append(fact)
            self.data["user"]["notes"] = notes[-30:]
        else:
            facts = self.data.setdefault("facts", [])
            if not any(f.get("text") == fact for f in facts):
                facts.append(entry)
            self.data["facts"] = facts[-80:]
        self.save()

    def add_goal(self, text: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {}
        for g in self.data.get("active_goals", []):
            if g.get("text", "").lower() == text.lower():
                g["updated"] = datetime.now().isoformat(timespec="seconds")
                g["status"] = "active"
                self.save()
                return g
        goal = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S"),
            "text": text,
            "status": "active",
            "created": datetime.now().isoformat(timespec="seconds"),
            "updated": datetime.now().isoformat(timespec="seconds"),
            "tags": tags or _infer_goal_tags(text),
        }
        self.data.setdefault("active_goals", []).append(goal)
        self.data["active_goals"] = self.data["active_goals"][-20:]
        self.save()
        return goal

    def complete_goal(self, text_or_id: str, outcome: str = "") -> bool:
        key = (text_or_id or "").strip().lower()
        active = self.data.get("active_goals", [])
        kept = []
        done = None
        for g in active:
            if g.get("id") == text_or_id or g.get("text", "").lower() == key:
                g["status"] = "done"
                g["outcome"] = (outcome or "")[:500]
                g["updated"] = datetime.now().isoformat(timespec="seconds")
                done = g
            else:
                kept.append(g)
        if done:
            self.data["active_goals"] = kept
            hist = self.data.setdefault("goal_history", [])
            hist.append(done)
            self.data["goal_history"] = hist[-40:]
            self.save()
            return True
        return False

    def upsert_task(
        self,
        name: str,
        goal: str = "",
        status: str = "open",
        notes: str = "",
        artifacts: Optional[Any] = None,
    ) -> None:
        name = (name or "").strip()
        if not name:
            return
        tasks = self.data.setdefault("tasks", {})
        cur = tasks.get(name, {})
        cur.update({
            "name": name,
            "goal": goal or cur.get("goal", ""),
            "status": status,
            "notes": notes or cur.get("notes", ""),
            "last_run": datetime.now().isoformat(timespec="seconds"),
        })
        if artifacts is not None:
            cur["artifacts"] = artifacts
        tasks[name] = cur
        self.data["tasks"] = dict(list(tasks.items())[-30:])
        self.save()

    def record_run(
        self,
        goal: str,
        run_id: str,
        summary: str,
        extracted: Optional[Dict] = None,
        steps: int = 0,
    ) -> None:
        digest = {
            "run_id": run_id,
            "goal": goal,
            "summary": (summary or "")[:400],
            "steps": steps,
            "extracted_keys": list((extracted or {}).keys()),
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
        runs = self.data.setdefault("run_summaries", [])
        runs.append(digest)
        self.data["run_summaries"] = runs[-25:]
        self.add_goal(goal)
        if extracted:
            for k, v in extracted.items():
                n = len(v) if isinstance(v, list) else 1
                self.remember(
                    f"Run {run_id} extracted {k} ({n} items) for: {goal}",
                    kind="fact",
                )
        self.save()

    def related_context(self, goal: str, limit: int = 6) -> str:
        g = (goal or "").lower()
        tags = set(_infer_goal_tags(goal))
        hits: List[str] = []
        words = [w for w in g.split() if len(w) > 3]

        for fact in reversed(self.data.get("facts", [])):
            text = fact.get("text", "")
            tl = text.lower()
            if any(t in tl for t in tags) or any(w in tl for w in words):
                hits.append(f"fact: {text}")
            if len(hits) >= limit:
                break

        for name, task in self.data.get("tasks", {}).items():
            blob = f"{name} {task.get('goal', '')} {task.get('notes', '')}".lower()
            if tags & set(_infer_goal_tags(blob)) or any(w in blob for w in words):
                hits.append(
                    f"task[{name}]: {task.get('status')} — "
                    f"{task.get('goal') or task.get('notes')}"
                )

        for past in reversed(self.data.get("run_summaries", [])):
            pg = (past.get("goal") or "").lower()
            if any(w in pg for w in words):
                hits.append(f"past_run: {past.get('goal')} → {past.get('summary')}")
            if len(hits) >= limit:
                break

        return "\n".join(f"  - {h}" for h in hits[:limit]) or "  - (no related memory yet)"

    def prompt_block(self, current_goal: str = "") -> str:
        user = self.data.get("user") or {}
        name = user.get("name") or "(unknown — set with /remember name=...)"
        prefs = user.get("preferences") or {}
        pref_s = ", ".join(f"{k}={v}" for k, v in list(prefs.items())[:6]) or "(none)"
        notes = user.get("notes") or []
        note_s = "; ".join(notes[-3:]) if notes else "(none)"

        active = self.data.get("active_goals") or []
        active_lines = "\n".join(
            f"  [{g.get('id')}] {g.get('text')} tags={g.get('tags')}"
            for g in active[-5:]
        ) or "  (none)"

        tasks = self.data.get("tasks") or {}
        task_lines = "\n".join(
            f"  - {n}: {t.get('status')} | {t.get('goal') or t.get('notes') or ''}"
            for n, t in list(tasks.items())[-6:]
        ) or "  (none)"

        related = self.related_context(current_goal) if current_goal else "  - (n/a)"
        return (
            f"USER MEMORY:\n"
            f"  name: {name}\n"
            f"  prefs: {pref_s}\n"
            f"  notes: {note_s}\n"
            f"ACTIVE GOALS:\n{active_lines}\n"
            f"KNOWN TASKS:\n{task_lines}\n"
            f"RELATED TO THIS GOAL:\n{related}"
        )

    def summary_text(self) -> str:
        return self.prompt_block()


def _infer_goal_tags(text: str) -> List[str]:
    low = (text or "").lower()
    mapping = {
        "maps": (
            "maps", "google maps", "scrape", "scrap", "pharmacy", "pharmacies",
            "hedge", "places", "location",
        ),
        "gujarat": ("gujarat", "gujrat"),
        "pincode": ("pincode", "pin code", "postal"),
        "pharmacy": ("pharmacy", "pharmacies", "chemist", "medical"),
        "hinjewadi": ("hinjewadi", "hinjawadi", "pune"),
        "har": ("har", "network", "traffic", "api"),
        "cdp": ("cdp", "browser", "chrome"),
    }
    tags = [tag for tag, keys in mapping.items() if any(k in low for k in keys)]
    return tags or ["general"]


# ============================================================================
# 5. ORCHESTRATOR AGENT (Reasoning & Tool Execution Loop)
# ============================================================================

class OrchestratorAgent:
    """
    Coordinates reasoning, web perception, and network recording.
    Supports multi-tab CDP, AX/CSS/JEV, HAR, and persistent user/goal memory.
    """

    def __init__(
        self,
        llm_fn: Callable[[str], str],
        page_fetcher: PageFetcher,
        har_manager: HarManager,
        ui_callback: Optional[Callable[[str, Any], None]] = None,
        memory: Optional[AgentMemory] = None,
    ):
        self.llm_fn = llm_fn
        self.fetcher = page_fetcher
        self.har = har_manager
        self.ui_callback = ui_callback
        self.memory = memory or AgentMemory()
        self.stop_requested = False
        self.current_goal: str = ""
        self.history: List[Dict[str, Any]] = []
        self.tasks: Dict[str, Dict[str, Any]] = {}  # named parallel tab tasks
        self.extracted: Dict[str, Any] = {}
        self.run_id: str = ""
        self.run_path: str = ""

    def stop(self) -> None:
        self.stop_requested = True

    def _get_db(self):
        """Lazily create/return a Database instance for places persistence."""
        if not hasattr(self, "_db") or self._db is None:
            try:
                from agent.database import Database
                from agent.config import AgentConfig
                cfg = AgentConfig.from_env()
                self._db = Database(cfg.db_path)
            except Exception:
                self._db = None
        return self._db

    def _mmcp_tool_executor(self) -> Callable[[str, Dict[str, Any]], Dict[str, Any]]:
        """Bridge mmcp workflow tool names → OrchestratorAgent.execute_action."""

        def _exec(tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
            name = (tool or "").strip().lower()
            if name in ("finish", "done"):
                return {"done": True, "answer": args.get("answer") or args.get("summary") or ""}
            if name == "har_start":
                ok = self.har.start_capture(self.fetcher.port)
                return {"ok": ok, "summary": self.har.get_summary()}
            if name == "har_stop":
                return {"ok": True, "summary": self.har.stop_capture()}
            if name == "har_save":
                path, n = self.har.save_har(args.get("filepath"))
                return {"ok": True, "filepath": path, "entries": n}
            if name == "har_analyze":
                obs = self.execute_action("har_analyze", str(args.get("filepath") or ""))
                return {"ok": True, "observation": obs}
            if name == "har_apis":
                rows = self.har.recent_apis(limit=15, url_substr=str(args.get("substr") or ""))
                return {"ok": True, "apis": rows}
            if name == "browser_navigate":
                url = str(args.get("url") or "")
                return {"ok": True, "observation": self.execute_action("fetch", url)}
            if name == "browser_get_content":
                snap = self.fetcher.fetch()
                return {"ok": True, "summary": snap.summary(max_text_chars=800)}
            # Fall through to native action names
            arg = args.get("arg") or args.get("url") or args.get("selector") or ""
            if isinstance(arg, dict):
                arg = json.dumps(arg)
            obs = self.execute_action(name, str(arg))
            return {"ok": True, "observation": obs}

        return _exec

    def _notify(self, event_type: str, data: Any) -> None:
        if self.ui_callback:
            try:
                self.ui_callback(event_type, data)
            except Exception as e:
                logger.debug(f"UI callback error: {e}")

    def _append_run_log(self, record: Dict[str, Any]) -> None:
        if not self.run_path:
            return
        try:
            with open(self.run_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as e:
            logger.debug(f"run log write failed: {e}")

    def plan_tasks_for_goal(self, goal: str) -> List[Dict[str, str]]:
        """Heuristic task split for Maps-style geo scrapes (pincodes ∥ maps)."""
        if HAS_SKILLS and SkillsPipeline is not None:
            pipe = SkillsPipeline(pincode_csv=DEFAULT_PINCODE_CSV)
            if pipe.can_handle(goal):
                return pipe.decision.build(goal, dry_run=True).as_plan_tasks()
        g = goal.lower()
        tasks = []
        if any(k in g for k in ("gujarat", "gujrat", "pincode", "pin code", "maps", "scrape", "scrap", "hedge", "phone")):
            tasks.append({
                "name": "pincodes",
                "goal": f"Load pincode CSV ({DEFAULT_PINCODE_CSV}) for geo coverage",
                "hint_url": f"file://{DEFAULT_PINCODE_CSV}",
            })
            q = "hedge funds"
            for token in ("hedge fund", "hedge funds", "pharmacy", "pharmacies", "vc", "startup"):
                if token in g:
                    q = token if not token.endswith("ies") else "pharmacy"
                    break
            region = "Gujarat" if ("gujarat" in g or "gujrat" in g) else "India"
            maps_q = quote_plus(f"{q} in {region}")
            tasks.append({
                "name": "maps",
                "goal": f"Open Google Maps and scrape results for: {q} in {region}",
                "hint_url": f"https://www.google.com/maps/search/{maps_q}",
            })
        return tasks

    def should_use_skills(self, goal: str) -> bool:
        """Prefer skills (not LLM) for Maps / phone / geo scrape goals."""
        if not HAS_SKILLS or SkillsPipeline is None:
            return False
        # Explicit override
        low = (goal or "").lower()
        if "use llm" in low or "llm mode" in low:
            return False
        pipe = SkillsPipeline(pincode_csv=DEFAULT_PINCODE_CSV)
        return pipe.can_handle(goal)

    def run_goal_with_skills(self, goal: str, dry_run: bool = True) -> str:
        """Deterministic skill pipeline — DecisionBuilder → Pincodes → MapsGeo."""
        if not HAS_SKILLS or SkillsPipeline is None:
            return "Skills pipeline unavailable"

        pipe = SkillsPipeline(
            page_fetcher=self.fetcher,
            har_manager=self.har,
            notify=self._notify,
            pincode_csv=DEFAULT_PINCODE_CSV,
            db=self._get_db(),
        )
        result = pipe.run(goal, dry_run=dry_run)
        self.extracted.update(result.get("extracted") or {})
        self.memory.upsert_task(
            "pincodes",
            goal=f"CSV {DEFAULT_PINCODE_CSV}",
            status="done",
            notes=str((result.get("pincodes") or {}).get("filtered")),
            artifacts={"sample": (result.get("pincodes") or {}).get("sample_pins")},
        )
        decision = result.get("decision") or {}
        stopped = bool(result.get("stopped"))
        stop_reason = result.get("stop_reason") or ""
        maps_status = (
            "dry" if dry_run else ("stopped" if stopped and not (self.extracted.get("maps_cards")) else "done")
        )
        self.memory.upsert_task(
            "maps",
            goal=goal,
            status=maps_status,
            notes=result.get("summary", "") + (f" | {stop_reason}" if stop_reason else ""),
            artifacts={
                "decision": decision,
                "extract_path": result.get("extract_path"),
                "selectors": (result.get("extracted") or {}).get("selectors"),
                "stop_reason": stop_reason or None,
            },
        )
        pin_n = (result.get("pincodes") or {}).get("filtered")
        self.memory.remember(
            f"pincode_csv={DEFAULT_PINCODE_CSV}; "
            f"query={decision.get('query')!r} state={decision.get('state')!r} "
            f"city={decision.get('city')!r} pins={pin_n}",
            kind="fact",
        )
        suggested_cron = decision.get("suggested_cron") or ""
        if suggested_cron:
            self.memory.upsert_task(
                "cron",
                goal=goal,
                status="suggested",
                notes=f"{decision.get('cron_label')}: {suggested_cron}",
                artifacts={"cron_expr": suggested_cron, "goal": goal},
            )
            self.memory.remember(
                f"cron_hint for '{goal[:80]}' → {suggested_cron}",
                kind="fact",
            )
        self.memory.set_user(pincode_csv=DEFAULT_PINCODE_CSV)
        summary = result.get("summary") or "skills done"
        if dry_run and not (self.extracted.get("maps_cards") or self.extracted.get("phones")):
            summary += (
                " | NOT SCRAPED — dry plan only. "
                "Re-run the same goal (Chrome will auto-start), or add 'live', "
                "or: python launch-chrome.py"
            )
        if suggested_cron:
            summary += f" | cron_hint={suggested_cron} (F8 to add)"
        self.memory.record_run(
            goal=goal,
            run_id=self.run_id,
            summary=summary,
            extracted=self.extracted,
            steps=len(decision.get("steps") or []),
        )
        self._notify(
            "agent_finished",
            {
                "goal": goal,
                "summary": summary,
                "run_id": self.run_id,
                "run_path": self.run_path,
                "extracted": self.extracted,
                "mode": "skills",
                "dry_run": dry_run,
                "decision": decision,
                "suggested_cron": suggested_cron,
                "stopped": stopped,
                "stop_reason": stop_reason or None,
                "extract_path": result.get("extract_path"),
                "ok": result.get("ok", True),
            },
        )
        self._append_run_log({"event": "skills_result", **{k: v for k, v in result.items() if k != "extracted"}})
        self._append_run_log({
            "event": "finished",
            "summary": summary,
            "mode": "skills",
            "stopped": stopped,
            "stop_reason": stop_reason or None,
            "ok": result.get("ok", True),
        })
        return summary

    def build_agent_prompt(self, goal: str, step: int, max_steps: int) -> str:
        """Formulate compact system prompt + current state for local LLM."""
        snapshot = self.fetcher.last_snapshot or self.fetcher.fetch()
        har_block = self.har.summary_for_prompt(limit=6)
        tabs = self.fetcher.list_tabs()
        tab_lines = "\n".join(
            f"  [{t['index']}] {t['title'][:40]} | {t['url'][:60]}" for t in tabs[:6]
        ) or "  (no tabs)"
        task_lines = "\n".join(
            f"  - {n}: tab={meta.get('tab_id')} status={meta.get('status')}"
            for n, meta in self.tasks.items()
        ) or "  (none — use assign_task)"

        recent = ""
        if self.history:
            last = self.history[-1]
            recent = (
                f"\nLAST STEP: {last.get('action')}\n"
                f"LAST OBS: {str(last.get('observation', ''))[:350]}"
            )

        prompt = f"""<|system|>
You are an autonomous multi-tab CDP browser agent.
GOAL: {goal}
STEP: {step} of {max_steps}
CURRENT PAGE: {snapshot.title} ({snapshot.url})
{har_block}

OPEN TABS:
{tab_lines}

ASSIGNED TASKS:
{task_lines}
{recent}

TOOLS (pick ONE per step):
- ACTION: assign_task <name>|<url>     # open URL in a NEW tab and name it (e.g. pincodes|https://...)
- ACTION: switch_task <name_or_index> # attach CDP to that tab
- ACTION: fetch <url>
- ACTION: click <idx_or_selector>
- ACTION: type <selector> <text>
- ACTION: ax_find <role_or_name>      # Accessibility tree probe
- ACTION: css_test <selector>         # CSS match probe (Maps: div[role=feed], a.hfpxzc)
- ACTION: jev_maps                    # run typesafe Maps card JEV / library scroll scrape
- ACTION: run_script <path>           # scripts-library JS e.g. google-maps/get-cards-via-scroll
- ACTION: har_start | har_stop | har_save | har_apis [substr] | har_analyze [path]
- ACTION: mmcp_run <goal>             # LangGraph multi-model workflow (when mmcp installed)
- ACTION: finish <answer>

STRATEGY for geo Maps scrapes:
1) har_start
2) assign_task pincodes|<pincode source url>
3) assign_task maps|https://www.google.com/maps/search/...
4) switch_task maps → ax_find searchbox/feed → css_test → jev_maps
5) Use HAR APIs when Maps XHR appears; finish with structured findings

PAGE SUMMARY:
{snapshot.summary(max_text_chars=500)}

Respond strictly:
THOUGHT: <one sentence>
ACTION: <tool call>
</s>
<|user|>
Next step for: {goal}
</s>
<|assistant|>
"""
        return prompt

    def parse_action(self, text: str) -> Tuple[str, str, str]:
        """Extract THOUGHT and ACTION from LLM output."""
        thought = ""
        action_name = ""
        action_arg = ""

        t_match = re.search(r"THOUGHT:\s*(.*?)(?=\n|ACTION:|$)", text, re.IGNORECASE | re.DOTALL)
        if t_match:
            thought = t_match.group(1).strip()

        a_match = re.search(r"ACTION:\s*([a-zA-Z_]+)(?:\s+(.*?))?(?:\n|$)", text, re.IGNORECASE)
        if a_match:
            action_name = a_match.group(1).strip().lower()
            action_arg = (a_match.group(2) or "").strip()
        else:
            if "finish" in text.lower():
                action_name = "finish"
                action_arg = text.strip()
            elif "fetch" in text.lower():
                m = re.search(r"https?://\S+", text)
                if m:
                    action_name = "fetch"
                    action_arg = m.group(0)

        return thought, action_name, action_arg

    def execute_action(self, action_name: str, action_arg: str) -> str:
        """Execute tool call and return observation."""
        if action_name == "fetch":
            url = action_arg.strip()
            if not url:
                return "Error: fetch requires a URL"
            snap = self.fetcher.fetch(url)
            return (
                f"Page loaded: '{snap.title}' "
                f"({len(snap.interactives)} interactives, {len(snap.text)} chars)"
            )

        if action_name == "click":
            target = action_arg.strip()
            if not target:
                return "Error: click requires an element index or selector"
            res = self.fetcher.click(target)
            if res.get("success"):
                return f"Successfully clicked: {res.get('text', target)}"
            return f"Click failed: {res.get('error', 'unknown error')}"

        if action_name == "type":
            parts = action_arg.split(maxsplit=1)
            if len(parts) < 2:
                return "Error: type requires <selector> <text>"
            selector, txt = parts[0], parts[1]
            res = self.fetcher.type_text(selector, txt)
            if res.get("success"):
                return f"Typed text into '{selector}'"
            return f"Typing failed: {res.get('error', 'unknown error')}"

        if action_name == "assign_task":
            # name|url
            if "|" not in action_arg:
                return "Error: assign_task requires name|url"
            name, url = [x.strip() for x in action_arg.split("|", 1)]
            tab = self.fetcher.create_tab(url)
            if not tab:
                return f"Failed to create tab for task '{name}'"
            self.tasks[name] = {
                "tab_id": tab["id"],
                "url": tab.get("url") or url,
                "status": "opened",
                "title": tab.get("title", ""),
            }
            # Attach to the new tab so follow-up actions hit it
            self.fetcher.attach_tab(tab["id"])
            time.sleep(1.2)
            snap = self.fetcher.fetch()
            self.tasks[name]["status"] = "attached"
            self.tasks[name]["title"] = snap.title
            return (
                f"Task '{name}' opened on tab {tab['id'][:8]}… "
                f"now on '{snap.title}' ({snap.url})"
            )

        if action_name == "switch_task":
            key = action_arg.strip()
            if key in self.tasks:
                ok = self.fetcher.attach_tab(self.tasks[key]["tab_id"])
            else:
                ok = self.fetcher.attach_tab(key)
            if not ok:
                return f"Failed to switch to '{key}'"
            snap = self.fetcher.fetch()
            return f"Switched to '{snap.title}' ({snap.url})"

        if action_name in ("ax_find", "ax"):
            q = action_arg.strip() or "searchbox"
            res = self.fetcher.find_ax(q)
            if not res.get("ok"):
                return f"AX probe failed: {res.get('error')}"
            nodes = res.get("nodes") or []
            lines = [f"AX matches for '{q}': {res.get('count')}"]
            for n in nodes[:10]:
                lines.append(f"  role={n.get('role')} name={n.get('name')!r}")
            return "\n".join(lines)

        if action_name in ("css_test", "css"):
            sel = action_arg.strip()
            if not sel:
                return "Error: css_test requires a selector"
            res = self.fetcher.test_css(sel)
            if not res.get("ok"):
                return f"CSS probe failed: {res.get('error')}"
            lines = [f"CSS '{sel}': {res.get('match_count')} matches"]
            for s in (res.get("samples") or [])[:5]:
                lines.append(
                    f"  <{s.get('tag')} role={s.get('role')}> {s.get('text')!r}"
                )
            return "\n".join(lines)

        if action_name in ("jev_maps", "jev"):
            # Prefer library scroll scrape; fall back to light feed probe
            result = self.fetcher.run_library_script("google-maps/get-cards-via-scroll")
            if isinstance(result, dict) and result.get("ok"):
                validated = _validate_against_schema(result, MAPS_CARD_SCHEMA, "$")
                self.extracted["maps_cards"] = result.get("data") or []
                return (
                    f"JEV maps scrape ok={len(validated)==0} count={result.get('count')} "
                    f"schema_errors={validated[:3] or 'none'} "
                    f"sample={[c.get('name') for c in (result.get('data') or [])[:5]]}"
                )
            # Lightweight typesafe probe if scroll script fails
            probe = """
            (() => {
              const feed = document.querySelector('div[role="feed"]');
              if (!feed) return {ok:false, error:'no feed', data:[]};
              const data = [];
              feed.querySelectorAll('div[role="article"]').forEach(card => {
                const a = card.querySelector('a.hfpxzc');
                if (!a) return;
                data.push({
                  name: a.getAttribute('aria-label') || a.innerText.trim(),
                  maps_url: a.href || '',
                  address: ([...card.querySelectorAll('.W4Efsd')].map(x=>x.innerText.trim()).find(t=>t.includes('·'))||'')
                });
              });
              return {ok:true, count:data.length, data};
            })()
            """
            jev = self.fetcher.run_jev(MAPS_CARD_SCHEMA, probe)
            if jev.get("ok"):
                self.extracted["maps_cards"] = (jev.get("data") or {}).get("data") or []
            return (
                f"JEV probe ok={jev.get('ok')} errors={jev.get('errors')} "
                f"count={(jev.get('data') or {}).get('count')}"
            )

        if action_name == "run_script":
            path = action_arg.strip()
            if not path:
                return "Error: run_script requires scripts-library relative path"
            result = self.fetcher.run_library_script(path)
            return f"Script result: {_clip_for_log(result, 600)}"

        if action_name == "har_start":
            ok = self.har.start_capture(self.fetcher.port)
            if ok:
                return "HAR capture started on browser CDP stream."
            return "Failed to start HAR capture (check Chrome connection)."

        if action_name == "har_stop":
            summary = self.har.stop_capture()
            return (
                f"HAR capture stopped. Total requests: {summary['total_requests']} "
                f"({summary['api_requests']} API calls)"
            )

        if action_name == "har_save":
            filepath, count = self.har.save_har()
            return f"HAR archive saved to: {os.path.basename(filepath)} ({count} requests)"

        if action_name == "har_apis":
            rows = self.har.recent_apis(limit=15, url_substr=action_arg.strip())
            if not rows:
                return "No API-like HAR entries yet."
            return "HAR APIs:\n" + "\n".join(
                f"  [{r.get('status')}] {r.get('method')} {r.get('url')}" for r in rows
            )

        if action_name == "har_analyze":
            path = (action_arg or "").strip()
            if not path:
                path = getattr(self.har, "last_path", None) or ""
            if not path or not os.path.isfile(path):
                # Auto-save then analyze
                path, _ = self.har.save_har()
            if HAS_MMCP and mmcp_analyze_har is not None:
                report = mmcp_analyze_har(path, deep=True)
                top = report.get("top_endpoints") or report.get("top_apis") or []
                return (
                    f"HAR analyze ({report.get('engine')}): entries={report.get('entries')} "
                    f"apis={report.get('api_like_count') or report.get('api_endpoints')} "
                    f"score={report.get('security_score', 'n/a')}\n"
                    + "\n".join(
                        f"  - {t.get('endpoint') or t}" for t in top[:8]
                    )
                )
            return f"HAR saved at {path} (mmcp analyzer unavailable)"

        if action_name == "mmcp_run":
            if not HAS_MMCP or MultiModelWorkflow is None:
                return "mmcp not installed"
            goal = (action_arg or self.current_goal or "").strip()
            if not goal:
                return "mmcp_run requires a goal"
            wf = MultiModelWorkflow(
                tool_executor=self._mmcp_tool_executor(),
                use_langgraph=True,
            )
            state = wf.run(goal, har_summary=self.har.summary_for_prompt(), max_steps=6)
            return (
                f"mmcp[{wf.backend}] role={state.get('role')} "
                f"model={state.get('model_used')}\n"
                f"{state.get('answer') or state.get('plan') or 'done'}"
            )

        if action_name == "finish":
            if self.extracted.get("maps_cards"):
                n = len(self.extracted["maps_cards"])
                return (action_arg or "Goal complete.") + f" | extracted_maps_cards={n}"
            return action_arg or "Goal complete."

        return f"Unknown action: '{action_name}'"

    def run_goal(self, goal: str, max_steps: int = 20, dry_run: Optional[bool] = None) -> str:
        """Run autonomous agent loop up to max_steps.

        Geo/phone/Maps goals prefer the skills pipeline (no LLM).
        dry_run defaults True unless goal contains 'live' / env AGENT_LIVE=1.
        """
        self.stop_requested = False
        self.current_goal = goal
        self.history.clear()
        self.extracted.clear()
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(AGENT_RUNS_DIR, exist_ok=True)
        self.run_path = os.path.join(AGENT_RUNS_DIR, f"run_{self.run_id}.jsonl")
        self._append_run_log({"event": "agent_started", "goal": goal, "run_id": self.run_id})

        self._notify("agent_started", {"goal": goal, "run_id": self.run_id})
        final_summary = ""

        # Ensure CDP probe early so dry_run can auto-flip to live
        if not self.fetcher.is_connected():
            found_port = self.fetcher.find_available_port()
            if found_port:
                self.fetcher.connect(found_port)

        low_g = (goal or "").lower()
        force_dry = (
            dry_run is True
            or " dry" in f" {low_g}"
            or low_g.startswith("dry ")
            or "dry_run" in low_g
        )
        force_live = (
            dry_run is False
            or os.environ.get("AGENT_LIVE", "").strip().lower() in ("1", "true", "yes")
            or " live" in f" {low_g}"
            or low_g.startswith("live ")
        )

        # Skills scrapes: auto-start Chrome unless user explicitly asked for dry plan
        wants_skills = self.should_use_skills(goal)
        if wants_skills and not force_dry and not self.fetcher.is_connected():
            self._notify(
                "step_action",
                {
                    "step": 0,
                    "thought": "Chrome CDP offline — launching browser for live scrape",
                    "action": "ensure_chrome",
                    "arg": f"port={self.fetcher.port}",
                },
            )
            chrome = self.fetcher.ensure_chrome(
                notify=lambda m: self._notify(
                    "step_observation", {"step": 0, "observation": m}
                )
            )
            self._append_run_log({"event": "ensure_chrome", **chrome})
            if not chrome.get("ok"):
                # Fall through to dry plan only if launch failed and user didn't force live
                if force_live:
                    summary = (
                        "Blocked: need Chrome CDP for live scrape. "
                        f"{chrome.get('message')}. "
                        "Run: python launch-chrome.py  then retry."
                    )
                    self._notify(
                        "agent_finished",
                        {
                            "goal": goal,
                            "summary": summary,
                            "run_id": self.run_id,
                            "run_path": self.run_path,
                            "mode": "skills",
                            "dry_run": False,
                            "ok": False,
                            "blocked": True,
                        },
                    )
                    self._append_run_log(
                        {"event": "finished", "summary": summary, "ok": False, "blocked": True}
                    )
                    return summary

        if dry_run is None:
            if force_dry:
                dry_run = True
            elif force_live:
                dry_run = False
            else:
                # Prefer live whenever CDP is up (including after auto-launch)
                dry_run = not (
                    self.fetcher.is_connected() or self.fetcher.cdp_reachable()
                )

        # Explicit multi-model context protocol path (LangGraph + router)
        use_mmcp = (
            HAS_MMCP
            and MultiModelWorkflow is not None
            and (
                os.environ.get("MMCP_AGENT", "").strip().lower() in ("1", "true", "yes")
                or "mmcp" in (goal or "").lower()
                or "langgraph" in (goal or "").lower()
            )
        )
        if use_mmcp:
            self._append_run_log({"event": "mode", "mode": "mmcp"})
            self._notify("step_action", {
                "step": 0,
                "thought": "Using mmcp multi-model workflow",
                "action": "mmcp_run",
                "arg": goal,
            })
            summary = self.execute_action("mmcp_run", goal)
            self.memory.record_run(
                goal=goal, run_id=self.run_id, summary=summary, extracted=self.extracted, steps=1
            )
            self._notify("agent_finished", {
                "goal": goal,
                "summary": summary,
                "run_id": self.run_id,
                "mode": "mmcp",
                "ok": True,
            })
            self._append_run_log({"event": "finished", "summary": summary, "mode": "mmcp"})
            return summary

        # Skills path — DecisionBuilder + pincode CSV + Maps JEV (no LLM)
        if wants_skills:
            self._append_run_log({"event": "mode", "mode": "skills", "dry_run": dry_run})
            self._notify("step_action", {
                "step": 0,
                "thought": (
                    "Using skills pipeline (decision + pincodes + maps) — LLM skipped"
                    + (" [LIVE]" if not dry_run else " [DRY plan only]")
                ),
                "action": "skills_pipeline",
                "arg": f"dry_run={dry_run} cdp={self.fetcher.is_connected()}",
            })
            return self.run_goal_with_skills(goal, dry_run=bool(dry_run))

        planned = self.plan_tasks_for_goal(goal)
        if planned:
            self._notify("agent_plan", {"tasks": planned})
            self._append_run_log({"event": "plan", "tasks": planned})

        for step in range(1, max_steps + 1):
            if self.stop_requested:
                self._notify("agent_stopped", {"step": step})
                self._append_run_log({"event": "stopped", "step": step})
                return "Agent stopped by user."

            prompt = self.build_agent_prompt(goal, step, max_steps)
            self._notify("step_prompting", {"step": step})

            raw_reply = self.llm_fn(prompt)
            thought, action_name, action_arg = self.parse_action(raw_reply)

            self._notify(
                "step_action",
                {
                    "step": step,
                    "thought": thought,
                    "action": action_name,
                    "arg": action_arg,
                },
            )

            observation = self.execute_action(action_name, action_arg)
            self._notify("step_observation", {"step": step, "observation": observation})

            record = {
                "step": step,
                "thought": thought,
                "action": f"{action_name} {action_arg}".strip(),
                "observation": observation,
                "cdp_tail": self.fetcher.cdp_log[-3:],
                "har": self.har.get_summary(),
            }
            self.history.append(record)
            self._append_run_log({"event": "step", **record})

            if action_name == "finish" or step == max_steps:
                final_summary = action_arg or observation
                break

            time.sleep(0.4)

        # Persist full run snapshot
        summary_path = os.path.join(AGENT_RUNS_DIR, f"run_{self.run_id}_summary.json")
        try:
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "goal": goal,
                        "run_id": self.run_id,
                        "summary": final_summary,
                        "tasks": self.tasks,
                        "extracted": self.extracted,
                        "history": self.history,
                        "cdp_log": self.fetcher.cdp_log[-50:],
                        "har": self.har.get_summary(),
                        "har_apis": self.har.recent_apis(20),
                    },
                    f,
                    indent=2,
                    default=str,
                )
        except Exception as e:
            logger.debug(f"summary save failed: {e}")

        self._notify(
            "agent_finished",
            {
                "goal": goal,
                "summary": final_summary,
                "run_id": self.run_id,
                "run_path": self.run_path,
                "extracted": self.extracted,
            },
        )
        self._append_run_log({"event": "finished", "summary": final_summary})
        return final_summary


# ============================================================================
# 6. CRON STORE (schedule maps scrapes from TUI menu)
# ============================================================================

class CronStore:
    """Thin wrapper over agent.db schedules for the llama_tui Cron menu."""

    TASK_TYPE = "maps_scrape"

    PRESETS = [
        ("every minute", "* * * * *"),
        ("hourly", "0 * * * *"),
        ("daily 09:00", "0 9 * * *"),
        ("daily 21:00", "0 21 * * *"),
        ("weekdays 09:00", "0 9 * * 1-5"),
        ("weekly Mon 09:00", "0 9 * * 1"),
    ]

    def __init__(self, db_path: Optional[str] = None):
        from agent.config import AgentConfig
        from agent.database import Database
        from agent.cron import CronExpression

        self._CronExpression = CronExpression
        cfg = AgentConfig()
        self.db_path = db_path or cfg.db_path
        self.db = Database(self.db_path)

    def list_jobs(self) -> List[Dict[str, Any]]:
        rows = self.db.get_schedules()
        out = []
        for r in rows:
            item = dict(r)
            payload = item.get("payload")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            item["payload"] = payload or {}
            item["goal"] = (item["payload"] or {}).get("goal", "")
            out.append(item)
        return out

    def add_job(
        self,
        name: str,
        cron_expr: str,
        goal: str,
        dry_run: bool = False,
        priority: int = 5,
    ) -> Dict[str, Any]:
        name = (name or "").strip()
        goal = (goal or "").strip()
        cron_expr = (cron_expr or "").strip()
        if not name or not goal or not cron_expr:
            raise ValueError("name, cron_expr, and goal are required")
        # validate
        cron = self._CronExpression(cron_expr)
        next_run = cron.next_run().isoformat()
        existing = self.db.get_schedule_by_name(name)
        if existing:
            self.db.delete_schedule(name)
        sid = self.db.insert_schedule(
            name=name,
            task_type=self.TASK_TYPE,
            cron_expr=cron_expr,
            payload={"goal": goal, "dry_run": bool(dry_run)},
            priority=priority,
            next_run_at=next_run,
        )
        return {
            "id": sid,
            "name": name,
            "cron_expr": cron_expr,
            "goal": goal,
            "next_run_at": next_run,
            "dry_run": dry_run,
        }

    def enable(self, name: str, enabled: bool = True) -> None:
        self.db.set_schedule_enabled(name, enabled)

    def delete(self, name: str) -> bool:
        return self.db.delete_schedule(name)

    def summary_text(self) -> str:
        jobs = self.list_jobs()
        if not jobs:
            return "(no cron jobs — use F8 menu to add)"
        lines = []
        for j in jobs:
            en = "ON " if j.get("enabled") else "OFF"
            goal = (j.get("goal") or "")[:40]
            lines.append(
                f"  [{en}] {j.get('name')}  {j.get('cron_expr')}  "
                f"next={j.get('next_run_at', '?')[:19]}  {goal}"
            )
        return "\n".join(lines)
