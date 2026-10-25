"""Secret / PII redaction for HAR payloads."""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, MutableMapping, Optional, Set

# Header names (case-insensitive) whose values are always scrubbed
SENSITIVE_HEADERS: Set[str] = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "x-access-token",
    "x-csrf-token",
    "x-session-token",
    "api-key",
    "apikey",
}

# Query / form / JSON keys to scrub
SENSITIVE_KEYS = re.compile(
    r"(pass(word)?|secret|token|auth|api[_-]?key|session|csrf|jwt|bearer|credential|private)",
    re.I,
)

# Inline patterns in bodies / URLs
_PATTERNS = [
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/=]+", re.I), r"\1[REDACTED]"),
    (re.compile(r"(Basic\s+)[A-Za-z0-9+/=]+", re.I), r"\1[REDACTED]"),
    (
        re.compile(
            r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
        ),
        "[REDACTED_JWT]",
    ),
    (
        re.compile(r"(api[_-]?key|access[_-]?token|refresh[_-]?token)=([^&\s]+)", re.I),
        r"\1=[REDACTED]",
    ),
]

REDACTED = "[REDACTED]"


def redact_string(value: str) -> str:
    out = value
    for pat, repl in _PATTERNS:
        out = pat.sub(repl, out)
    return out


def _header_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name") or item.get("Name") or "")
    return ""


def _header_value(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("value") if "value" in item else item.get("Value", ""))
    return str(item)


def redact_headers(headers: Any) -> Any:
    if isinstance(headers, dict):
        out: Dict[str, Any] = {}
        for k, v in headers.items():
            if str(k).lower() in SENSITIVE_HEADERS or SENSITIVE_KEYS.search(str(k)):
                out[k] = REDACTED
            else:
                out[k] = redact_string(str(v)) if isinstance(v, str) else v
        return out
    if isinstance(headers, list):
        out_list: List[Any] = []
        for h in headers:
            name = _header_name(h)
            if name.lower() in SENSITIVE_HEADERS or SENSITIVE_KEYS.search(name):
                if isinstance(h, dict):
                    nh = dict(h)
                    nh["value"] = REDACTED
                    out_list.append(nh)
                else:
                    out_list.append(h)
            elif isinstance(h, dict):
                nh = dict(h)
                if isinstance(nh.get("value"), str):
                    nh["value"] = redact_string(nh["value"])
                out_list.append(nh)
            else:
                out_list.append(h)
        return out_list
    return headers


def redact_mapping(obj: MutableMapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in obj.items():
        if SENSITIVE_KEYS.search(str(k)):
            out[k] = REDACTED
        elif isinstance(v, dict):
            out[k] = redact_mapping(v)
        elif isinstance(v, list):
            out[k] = [
                redact_mapping(i) if isinstance(i, dict) else (
                    redact_string(i) if isinstance(i, str) else i
                )
                for i in v
            ]
        elif isinstance(v, str):
            out[k] = redact_string(v)
        else:
            out[k] = v
    return out


def redact_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    e = copy.deepcopy(entry)
    req = e.get("request") or {}
    resp = e.get("response") or {}

    if "url" in req and isinstance(req["url"], str):
        req["url"] = redact_string(req["url"])
    if "headers" in req:
        req["headers"] = redact_headers(req["headers"])
    if "cookies" in req:
        req["cookies"] = [
            {**c, "value": REDACTED} if isinstance(c, dict) else c
            for c in (req["cookies"] or [])
        ]
    post = req.get("postData")
    if isinstance(post, dict) and isinstance(post.get("text"), str):
        post["text"] = redact_string(post["text"])
    elif isinstance(post, str):
        req["postData"] = redact_string(post)

    if "headers" in resp:
        resp["headers"] = redact_headers(resp["headers"])
    if "cookies" in resp:
        resp["cookies"] = [
            {**c, "value": REDACTED} if isinstance(c, dict) else c
            for c in (resp["cookies"] or [])
        ]
    content = resp.get("content")
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        content["text"] = redact_string(content["text"])

    e["request"] = req
    e["response"] = resp
    # Drop internal auth mirrors if present
    e.pop("auth_headers", None)
    return e


def redact_har(har_doc: Dict[str, Any]) -> Dict[str, Any]:
    doc = copy.deepcopy(har_doc)
    log = doc.get("log") or {}
    entries = log.get("entries") or []
    log["entries"] = [redact_entry(e) if isinstance(e, dict) else e for e in entries]
    doc["log"] = log
    return doc
