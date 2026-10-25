"""HAR analysis facade — wraps AdvancedHARAnalyzer when present."""

from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _load_har(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _entries(har: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list((har.get("log") or {}).get("entries") or [])


def lightweight_analyze(har_path: str) -> Dict[str, Any]:
    """Fast, dependency-free HAR summary for MCP / agent prompts."""
    har = _load_har(har_path)
    entries = _entries(har)
    domains: Counter = Counter()
    methods: Counter = Counter()
    statuses: Counter = Counter()
    apis: List[Dict[str, Any]] = []
    endpoints: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "methods": set(), "statuses": []}
    )

    for e in entries:
        req = e.get("request") or {}
        resp = e.get("response") or {}
        url = req.get("url") or ""
        method = req.get("method") or "GET"
        status = int(resp.get("status") or 0)
        mime = str((resp.get("content") or {}).get("mimeType") or resp.get("mimeType") or "")
        host = urlparse(url).netloc
        if host:
            domains[host] += 1
        methods[method] += 1
        statuses[str(status)] += 1

        path = urlparse(url).path or "/"
        key = f"{method} {host}{path}"
        endpoints[key]["count"] += 1
        endpoints[key]["methods"].add(method)
        endpoints[key]["statuses"].append(status)

        is_api = (
            "json" in mime.lower()
            or "/api" in url.lower()
            or "graphql" in url.lower()
            or "batchexecute" in url.lower()
        )
        if is_api:
            apis.append(
                {
                    "method": method,
                    "status": status,
                    "url": url[:240],
                    "mime": mime,
                    "time_ms": e.get("time"),
                }
            )

    top_endpoints = []
    for k, v in sorted(endpoints.items(), key=lambda kv: -kv[1]["count"])[:25]:
        top_endpoints.append(
            {
                "endpoint": k,
                "count": v["count"],
                "methods": sorted(v["methods"]),
                "status_counts": dict(Counter(v["statuses"])),
            }
        )

    return {
        "har_file": har_path,
        "entries": len(entries),
        "domains": domains.most_common(20),
        "methods": dict(methods),
        "statuses": dict(statuses),
        "api_like": apis[:50],
        "api_like_count": len(apis),
        "top_endpoints": top_endpoints,
        "engine": "mmcp.lightweight",
    }


def advanced_analyze(
    har_path: str,
    *,
    output: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Prefer AdvancedHARAnalyzer when available; else lightweight.
    Returns a JSON-serializable summary (not the full analyzer object).
    """
    try:
        from advanced_har_analyzer1 import AdvancedHARAnalyzer  # type: ignore
    except Exception:
        try:
            import importlib

            mod = importlib.import_module("advanced_har_analyzer1")
            AdvancedHARAnalyzer = getattr(mod, "AdvancedHARAnalyzer")
        except Exception as e:
            logger.info("AdvancedHARAnalyzer unavailable (%s); using lightweight", e)
            return lightweight_analyze(har_path)

    out = output or (os.path.splitext(har_path)[0] + "_analysis.json")
    try:
        analyzer = AdvancedHARAnalyzer(har_path, analysis_file=out)
        analyzer.run_all()
        summary = {
            "har_file": har_path,
            "analysis_file": out,
            "entries": len(getattr(analyzer, "views", []) or []),
            "api_endpoints": len(getattr(analyzer, "api_endpoints", {}) or {}),
            "security_score": (getattr(analyzer, "security_report", {}) or {}).get("score"),
            "sensitive_count": len(getattr(analyzer, "sensitive_data", []) or []),
            "top_apis": [],
            "engine": "advanced_har_analyzer1",
        }
        for i, (ep, d) in enumerate(list((analyzer.api_endpoints or {}).items())[:15]):
            summary["top_apis"].append(
                {
                    "endpoint": ep,
                    "count": d.get("count"),
                    "statuses": dict(Counter(d.get("statuses") or [])),
                }
            )
        # Merge lightweight domain stats
        light = lightweight_analyze(har_path)
        summary["domains"] = light.get("domains")
        summary["methods"] = light.get("methods")
        summary["api_like_count"] = light.get("api_like_count")
        return summary
    except Exception:
        logger.exception("advanced analyze failed; falling back")
        return lightweight_analyze(har_path)


def analyze_har(har_path: str, *, deep: bool = True) -> Dict[str, Any]:
    if not os.path.isfile(har_path):
        return {"error": f"HAR not found: {har_path}"}
    if deep:
        return advanced_analyze(har_path)
    return lightweight_analyze(har_path)
