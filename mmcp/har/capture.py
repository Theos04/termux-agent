"""
Production CDP HAR capturer.

Improvements over agent_bridge.HarManager:
  - multi-tab attach
  - optional response body capture via Network.getResponseBody
  - entry cap + body size limits
  - HAR 1.2 serialize with secret redaction
  - thread-safe summary / API listing
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from mmcp.config import MMCPConfig, load_config
from mmcp.har.serialize import build_har, default_har_path, write_har

logger = logging.getLogger(__name__)

try:
    import requests as _requests
except Exception:  # pragma: no cover
    _requests = None

try:
    import websocket as _websocket
except Exception:  # pragma: no cover
    _websocket = None

if _websocket is None:
    try:
        from websockets.sync.client import connect as _ws_sync_connect

        class _WebSocketTimeoutException(TimeoutError):
            pass

        class _SyncWebSocketShim:
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

        _websocket = _WebsocketModule()
    except Exception:
        _websocket = None



class ProductionHARCapturer:
    """Background multi-tab Network.* → HAR 1.2 capturer."""

    def __init__(self, config: Optional[MMCPConfig] = None, port: Optional[int] = None):
        self.config = config or load_config()
        self.port = port or self.config.chrome_debug_port
        self.is_capturing = False
        self.entries: List[Dict[str, Any]] = []
        self.pending: Dict[str, Dict[str, Any]] = {}
        self.domains_seen: Set[str] = set()
        self.start_time: Optional[datetime] = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._threads: Dict[str, threading.Thread] = {}
        self._sockets: Dict[str, Any] = {}
        self._msg_id = 200
        self._ws_lock = threading.Lock()
        self.last_path: Optional[str] = None

    # ----- CDP helpers -----

    def _list_tabs(self) -> List[Dict[str, Any]]:
        if not _requests:
            return []
        try:
            r = _requests.get(f"http://127.0.0.1:{self.port}/json", timeout=2)
            tabs = [t for t in r.json() if t.get("type") == "page"]
            return tabs
        except Exception as e:
            logger.debug("list tabs failed: %s", e)
            return []

    def _next_id(self) -> int:
        with self._ws_lock:
            self._msg_id += 1
            return self._msg_id

    def _send(self, ws: Any, method: str, params: Optional[Dict] = None) -> None:
        payload: Dict[str, Any] = {"id": self._next_id(), "method": method}
        if params:
            payload["params"] = params
        ws.send(json.dumps(payload))

    def _fetch_body(self, ws: Any, request_id: str) -> Optional[str]:
        if not self.config.har_capture_bodies:
            return None
        try:
            mid = self._next_id()
            ws.send(
                json.dumps(
                    {
                        "id": mid,
                        "method": "Network.getResponseBody",
                        "params": {"requestId": request_id},
                    }
                )
            )
            # Best-effort: drain until matching id or timeout
            deadline = time.time() + 0.8
            while time.time() < deadline:
                ws.settimeout(0.25)
                try:
                    raw = ws.recv()
                except Exception:
                    break
                data = json.loads(raw)
                if data.get("id") == mid:
                    result = data.get("result") or {}
                    body = result.get("body")
                    if result.get("base64Encoded") and isinstance(body, str):
                        # Keep truncated ascii-safe preview only
                        return body[: min(len(body), self.config.har_max_body_bytes)]
                    if isinstance(body, str):
                        return body[: self.config.har_max_body_bytes]
                    return None
                # Re-process unrelated events
                method = data.get("method")
                if method:
                    self._process_event(method, data.get("params") or {}, tab_id="?")
        except Exception as e:
            logger.debug("getResponseBody failed: %s", e)
        return None

    # ----- lifecycle -----

    def start(self, port: Optional[int] = None, multi_tab: Optional[bool] = None) -> bool:
        if self.is_capturing:
            return True
        if port:
            self.port = port
        if not _requests or not _websocket:
            logger.warning("HAR capture requires requests + websocket-client")
            return False

        tabs = self._list_tabs()
        if not tabs:
            logger.warning("No Chrome page tabs on port %s", self.port)
            return False

        use_multi = self.config.har_multi_tab if multi_tab is None else multi_tab
        targets = tabs if use_multi else tabs[:1]

        with self._lock:
            self.entries.clear()
            self.pending.clear()
            self.domains_seen.clear()
            self.start_time = datetime.now()
            self._stop.clear()
            self.is_capturing = True

        started = 0
        for tab in targets:
            ws_url = tab.get("webSocketDebuggerUrl")
            tab_id = tab.get("id") or ws_url or str(started)
            if not ws_url:
                continue
            t = threading.Thread(
                target=self._capture_loop,
                args=(ws_url, tab_id),
                daemon=True,
                name=f"mmcp-har-{str(tab_id)[:8]}",
            )
            self._threads[tab_id] = t
            t.start()
            started += 1

        if started == 0:
            self.is_capturing = False
            return False
        logger.info("HAR capture started on %d tab(s) port=%s", started, self.port)
        return True

    # aliases for agent_bridge.HarManager compatibility
    def start_capture(self, port: Optional[int] = None) -> bool:
        return self.start(port=port)

    def stop(self) -> Dict[str, Any]:
        self._stop.set()
        for t in list(self._threads.values()):
            if t.is_alive():
                t.join(timeout=2.0)
        for ws in list(self._sockets.values()):
            try:
                ws.close()
            except Exception:
                pass
        self._sockets.clear()
        self._threads.clear()
        self.is_capturing = False
        return self.summary()

    def stop_capture(self) -> Dict[str, Any]:
        return self.stop()

    def _capture_loop(self, ws_url: str, tab_id: str) -> None:
        ws = None
        try:
            ws = _websocket.create_connection(ws_url, timeout=5)
            self._sockets[tab_id] = ws
            self._send(ws, "Network.enable", {"maxResourceBufferSize": 50_000_000})
            self._send(ws, "Page.enable")
            while not self._stop.is_set():
                try:
                    ws.settimeout(1.0)
                    raw = ws.recv()
                    data = json.loads(raw)
                    method = data.get("method")
                    if method:
                        self._process_event(method, data.get("params") or {}, tab_id, ws)
                except Exception as e:
                    # timeout → continue; hard errors → break
                    name = type(e).__name__
                    if "Timeout" in name:
                        continue
                    break
        except Exception as e:
            logger.debug("HAR socket error tab=%s: %s", tab_id, e)
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
            self._sockets.pop(tab_id, None)

    def _process_event(
        self,
        method: str,
        params: Dict[str, Any],
        tab_id: str,
        ws: Any = None,
    ) -> None:
        req_id = params.get("requestId")
        if not req_id:
            return
        key = f"{tab_id}:{req_id}"

        with self._lock:
            if method == "Network.requestWillBeSent":
                req = params.get("request") or {}
                url = req.get("url") or ""
                if url.startswith(("data:", "blob:", "chrome-extension:")):
                    return
                domain = urlparse(url).netloc
                if domain:
                    self.domains_seen.add(domain)
                headers = req.get("headers") or {}
                post = req.get("postData")
                self.pending[key] = {
                    "startedDateTime": datetime.now().isoformat(),
                    "request": {
                        "method": req.get("method", "GET"),
                        "url": url,
                        "headers": headers,
                        "postData": {"text": post} if isinstance(post, str) and post else None,
                    },
                    "response": None,
                    "time": 0,
                    "tab_id": tab_id,
                    "request_id": req_id,
                    "_timestamp": params.get("timestamp", time.time()),
                }

            elif method == "Network.requestWillBeSentExtraInfo":
                if key in self.pending:
                    extra = params.get("headers") or {}
                    if isinstance(extra, dict):
                        cur = self.pending[key]["request"].get("headers") or {}
                        if isinstance(cur, dict):
                            cur.update(extra)
                            self.pending[key]["request"]["headers"] = cur

            elif method == "Network.responseReceived":
                if key in self.pending:
                    resp = params.get("response") or {}
                    self.pending[key]["response"] = {
                        "status": resp.get("status", 0),
                        "statusText": resp.get("statusText", ""),
                        "mimeType": resp.get("mimeType", ""),
                        "headers": resp.get("headers") or {},
                        "content": {"mimeType": resp.get("mimeType", "")},
                    }

            elif method == "Network.loadingFinished":
                entry = self.pending.pop(key, None)
                if not entry or not entry.get("response"):
                    return
                end_ts = params.get("timestamp", time.time())
                dur_ms = max(1.0, (end_ts - entry.get("_timestamp", end_ts)) * 1000)
                entry["time"] = round(dur_ms, 2)
                entry.pop("_timestamp", None)

                if ws is not None and self.config.har_capture_bodies:
                    body = self._fetch_body(ws, req_id)
                    if body is not None:
                        entry["response"].setdefault("content", {})
                        entry["response"]["content"]["text"] = body
                        entry["response"]["content"]["size"] = len(
                            body.encode("utf-8", errors="replace")
                        )

                if len(self.entries) >= self.config.har_max_entries:
                    # drop oldest to stay bounded
                    self.entries.pop(0)
                self.entries.append(entry)

    # ----- export / query -----

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self.entries)
            api = sum(
                1
                for e in self.entries
                if "json" in str((e.get("response") or {}).get("mimeType", "")).lower()
            )
            domains = list(self.domains_seen)
            dur = (
                (datetime.now() - self.start_time).total_seconds()
                if self.start_time
                else 0.0
            )
            return {
                "is_capturing": self.is_capturing,
                "total_requests": total,
                "api_requests": api,
                "domains": domains[:12],
                "total_domains": len(domains),
                "duration_seconds": round(dur, 1),
                "tabs": len(self._threads),
                "last_path": self.last_path,
            }

    def get_summary(self) -> Dict[str, Any]:
        return self.summary()

    def save(
        self,
        filepath: Optional[str] = None,
        *,
        redact: Optional[bool] = None,
    ) -> Tuple[str, int]:
        path = filepath or default_har_path()
        do_redact = self.config.har_redact_secrets if redact is None else redact
        with self._lock:
            doc = build_har(list(self.entries), comment=f"port={self.port}")
        path, n = write_har(doc, path, redact=do_redact)
        self.last_path = path
        return path, n

    def save_har(self, filepath: Optional[str] = None) -> Tuple[str, int]:
        return self.save(filepath)

    def recent_apis(self, limit: int = 12, url_substr: str = "") -> List[Dict[str, Any]]:
        with self._lock:
            rows: List[Dict[str, Any]] = []
            needle = (url_substr or "").lower()
            for e in reversed(self.entries):
                resp = e.get("response") or {}
                mime = str(resp.get("mimeType") or "").lower()
                url = (e.get("request") or {}).get("url", "")
                method = (e.get("request") or {}).get("method", "")
                is_api = (
                    "json" in mime
                    or "/api" in url.lower()
                    or "graphql" in url.lower()
                    or "maps.googleapis" in url.lower()
                    or "batchexecute" in url.lower()
                    or "xhr" in mime
                )
                if not is_api:
                    continue
                if needle and needle not in url.lower():
                    continue
                rows.append(
                    {
                        "method": method,
                        "status": resp.get("status"),
                        "mime": mime,
                        "url": url[:220],
                        "time_ms": e.get("time"),
                        "tab_id": e.get("tab_id"),
                    }
                )
                if len(rows) >= limit:
                    break
            return rows

    def summary_for_prompt(self, limit: int = 8) -> str:
        stats = self.summary()
        lines = [
            f"HAR capturing={stats['is_capturing']} reqs={stats['total_requests']} "
            f"apis={stats['api_requests']} domains={stats['total_domains']} "
            f"tabs={stats.get('tabs', 1)}"
        ]
        apis = self.recent_apis(limit=limit)
        if apis:
            lines.append("Recent API-like requests:")
            for a in apis:
                lines.append(f"  [{a.get('status')}] {a.get('method')} {a.get('url')}")
        else:
            lines.append("Recent API-like requests: (none yet)")
        return "\n".join(lines)


# Back-compat alias
HarManager = ProductionHARCapturer
