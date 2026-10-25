"""HAR 1.2 document builders and writers."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from mmcp.har.redact import redact_har


CREATOR = {"name": "termux-agent-mmcp", "version": "1.0.0"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def headers_to_har(headers: Any) -> List[Dict[str, str]]:
    if isinstance(headers, list):
        out = []
        for h in headers:
            if isinstance(h, dict) and "name" in h:
                out.append({"name": str(h["name"]), "value": str(h.get("value", ""))})
            elif isinstance(h, (list, tuple)) and len(h) >= 2:
                out.append({"name": str(h[0]), "value": str(h[1])})
        return out
    if isinstance(headers, dict):
        return [{"name": str(k), "value": str(v)} for k, v in headers.items()]
    return []


def normalize_entry(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce internal capture dicts into HAR 1.2 entry shape."""
    req = raw.get("request") or {}
    resp = raw.get("response") or {}

    method = req.get("method") or "GET"
    url = req.get("url") or ""
    req_headers = headers_to_har(req.get("headers"))
    resp_headers = headers_to_har(resp.get("headers"))

    post = req.get("postData")
    post_data = None
    if isinstance(post, dict) and post.get("text"):
        post_data = {
            "mimeType": post.get("mimeType") or "application/octet-stream",
            "text": str(post.get("text"))[:2_000_000],
        }
    elif isinstance(post, str) and post:
        post_data = {"mimeType": "text/plain", "text": post[:2_000_000]}

    mime = ""
    body_text = None
    body_size = -1
    content = resp.get("content")
    if isinstance(content, dict):
        mime = content.get("mimeType") or resp.get("mimeType") or ""
        if content.get("text") is not None:
            body_text = str(content.get("text"))
            body_size = len(body_text.encode("utf-8", errors="replace"))
        elif content.get("size"):
            body_size = int(content.get("size") or -1)
    else:
        mime = resp.get("mimeType") or ""

    content_obj: Dict[str, Any] = {"size": body_size, "mimeType": mime or "application/octet-stream"}
    if body_text is not None:
        content_obj["text"] = body_text

    timings = raw.get("timings") if isinstance(raw.get("timings"), dict) else {}
    time_ms = float(raw.get("time") or timings.get("receive") or 0) or 0.0

    entry: Dict[str, Any] = {
        "startedDateTime": raw.get("startedDateTime") or _iso_now(),
        "time": round(time_ms, 2),
        "request": {
            "method": method,
            "url": url,
            "httpVersion": req.get("httpVersion") or "HTTP/1.1",
            "cookies": req.get("cookies") or [],
            "headers": req_headers,
            "queryString": req.get("queryString") or [],
            "headersSize": -1,
            "bodySize": len(post_data["text"]) if post_data else 0,
        },
        "response": {
            "status": int(resp.get("status") or 0),
            "statusText": resp.get("statusText") or "",
            "httpVersion": resp.get("httpVersion") or "HTTP/1.1",
            "cookies": resp.get("cookies") or [],
            "headers": resp_headers,
            "content": content_obj,
            "redirectURL": resp.get("redirectURL") or "",
            "headersSize": -1,
            "bodySize": body_size,
        },
        "cache": {},
        "timings": {
            "blocked": timings.get("blocked", -1),
            "dns": timings.get("dns", -1),
            "connect": timings.get("connect", -1),
            "send": timings.get("send", 0),
            "wait": timings.get("wait", max(0.0, time_ms * 0.8)),
            "receive": timings.get("receive", max(0.0, time_ms * 0.2)),
            "ssl": timings.get("ssl", -1),
        },
    }
    if post_data:
        entry["request"]["postData"] = post_data

    # Preserve useful custom fields under underscore prefix
    if raw.get("tab_id"):
        entry["_tabId"] = raw["tab_id"]
    if raw.get("request_id"):
        entry["_requestId"] = raw["request_id"]
    return entry


def build_har(
    entries: List[Dict[str, Any]],
    *,
    pages: Optional[List[Dict[str, Any]]] = None,
    creator: Optional[Dict[str, str]] = None,
    comment: str = "",
) -> Dict[str, Any]:
    normalized = [normalize_entry(e) if "log" not in e else e for e in entries]
    # Skip already-full HAR docs accidentally passed in
    clean = []
    for e in normalized:
        if isinstance(e, dict) and "request" in e:
            clean.append(e)
    log: Dict[str, Any] = {
        "version": "1.2",
        "creator": creator or CREATOR,
        "entries": clean,
    }
    if pages:
        log["pages"] = pages
    if comment:
        log["comment"] = comment
    return {"log": log}


def write_har(
    har_doc: Dict[str, Any],
    filepath: str,
    *,
    redact: bool = True,
    indent: int = 2,
) -> Tuple[str, int]:
    doc = redact_har(har_doc) if redact else har_doc
    os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=indent, ensure_ascii=False)
    n = len((doc.get("log") or {}).get("entries") or [])
    return filepath, n


def default_har_path(directory: Optional[str] = None) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = directory or os.getcwd()
    return os.path.join(base, f"capture_{ts}.har")
