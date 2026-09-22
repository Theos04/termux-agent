#!/usr/bin/env python3
"""
advanced_har_analyzer2.py

Enhanced HAR Capture & Analysis — patched release.

Fixes over v1 (see CHANGELOG in comments):
  #1  Sensitive-data false positives (timestamps, UA versions, base64 fragments)
  #2  Timing silently empty when HAR has no timings — now warns
  #3  Cookies never populated from Chrome HARs — now parses Set-Cookie/Cookie headers
  #4  Bandwidth always 0 — now uses bodySize / compression fallbacks
  #5  Static asset paths polluting endpoint list — filtered by default
  #6  Endpoint collisions across hosts — host now part of the key
  #7  Tracker domain noise — separated from real APIs
  #8  Misleading security score — deduplicated, info no longer scored
  #9  Missed high-entropy secrets in query params (entropy-based detection)

Usage:
    python advanced_har_analyzer2.py capture.har
    python advanced_har_analyzer2.py capture.har --html report.html --csv out_dir
    python advanced_har_analyzer2.py capture.har --diff other.har
    python advanced_har_analyzer2.py capture.har --config cfg.json --log-file run.log -v
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import math
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse, parse_qs


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG = logging.getLogger("har_analyzer")


def configure_logging(verbosity: int = 0, log_file: Optional[str] = None) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(level=level, format=fmt, handlers=handlers, force=True)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Any] = {
    "max_body_scan_bytes": 200_000,
    "sensitive_sample_len": 60,
    "top_endpoints": 30,
    "filter_static_assets": True,
    "filter_tracker_domains": True,
    "static_extensions": [
        ".js", ".css", ".mjs", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
        ".woff", ".woff2", ".ttf", ".eot", ".otf", ".map", ".webp", ".avif",
        ".mp4", ".webm", ".mp3", ".ogg", ".pdf", ".zip",
    ],
    "static_path_hints": [
        "/assets/", "/static/", "/cdn-", "/bundle/", "/dist/", "/icons/",
        "/images/", "/fonts/", "/js/", "/css/", "/chunks/", "/_next/",
    ],
    "tracker_domains": [
        "bat.bing.com", "clarity.ms", "google-analytics.com",
        "googletagmanager.com", "analytics.google.com", "stats.g.doubleclick.net",
        "doubleclick.net", "googleadservices.com", "googlesyndication.com",
        "googletagmanager.com", "gstatic.com",
        "facebook.com", "facebook.net", "connect.facebook.net",
        "taboola.com", "trc.taboola.com", "cdn.taboola.com",
        "criteo.com", "criteo.net", "dynamic.criteo.com", "sslwidget.criteo.com",
        "snapchat.com", "sc-static.net",
        "adsrvr.org", "insight.adsrvr.org",
        "scorecardresearch.com", "quantserve.com", "rlcdn.com",
        "casalemedia.com", "rubiconproject.com", "pubmatic.com",
        "3lift.com", "adnxs.com", "bidswitch.net", "outbrain.com",
        "teads.tv", "media.net", "smartadserver.com", "yieldlab.net",
        "tapad.com", "socdm.com", "360yield.com", "bidtheatre.com",
        "adform.net", "advertising.com", "agkn.com", "crwdcntrl.net",
        "everesttech.net", "exelator.com", "mathtag.com", "ml314.com",
        "narrative.io", "netmng.com", "nrich.ai", "openx.net",
        "sharethrough.com", "simpli.fi", "sitescout.com", "spotxchange.com",
        "tapad.com", "thetradedesk.com", "tremorhub.com", "triplelift.com",
        "turn.com", "unrulymedia.com", "vidora.com", "yieldmo.com",
        "zeotap.com", "krxd.net", "agkn.com",
        "skimresources.com", "shareasale.com", "prf.hn",
        "yimg.jp", "yahoo.co.jp",
        "fls.doubleclick.net", "gumi.criteo.com", "dmxleo.com",
        "smt.docomo.ne.jp", "flvcdn.net", "yimg.com",
    ],
    "security": {
        "required_headers": [
            "strict-transport-security",
            "content-security-policy",
            "x-frame-options",
            "x-content-type-options",
            "referrer-policy",
        ],
        "csp_strong_directives": ["default-src", "object-src", "base-uri", "frame-ancestors"],
        "rate_limit_status": 429,
        "brute_force_window_sec": 60,
        "brute_force_threshold": 5,
        "high_entropy_threshold": 3.5,
        "high_entropy_min_len": 20,
    },
}


# ---------------------------------------------------------------------------
# Precompiled regexes
# ---------------------------------------------------------------------------
RX_ID_PATH = re.compile(r"/\d+")
RX_OBJECTID_PATH = re.compile(r"/[a-f0-9]{24,}")
RX_TOKEN_PATH = re.compile(r"/[A-Za-z0-9_\-]{20,}")
RX_EXT = re.compile(
    r"\.(json|xml|html|htm|js|mjs|css|png|jpg|jpeg|gif|svg|ico|woff2?|ttf|eot|otf|map|webp|avif)$",
    re.I,
)
RX_CONTENT_HASH = re.compile(r"-[0-9a-f]{8,}(\.[a-z0-9]+)?$", re.I)

RX_EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
RX_PHONE_CANDIDATE = re.compile(r"\b\d{10,13}\b")
RX_AADHAR_CANDIDATE = re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b")
RX_PAN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
RX_DOB = re.compile(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b")
RX_SALARY = re.compile(r"₹?\s?[\d,]+\.?\d*\s?(?:LPA|Lakh|Crore|K\b)", re.I)
RX_CC_CANDIDATE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
RX_IPV4_CANDIDATE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
RX_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9\-_.=]+")
RX_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
RX_PASSWORD_FIELD = re.compile(
    r'(?:password|passwd|pwd)["\']?\s*[:=]\s*["\']?([^"\',&\s]{6,})',
    re.IGNORECASE,
)
RX_APIKEY_CANDIDATE = re.compile(r"\b[A-Za-z0-9_\-]{32,64}\b")

# Security patterns
RX_SQLI = re.compile(
    r"(?:\bunion\b[\s\S]{0,40}\bselect\b)|(?:'\s*or\s*'?\d)|(?:--\s)|"
    r"(?:\bor\s+1\s*=\s*1\b)|(?:;\s*drop\s+table)|(?:sleep\(\d+\))|(?:benchmark\()",
    re.IGNORECASE,
)
RX_XSS = re.compile(
    r"(?:<script[^>]*>)|(?:javascript:)|(?:onerror\s*=)|(?:onload\s*=)|"
    r"(?:<img[^>]+src\s*=\s*['\"]?x)|(?:\balert\s*\()",
    re.IGNORECASE,
)
RX_SSRF = re.compile(
    r"(?:https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|169\.254\.169\.254|"
    r"10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+))",
    re.IGNORECASE,
)
RX_OPEN_REDIRECT = re.compile(
    r"(?:[?&](?:url|next|redirect|return|dest|continue|target|goto|r)=)"
    r"(?:https?:)?//",
    re.IGNORECASE,
)
RX_CSRF_NAME = re.compile(
    r"(csrf|xsrf|authenticity[_-]?token|__requestverificationtoken)", re.IGNORECASE
)
RX_SECRETISH_VALUE = re.compile(r"^[A-Za-z0-9_\-+/=%\.]+$")


# ---------------------------------------------------------------------------
# Validators (fix #1)
# ---------------------------------------------------------------------------
def _luhn_ok(num: str) -> bool:
    digits = [int(c) for c in num if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    odd = digits[-1::-2]
    even = digits[-2::-2]
    total = sum(odd) + sum(sum(divmod(d * 2, 10)) for d in even)
    return total % 10 == 0


def _looks_like_timestamp(num: str) -> bool:
    """Unix ms in 2001–2286: 13 digits starting with 1."""
    if len(num) != 13:
        return False
    try:
        n = int(num)
    except ValueError:
        return False
    return 946_684_800_000 <= n <= 9_999_999_999_999


def _is_false_positive(kind: str, match: str, location: str, context: str) -> bool:
    if kind == "phone":
        if _looks_like_timestamp(match):
            return True
        if len(match) == 10 and match[0] not in "6789":
            return True
        if len(match) in (11, 13):
            return True
    if kind == "credit_card":
        if _looks_like_timestamp(match):
            return True
        if not _luhn_ok(match):
            return True
    if kind == "aadhar":
        digits = re.sub(r"\D", "", match)
        if len(digits) != 12 or digits[0] in "01":
            return True
        i = context.find(match)
        if i > 0 and context[i - 1].isdigit():
            return True
        if i + len(match) < len(context) and context[i + len(match)].isdigit():
            return True
        if "%" in context[max(0, i - 20):i]:
            return True
    if kind == "ip_address":
        if "user-agent" in location.lower():
            return True
        parts = match.split(".")
        try:
            if any(int(p) > 255 for p in parts):
                return True
            if parts[0] in {"0", "127"} and all(p == "0" for p in parts[1:]):
                return True
            if all(p == "0" for p in parts[1:]):
                return True
        except ValueError:
            return True
    if kind == "api_key_like":
        if len(match) < 40 and re.search(r"[-_]", match):
            return True
        i = context.find(match)
        if i > 0 and context[i - 1].isalnum():
            return True
        if i + len(match) < len(context) and context[i + len(match)].isalnum():
            return True
    return False


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _looks_secretish(value: str, min_len: int = 20, threshold: float = 3.5) -> bool:
    if len(value) < min_len:
        return False
    if not RX_SECRETISH_VALUE.match(value):
        return False
    return _shannon_entropy(value) > threshold


# ---------------------------------------------------------------------------
# Cookie parsers (fix #3)
# ---------------------------------------------------------------------------
def _parse_set_cookie(value: str) -> Dict[str, Any]:
    parts = [p.strip() for p in value.split(";") if p.strip()]
    if not parts:
        return {}
    name, _, first_val = parts[0].partition("=")
    if not name:
        return {}
    cookie: Dict[str, Any] = {"name": name.strip(), "value": first_val.strip()}
    for attr in parts[1:]:
        k, _, v = attr.partition("=")
        k = k.strip().lower()
        v = v.strip()
        if k == "secure":
            cookie["secure"] = True
        elif k == "httponly":
            cookie["httpOnly"] = True
        elif k == "samesite":
            cookie["sameSite"] = v
        elif k == "domain":
            cookie["domain"] = v
        elif k == "path":
            cookie["path"] = v
        elif k == "expires":
            cookie["expires"] = v
        elif k == "max-age":
            cookie["maxAge"] = v
    return cookie


def _parse_cookie_header(value: str) -> List[Dict[str, Any]]:
    out = []
    for pair in value.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, _, val = pair.partition("=")
        out.append({"name": name.strip(), "value": val.strip()})
    return out


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class Finding:
    category: str
    severity: str
    title: str
    detail: str
    url: str = ""
    evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EntryView:
    index: int
    url: str
    method: str
    status: int
    started: str
    time_ms: float
    timings: Dict[str, float]
    req_headers: List[Tuple[str, str]]
    req_header_map: Dict[str, str]
    res_headers: List[Tuple[str, str]]
    res_header_map: Dict[str, str]
    query: Dict[str, List[str]]
    request_body: str
    response_body: str
    response_mime: str
    response_size: int
    cookies_sent: List[Dict[str, Any]]
    cookies_set: List[Dict[str, Any]]
    path_pattern: str
    domain: str
    is_api: bool
    is_navigation: bool
    is_redirect: bool
    is_static: bool
    is_tracker: bool
    redirect_location: str


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------
class AdvancedHARAnalyzer:
    def __init__(
        self,
        har_file: str,
        analysis_file: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.har_file = har_file
        base = har_file.rsplit(".", 1)[0]
        self.analysis_file = analysis_file or base + "_advanced_analysis.json"
        self.cfg = self._merge_config(config or {})
        self.har_data: Dict[str, Any] = {}
        self.entries: List[Dict[str, Any]] = []
        self.views: List[EntryView] = []

        self.api_endpoints: Dict[str, Dict[str, Any]] = {}
        self.tracker_endpoints: Dict[str, Dict[str, Any]] = {}
        self.token_correlation: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.sensitive_data: List[Dict[str, Any]] = []
        self.session_flows: Dict[str, Any] = {}
        self.entry_timeline: List[Dict[str, Any]] = []
        self.findings: List[Finding] = []
        self.timing_stats: Dict[str, Any] = {}
        self.cookie_audit: Dict[str, Any] = {}
        self.query_analysis: Dict[str, Any] = {}
        self.redirect_chains: List[Dict[str, Any]] = []
        self.cache_analysis: Dict[str, Any] = {}
        self.bandwidth: Dict[str, Any] = {}
        self.error_rates: Dict[str, Any] = {}
        self.security_report: Dict[str, Any] = {}

        self.load_har()
        self._preprocess()

    # -- config ------------------------------------------------------------
    @staticmethod
    def _merge_config(user: Dict[str, Any]) -> Dict[str, Any]:
        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)
            else:
                merged[k] = v
        return merged

    # -- loading -----------------------------------------------------------
    def load_har(self) -> None:
        if not os.path.isfile(self.har_file):
            raise FileNotFoundError(self.har_file)
        with open(self.har_file, "r", encoding="utf-8", errors="replace") as f:
            self.har_data = json.load(f)
        if not isinstance(self.har_data, dict):
            raise ValueError("HAR root must be a JSON object")
        log = self.har_data.get("log")
        if not isinstance(log, dict) or not isinstance(log.get("entries"), list):
            raise ValueError("HAR missing log.entries list")
        self.entries = log["entries"]
        LOG.info("Loaded %d entries from %s", len(self.entries), self.har_file)

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _iter_kv(items: Any) -> Iterable[Tuple[str, str]]:
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    yield str(it.get("name", "")), str(it.get("value", ""))
        elif isinstance(items, dict):
            for k, v in items.items():
                yield str(k), str(v)

    @staticmethod
    def _extract_post_body(request: Dict[str, Any]) -> str:
        pd = request.get("postData")
        if not pd:
            return ""
        if isinstance(pd, str):
            return pd
        if not isinstance(pd, dict):
            return ""

        text = pd.get("text")
        if isinstance(text, str) and text:
            return text

        params = pd.get("params")
        if isinstance(params, list) and params:
            chunks: List[str] = []
            for p in params:
                if not isinstance(p, dict):
                    continue
                if "string" in p and isinstance(p["string"], str):
                    chunks.append(p["string"])
                else:
                    chunks.append(f"{p.get('name','')}={p.get('value','')}")
            return "&".join(chunks)
        return ""

    @staticmethod
    def _extract_response_body(response: Dict[str, Any], max_bytes: int) -> str:
        content = response.get("content")
        if not isinstance(content, dict):
            return ""
        text = content.get("text")
        if not isinstance(text, str):
            return ""
        return text[:max_bytes] if len(text) > max_bytes else text

    @staticmethod
    def _path_pattern(path: str) -> str:
        p = RX_ID_PATH.sub("/{id}", path)
        p = RX_OBJECTID_PATH.sub("/{objectId}", p)
        p = RX_TOKEN_PATH.sub("/{token}", p)
        p = RX_CONTENT_HASH.sub("-{hash}", p)
        p = RX_EXT.sub("", p)
        return p or "/"

    def _is_static_asset(self, url: str) -> bool:
        if not self.cfg.get("filter_static_assets"):
            return False
        try:
            path = urlparse(url).path.lower()
        except Exception:
            return False
        if any(path.endswith(ext) for ext in self.cfg["static_extensions"]):
            return True
        if any(hint in path for hint in self.cfg["static_path_hints"]):
            return True
        return False

    def _is_tracker(self, url: str) -> bool:
        if not self.cfg.get("filter_tracker_domains"):
            return False
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            return False
        if not host:
            return False
        host_no_port = host.split(":")[0]
        for td in self.cfg["tracker_domains"]:
            if host_no_port == td or host_no_port.endswith("." + td):
                return True
        return False

    # -- preprocessing (fixes #3, #4, #5, #6, #7) -------------------------
    def _preprocess(self) -> None:
        max_body = int(self.cfg["max_body_scan_bytes"])
        views: List[EntryView] = []

        for i, entry in enumerate(self.entries):
            if not isinstance(entry, dict):
                continue
            req = entry.get("request") or {}
            res = entry.get("response") or {}
            if not isinstance(req, dict) or not isinstance(res, dict):
                continue

            url = str(req.get("url", ""))
            method = str(req.get("method", "")).upper()
            try:
                status = int(res.get("status", 0) or 0)
            except (TypeError, ValueError):
                status = 0
            started = str(entry.get("startedDateTime", ""))
            try:
                time_ms = float(entry.get("time", 0) or 0)
            except (TypeError, ValueError):
                time_ms = 0.0

            timings_raw = entry.get("timings") or {}
            timings: Dict[str, float] = {}
            if isinstance(timings_raw, dict):
                for k, v in timings_raw.items():
                    try:
                        timings[k] = float(v) if v is not None and v >= 0 else 0.0
                    except (TypeError, ValueError):
                        timings[k] = 0.0

            try:
                parsed = urlparse(url)
                query = parse_qs(parsed.query, keep_blank_values=True)
                path = parsed.path or "/"
                domain = parsed.netloc
            except Exception:
                query, path, domain = {}, "/", ""

            path_pattern = self._path_pattern(path)

            req_headers = list(self._iter_kv(req.get("headers")))
            res_headers = list(self._iter_kv(res.get("headers")))
            req_map = {k.lower(): v for k, v in req_headers if k}
            res_map = {k.lower(): v for k, v in res_headers if k}

            request_body = self._extract_post_body(req)
            response_body = self._extract_response_body(res, max_body)

            response_mime = ""
            response_size = len(response_body)
            content = res.get("content")
            if isinstance(content, dict):
                response_mime = str(content.get("mimeType", "") or "")

                # fix #4: prefer wire size (compression), then bodySize, then text length
                comp = content.get("compression")
                body_size = content.get("bodySize")
                size_field = content.get("size")

                for cand in (comp, size_field, body_size):
                    try:
                        n = int(cand) if cand is not None else 0
                    except (TypeError, ValueError):
                        n = 0
                    if n > 0:
                        response_size = n
                        break
                else:
                    response_size = len(response_body)

            # fix #3: cookies from structured arrays + Set-Cookie / Cookie headers
            cookies_sent = [c for c in (req.get("cookies") or []) if isinstance(c, dict)]
            cookies_set = [c for c in (res.get("cookies") or []) if isinstance(c, dict)]

            if not cookies_set:
                for hk, hv in res_headers:
                    if hk.lower() == "set-cookie":
                        for line in re.split(r"[\r\n]+", hv):
                            parsed_c = _parse_set_cookie(line)
                            if parsed_c.get("name"):
                                cookies_set.append(parsed_c)

            if not cookies_sent:
                for hk, hv in req_headers:
                    if hk.lower() == "cookie":
                        cookies_sent.extend(_parse_cookie_header(hv))

            mime_l = response_mime.lower()
            is_navigation = "text/html" in mime_l
            is_api = (
                "/api" in url.lower()
                or "/graphql" in url.lower()
                or "/v1/" in url.lower()
                or "/v2/" in url.lower()
                or "application/json" in mime_l
                or (method in {"POST", "PUT", "PATCH", "DELETE"} and not is_navigation)
            )
            is_redirect = 300 <= status < 400
            redirect_location = res_map.get("location", "")

            is_static = self._is_static_asset(url)
            is_tracker = self._is_tracker(url)

            views.append(
                EntryView(
                    index=i,
                    url=url,
                    method=method,
                    status=status,
                    started=started,
                    time_ms=time_ms,
                    timings=timings,
                    req_headers=req_headers,
                    req_header_map=req_map,
                    res_headers=res_headers,
                    res_header_map=res_map,
                    query=query,
                    request_body=request_body,
                    response_body=response_body,
                    response_mime=response_mime,
                    response_size=response_size,
                    cookies_sent=cookies_sent,
                    cookies_set=cookies_set,
                    path_pattern=path_pattern,
                    domain=domain,
                    is_api=is_api,
                    is_navigation=is_navigation,
                    is_redirect=is_redirect,
                    is_static=is_static,
                    is_tracker=is_tracker,
                    redirect_location=redirect_location,
                )
            )

        self.views = views
        n_static = sum(1 for v in views if v.is_static)
        n_tracker = sum(1 for v in views if v.is_tracker)
        LOG.info(
            "Preprocessed %d entries (%d static, %d tracker)",
            len(views), n_static, n_tracker,
        )

    # -- tokens ------------------------------------------------------------
    def correlate_tokens_with_requests(self) -> Dict[str, Dict[str, int]]:
        self.token_correlation = defaultdict(list)

        for v in self.views:
            endpoint_key = f"{v.domain}{v.path_pattern}"

            auth = v.req_header_map.get("authorization", "")
            if auth:
                low = auth.lower()
                if low.startswith("bearer "):
                    self._record_token(endpoint_key, "Bearer", auth[7:].strip(), v.url)
                elif low.startswith("basic "):
                    self._record_token(endpoint_key, "Basic", auth[6:].strip(), v.url)

            for k, val in v.req_header_map.items():
                if k in {"authorization", "cookie", "host", "content-length",
                         "content-type", "user-agent", "referer", "origin",
                         "accept", "accept-encoding", "accept-language",
                         "connection", "cache-control", "pragma", "if-none-match"}:
                    continue
                if any(t in k for t in ("token", "api", "secret", "auth", "key")):
                    if isinstance(val, str) and len(val) >= 20 and val.lower() not in {"true", "false", "null"}:
                        self._record_token(endpoint_key, f"Header:{k}", val, v.url)

            for qk, qvals in v.query.items():
                if any(t in qk.lower() for t in
                       ("token", "api_key", "apikey", "access_token", "auth", "key", "secret")):
                    for qv in qvals:
                        if len(qv) >= 20:
                            self._record_token(endpoint_key, f"Query:{qk}", qv, v.url)

        token_endpoints: Dict[str, Dict[str, int]] = {}
        for endpoint, tokens in self.token_correlation.items():
            counter = Counter(t["type"] for t in tokens)
            token_endpoints[endpoint] = dict(counter)

        LOG.info("Found %d endpoints with token usage", len(self.token_correlation))
        return token_endpoints

    def _record_token(self, endpoint: str, ttype: str, token: str, url: str) -> None:
        sample_len = int(self.cfg["sensitive_sample_len"])
        masked = token[:sample_len] + "..." if len(token) > sample_len else token
        self.token_correlation[endpoint].append(
            {"type": ttype, "value": masked, "url": url}
        )

    # -- endpoints (fixes #5, #6, #7) -------------------------------------
    def analyze_api_endpoints(self) -> Dict[str, Dict[str, Any]]:
        api_buckets: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"methods": set(), "count": 0, "statuses": [], "urls": []}
        )
        tracker_buckets: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"methods": set(), "count": 0, "statuses": []}
        )

        for v in self.views:
            # fix #7: separate trackers
            if v.is_tracker:
                tk = f"{v.method} {v.domain}{v.path_pattern}"
                tracker_buckets[tk]["methods"].add(v.method)
                tracker_buckets[tk]["count"] += 1
                tracker_buckets[tk]["statuses"].append(v.status)
                continue

            # fix #5: skip static assets
            if v.is_static:
                continue

            # fix #6: include host in key
            key = f"{v.method} {v.domain}{v.path_pattern}"
            b = api_buckets[key]
            b["methods"].add(v.method)
            b["count"] += 1
            b["statuses"].append(v.status)
            b["urls"].append(v.url)

        self.api_endpoints = dict(
            sorted(api_buckets.items(), key=lambda x: x[1]["count"], reverse=True)
        )
        self.tracker_endpoints = dict(
            sorted(tracker_buckets.items(), key=lambda x: x[1]["count"], reverse=True)
        )
        LOG.info(
            "Found %d API endpoints (%d tracker endpoints filtered)",
            len(self.api_endpoints), len(self.tracker_endpoints),
        )
        return self.api_endpoints

    # -- sensitive data (fix #1) -------------------------------------------
    def detect_sensitive_data(self) -> List[Dict[str, Any]]:
        patterns: Dict[str, re.Pattern] = {
            "email": RX_EMAIL,
            "phone": RX_PHONE_CANDIDATE,
            "aadhar": RX_AADHAR_CANDIDATE,
            "pan": RX_PAN,
            "date_of_birth": RX_DOB,
            "salary": RX_SALARY,
            "credit_card": RX_CC_CANDIDATE,
            "ip_address": RX_IPV4_CANDIDATE,
            "bearer_token": RX_BEARER,
            "jwt": RX_JWT,
            "password": RX_PASSWORD_FIELD,
            "api_key_like": RX_APIKEY_CANDIDATE,
        }
        sample_len = int(self.cfg["sensitive_sample_len"])
        max_body = int(self.cfg["max_body_scan_bytes"])
        found: List[Dict[str, Any]] = []

        def scan(text: str, location: str, url: str, idx: int) -> None:
            if not text or len(text) > max_body:
                return
            for name, rx in patterns.items():
                for m in rx.finditer(text):
                    match = m.group(0)
                    if isinstance(match, tuple):
                        match = match[0] if match else ""
                    if not match or len(match) < 4:
                        continue
                    if _is_false_positive(name, match, location, text):
                        continue
                    masked = match[:sample_len] + "..." if len(match) > sample_len else match
                    found.append({
                        "type": name,
                        "value": masked,
                        "location": location,
                        "url": url[:120],
                        "entry": idx,
                    })

        for v in self.views:
            for k, val in v.req_headers:
                scan(val, f"{k} header", v.url, v.index)
            scan(v.request_body, "request body", v.url, v.index)
            scan(v.response_body, "response body", v.url, v.index)
            for qk, qvals in v.query.items():
                for qv in qvals:
                    scan(qv, f"query:{qk}", v.url, v.index)

        self.sensitive_data = found
        LOG.info("Found %d sensitive-data occurrences (after filtering)", len(found))
        return found

    # -- session flow ------------------------------------------------------
    def analyze_session_flow(self) -> Dict[str, Any]:
        nav_events = []
        api_calls = []
        for v in self.views:
            if v.is_navigation:
                nav_events.append(
                    {"timestamp": v.started, "url": v.url[:120], "status": v.status}
                )
            elif v.is_api and not v.is_tracker:
                api_calls.append({
                    "timestamp": v.started,
                    "method": v.method,
                    "url": v.url[:120],
                    "status": v.status,
                })
        self.session_flows = {
            "navigation_events": len(nav_events),
            "api_calls": len(api_calls),
            "navigations": nav_events[:10],
            "apis": api_calls[:20],
        }
        LOG.info("Session flow: %d navigations, %d API calls",
                 len(nav_events), len(api_calls))
        return self.session_flows

    # -- timeline ----------------------------------------------------------
    def generate_timeline(self, limit: int = 500) -> List[Dict[str, Any]]:
        tl = []
        for v in self.views[:limit]:
            tl.append({
                "time": v.started,
                "method": v.method,
                "url": v.url[:120],
                "status": v.status,
                "duration_ms": v.time_ms,
            })
        self.entry_timeline = tl
        LOG.info("Generated timeline with %d events", len(tl))
        return tl

    # -- timing (fix #2) ---------------------------------------------------
    def analyze_timing(self) -> Dict[str, Any]:
        sums: Dict[str, float] = defaultdict(float)
        counts: Dict[str, int] = defaultdict(int)
        slow: List[Tuple[float, str, str]] = []
        entries_with_time = 0

        for v in self.views:
            if v.time_ms > 0:
                entries_with_time += 1
                slow.append((v.time_ms, v.method, v.url))
            for phase in ("blocked", "dns", "connect", "ssl", "send", "wait", "receive"):
                val = v.timings.get(phase, 0.0)
                if val > 0:
                    sums[phase] += val
                    counts[phase] += 1

        if entries_with_time == 0:
            LOG.warning(
                "No timing data in HAR — entries have time=0/null timings. "
                "This HAR was likely written by a privacy-stripping tool or "
                "was captured with DevTools timing fields disabled."
            )

        averages = {k: round(sums[k] / counts[k], 2) for k in sums if counts[k]}
        slow.sort(reverse=True)
        top_slow = [
            {"duration_ms": round(d, 2), "method": m, "url": u[:120]}
            for d, m, u in slow[:20]
        ]

        self.timing_stats = {
            "entries_with_timing": entries_with_time,
            "totals_ms": {k: round(v, 2) for k, v in sums.items()},
            "averages_ms": averages,
            "slowest": top_slow,
        }
        LOG.info("Timing: %d/%d entries have timing data",
                 entries_with_time, len(self.views))
        return self.timing_stats

    # -- cookies -----------------------------------------------------------
    def analyze_cookies(self) -> Dict[str, Any]:
        set_cookie_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "secure": 0, "httponly": 0,
                     "samesite": Counter(), "domains": set(),
                     "paths": set(), "expires": []}
        )
        sent_names: Counter = Counter()

        for v in self.views:
            for c in v.cookies_set:
                name = str(c.get("name", ""))
                if not name:
                    continue
                st = set_cookie_stats[name]
                st["count"] += 1
                if c.get("secure"):
                    st["secure"] += 1
                if c.get("httpOnly"):
                    st["httponly"] += 1
                ss = c.get("sameSite")
                if ss:
                    st["samesite"][str(ss).lower()] += 1
                if c.get("domain"):
                    st["domains"].add(str(c["domain"]))
                if c.get("path"):
                    st["paths"].add(str(c["path"]))
                if c.get("expires"):
                    st["expires"].append(str(c["expires"]))
            for c in v.cookies_sent:
                nm = str(c.get("name", ""))
                if nm:
                    sent_names[nm] += 1

        cookies = {}
        for name, st in set_cookie_stats.items():
            cookies[name] = {
                "set_count": st["count"],
                "secure": st["secure"],
                "httpOnly": st["httponly"],
                "sameSite": dict(st["samesite"]),
                "domains": sorted(st["domains"]),
                "paths": sorted(st["paths"]),
                "insecure": st["count"] - st["secure"],
                "no_httponly": st["count"] - st["httponly"],
            }
            if st["count"] > st["secure"]:
                self.findings.append(Finding(
                    "cookie",
                    "medium" if st["count"] - st["secure"] < 3 else "high",
                    f"Cookie '{name}' set without Secure flag",
                    f"{st['count'] - st['secure']} of {st['count']} Set-Cookie occurrences missing Secure",
                ))
            if st["count"] > st["httponly"]:
                self.findings.append(Finding(
                    "cookie",
                    "medium",
                    f"Cookie '{name}' set without HttpOnly flag",
                    f"{st['count'] - st['httponly']} of {st['count']} Set-Cookie occurrences missing HttpOnly",
                ))
            if not st["samesite"]:
                self.findings.append(Finding(
                    "cookie",
                    "low",
                    f"Cookie '{name}' has no SameSite attribute",
                    "Consider SameSite=Lax or Strict",
                ))

        self.cookie_audit = {
            "unique_cookies_set": len(cookies),
            "unique_cookies_sent": len(sent_names),
            "cookies": cookies,
            "sent_names": dict(sent_names.most_common(50)),
        }
        LOG.info("Cookie audit: %d unique cookies set", len(cookies))
        return self.cookie_audit

    # -- query params (fix #9) ---------------------------------------------
    def analyze_query_params(self) -> Dict[str, Any]:
        param_names: Counter = Counter()
        sensitive_in_url: List[Dict[str, Any]] = []
        suspicious_kw = ("token", "auth", "key", "secret", "password",
                         "passwd", "session", "jwt", "signature", "sig")

        threshold = float(self.cfg["security"]["high_entropy_threshold"])
        min_len = int(self.cfg["security"]["high_entropy_min_len"])

        for v in self.views:
            if v.is_tracker or v.is_static:
                continue
            for k, vals in v.query.items():
                param_names[k] += 1
                # name-based
                if any(s in k.lower() for s in suspicious_kw):
                    sensitive_in_url.append({
                        "param": k,
                        "url": v.url[:160],
                        "count": len(vals),
                        "reason": "name",
                    })
                    continue
                # fix #9: entropy-based
                for qv in vals:
                    if _looks_secretish(qv, min_len, threshold):
                        sensitive_in_url.append({
                            "param": k,
                            "url": v.url[:160],
                            "count": len(vals),
                            "reason": "entropy",
                            "sample": qv[:40] + "..." if len(qv) > 40 else qv,
                        })
                        break

        pollution = [
            {"url": v.url[:160], "params": [k for k, vals in v.query.items() if len(vals) > 1]}
            for v in self.views
            if any(len(vals) > 1 for vals in v.query.values())
        ]

        self.query_analysis = {
            "unique_param_names": len(param_names),
            "top_params": dict(param_names.most_common(30)),
            "sensitive_in_url": sensitive_in_url[:100],
            "sensitive_in_url_count": len(sensitive_in_url),
            "parameter_pollution_candidates": pollution[:20],
        }
        if sensitive_in_url:
            self.findings.append(Finding(
                "url",
                "medium",
                f"{len(sensitive_in_url)} sensitive/high-entropy parameters appear in URLs",
                "Tokens in query strings are logged by servers, proxies, and CDNs",
            ))
        LOG.info("Query params: %d unique names, %d flagged",
                 len(param_names), len(sensitive_in_url))
        return self.query_analysis

    # -- redirects ---------------------------------------------------------
    def analyze_redirects(self) -> List[Dict[str, Any]]:
        chains: List[Dict[str, Any]] = []
        for v in self.views:
            if not v.is_redirect:
                continue
            loc = v.redirect_location
            entry: Dict[str, Any] = {
                "from": v.url,
                "status": v.status,
                "location": loc,
            }
            if loc.startswith("http://"):
                entry["downgrade"] = True
                self.findings.append(Finding(
                    "redirect", "high", "Redirect to plain HTTP",
                    f"{v.url} → {loc}", url=v.url,
                ))
            if RX_OPEN_REDIRECT.search(v.url):
                entry["open_redirect_candidate"] = True
                self.findings.append(Finding(
                    "redirect", "high", "Potential open redirect",
                    f"Redirect target: {loc}", url=v.url,
                ))
            chains.append(entry)

        self.redirect_chains = chains
        LOG.info("Redirect analysis: %d redirect responses", len(chains))
        return chains

    # -- caching -----------------------------------------------------------
    def analyze_cache(self) -> Dict[str, Any]:
        cacheable = 0
        not_modified = 0
        cache_control_seen: Counter = Counter()
        no_store = 0

        for v in self.views:
            if v.status == 304:
                not_modified += 1
            cc = v.res_header_map.get("cache-control", "")
            if cc:
                cache_control_seen[cc[:120]] += 1
                if "no-store" in cc.lower():
                    no_store += 1
                elif "max-age" in cc.lower() or "public" in cc.lower():
                    cacheable += 1

        self.cache_analysis = {
            "not_modified_304": not_modified,
            "cacheable_responses": cacheable,
            "no_store_responses": no_store,
            "top_cache_control_values": dict(cache_control_seen.most_common(20)),
        }
        LOG.info("Cache: %d cacheable, %d 304s", cacheable, not_modified)
        return self.cache_analysis

    # -- bandwidth ---------------------------------------------------------
    def analyze_bandwidth(self) -> Dict[str, Any]:
        total = 0
        per_endpoint: Dict[str, int] = defaultdict(int)
        comp_ratios: List[Tuple[float, str]] = []

        for v in self.views:
            size = v.response_size or 0
            total += size
            key = f"{v.method} {v.domain}{v.path_pattern}"
            per_endpoint[key] += size

            content = (self.entries[v.index].get("response") or {}).get("content") or {}
            if isinstance(content, dict):
                try:
                    comp = float(content.get("compression", 0) or 0)
                except (TypeError, ValueError):
                    comp = 0.0
                try:
                    body = float(content.get("bodySize", 0) or 0)
                except (TypeError, ValueError):
                    body = 0.0
                if comp > 0 and body > comp:
                    comp_ratios.append((body / comp, v.url[:120]))

        per_endpoint_sorted = sorted(per_endpoint.items(), key=lambda x: x[1], reverse=True)
        comp_ratios.sort(reverse=True)

        self.bandwidth = {
            "total_bytes": total,
            "total_human": _human_bytes(total),
            "top_endpoints": [
                {"endpoint": ep, "bytes": b, "human": _human_bytes(b)}
                for ep, b in per_endpoint_sorted[:20]
            ],
            "top_compression_ratios": [
                {"ratio": round(r, 2), "url": u} for r, u in comp_ratios[:10]
            ],
        }
        LOG.info("Bandwidth: total %s", _human_bytes(total))
        return self.bandwidth

    # -- error rates -------------------------------------------------------
    def analyze_error_rates(self) -> Dict[str, Any]:
        per_endpoint: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"total": 0, "4xx": 0, "5xx": 0, "3xx": 0}
        )
        for v in self.views:
            if v.is_tracker:
                continue
            key = f"{v.method} {v.domain}{v.path_pattern}"
            st = per_endpoint[key]
            st["total"] += 1
            if 400 <= v.status < 500:
                st["4xx"] += 1
            elif 500 <= v.status < 600:
                st["5xx"] += 1
            elif 300 <= v.status < 400:
                st["3xx"] += 1

        rates = {}
        for k, st in per_endpoint.items():
            rates[k] = {
                **st,
                "error_rate": round((st["4xx"] + st["5xx"]) / st["total"], 4) if st["total"] else 0.0,
            }

        worst = sorted(rates.items(), key=lambda x: x[1]["error_rate"], reverse=True)[:20]
        self.error_rates = {
            "endpoints": rates,
            "worst": [{"endpoint": k, **v} for k, v in worst if v["error_rate"] > 0],
        }
        return self.error_rates

    # -- pattern scanning --------------------------------------------------
    def _scan_patterns(
        self, rx: re.Pattern, category: str, severity: str, title: str
    ) -> List[Finding]:
        out: List[Finding] = []
        for v in self.views:
            targets = [v.url, v.request_body]
            for qv in v.query.values():
                targets.extend(qv)
            for t in targets:
                if not isinstance(t, str) or not t:
                    continue
                m = rx.search(t)
                if m:
                    out.append(Finding(
                        category, severity, title,
                        f"Matched: {m.group(0)[:80]}",
                        url=v.url[:200],
                        evidence=t[:200],
                    ))
        return out

    def detect_security_issues(self) -> List[Finding]:
        if self.findings:
            return self.findings

        findings: List[Finding] = []
        findings += self._scan_patterns(RX_SQLI, "injection", "high", "Possible SQL injection payload")
        findings += self._scan_patterns(RX_XSS, "xss", "high", "Possible XSS payload")
        findings += self._scan_patterns(RX_SSRF, "ssrf", "medium", "SSRF-style internal URL in parameters")
        findings += self._scan_patterns(RX_OPEN_REDIRECT, "redirect", "medium", "Possible open redirect parameter")

        # HTTPS (skip localhost + trackers)
        insecure = [
            v for v in self.views
            if v.url.startswith("http://")
            and "localhost" not in v.url
            and "127.0.0.1" not in v.url
            and not v.is_tracker
        ]
        if insecure:
            findings.append(Finding(
                "transport", "high",
                f"{len(insecure)} plain-HTTP requests",
                "Credentials/tokens may transit unencrypted",
                url=insecure[0].url[:160],
            ))

        # Missing security headers on real app HTML (skip trackers)
        required = self.cfg["security"]["required_headers"]
        html_views = [v for v in self.views if v.is_navigation and not v.is_tracker]
        if html_views:
            seen: Set[str] = set()
            for v in html_views:
                seen |= set(v.res_header_map.keys())
            missing = [h for h in required if h not in seen]
            if missing:
                findings.append(Finding(
                    "headers", "medium",
                    f"Missing security headers: {', '.join(missing)}",
                    f"Absent across {len(html_views)} HTML responses",
                ))

        # CSRF token check
        csrf_present = any(
            RX_CSRF_NAME.search(k) or RX_CSRF_NAME.search(v)
            for view in self.views
            for k, v in view.req_headers
        ) or any(
            RX_CSRF_NAME.search(view.request_body or "")
            for view in self.views
            if view.request_body
        )
        state_changing = [
            v for v in self.views
            if v.method in {"POST", "PUT", "PATCH", "DELETE"} and not v.is_tracker
        ]
        if state_changing and not csrf_present:
            findings.append(Finding(
                "csrf", "medium",
                "No CSRF token detected in state-changing requests",
                f"{len(state_changing)} mutation requests without CSRF-token signature",
            ))

        # Mixed content
        for v in self.views:
            if v.is_navigation and v.url.startswith("https://"):
                if re.search(r'(?:src|href)\s*=\s*["\']http://', v.response_body, re.I):
                    findings.append(Finding(
                        "mixed-content", "medium",
                        "Mixed content on HTTPS page",
                        "Page references http:// subresources",
                        url=v.url[:200],
                    ))
                    break

        findings += self._analyze_cors()
        findings += self._analyze_csp()
        findings += self._analyze_rate_limits()

        # 5xx spike over real app traffic only
        real = [v for v in self.views if not v.is_tracker and not v.is_static]
        fivexx = sum(1 for v in real if 500 <= v.status < 600)
        if real and fivexx / len(real) > 0.05:
            findings.append(Finding(
                "availability", "medium",
                f"High 5xx rate: {fivexx}/{len(real)}",
                "Server errors > 5% of app traffic",
            ))

        self.findings = findings
        return findings

    def _analyze_cors(self) -> List[Finding]:
        out: List[Finding] = []
        seen = set()
        for v in self.views:
            acao = v.res_header_map.get("access-control-allow-origin", "")
            if not acao:
                continue
            key = (acao.strip(), v.domain)
            if key in seen:
                continue
            seen.add(key)
            if acao.strip() == "*":
                acac = v.res_header_map.get("access-control-allow-credentials", "")
                sev = "high" if acac.lower() == "true" else "medium"
                out.append(Finding(
                    "cors", sev, "Wildcard CORS origin",
                    f"Access-Control-Allow-Origin: * (credentials={acac or 'false'})",
                    url=v.url[:200],
                ))
            elif "null" in acao.lower():
                out.append(Finding(
                    "cors", "high", "CORS allows null origin",
                    "Access-Control-Allow-Origin: null is unsafe",
                    url=v.url[:200],
                ))
        return out

    def _analyze_csp(self) -> List[Finding]:
        out: List[Finding] = []
        seen_hosts: Set[str] = set()
        for v in self.views:
            if v.domain in seen_hosts:
                continue
            csp = v.res_header_map.get("content-security-policy", "")
            if not csp:
                continue
            seen_hosts.add(v.domain)
            lower = csp.lower()
            if "unsafe-inline" in lower or "unsafe-eval" in lower:
                out.append(Finding(
                    "csp", "medium",
                    "CSP contains unsafe-inline / unsafe-eval",
                    csp[:200], url=v.url[:200],
                ))
            if re.search(r"default-src\s+\*", lower):
                out.append(Finding(
                    "csp", "high", "CSP allows wildcard default-src",
                    csp[:200], url=v.url[:200],
                ))
            if "report-uri" not in lower and "report-to" not in lower:
                out.append(Finding(
                    "csp", "low", "CSP has no report-uri/report-to",
                    "Violations won't be reported", url=v.url[:200],
                ))
        return out

    def _analyze_rate_limits(self) -> List[Finding]:
        out: List[Finding] = []
        throttled = [v for v in self.views if v.status == self.cfg["security"]["rate_limit_status"]]
        if throttled:
            out.append(Finding(
                "rate-limit", "info",
                f"Observed {len(throttled)} HTTP 429 responses",
                "Endpoint(s) enforce rate limiting",
                url=throttled[0].url[:200],
            ))

        window = float(self.cfg["security"]["brute_force_window_sec"])
        threshold = int(self.cfg["security"]["brute_force_threshold"])
        auth_attempts: Dict[str, List[float]] = defaultdict(list)

        for v in self.views:
            if v.method != "POST":
                continue
            if not any(k in v.path_pattern.lower() for k in ("login", "auth", "signin", "token")):
                continue
            try:
                ts = datetime.fromisoformat(v.started.replace("Z", "+00:00")).timestamp()
            except Exception:
                continue
            auth_attempts[v.path_pattern].append(ts)

        for path, times in auth_attempts.items():
            times.sort()
            for i in range(len(times) - threshold):
                if times[i + threshold] - times[i] <= window:
                    out.append(Finding(
                        "brute-force", "high",
                        f"High-frequency auth attempts on {path}",
                        f"{threshold + 1}+ POSTs within {window:.0f}s window",
                        url=path,
                    ))
                    break
        return out

    # -- upgrades ----------------------------------------------------------
    def analyze_upgrades(self) -> Dict[str, Any]:
        ws = []
        sse = []
        for v in self.views:
            upg = v.req_header_map.get("upgrade", "")
            if "websocket" in upg.lower():
                ws.append({"url": v.url[:200], "status": v.status})
            if "text/event-stream" in v.response_mime.lower():
                sse.append({"url": v.url[:200], "status": v.status})
        return {"websockets": ws, "event_streams": sse}

    # -- security report (fix #8) ------------------------------------------
    def generate_security_report(self) -> Dict[str, Any]:
        issues = self.detect_security_issues()

        # Deduplicate by (category, title, url-prefix)
        seen: Set[Tuple[str, str, str]] = set()
        deduped: List[Finding] = []
        for f in issues:
            key = (f.category, f.title, (f.url or "")[:80])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(f)

        severities = Counter(f.severity for f in deduped)
        weights = {"critical": 25, "high": 15, "medium": 5, "low": 1, "info": 0}
        penalty = sum(weights[f.severity] for f in deduped)
        score = max(0, min(100, 100 - penalty))

        self.security_report = {
            "score": score,
            "severity_counts": dict(severities),
            "findings": [f.to_dict() for f in deduped],
            "generated_at": datetime.now().isoformat(),
        }
        LOG.info("Security score: %d/100 (%d distinct findings)", score, len(deduped))
        return self.security_report

    # -- diff --------------------------------------------------------------
    @staticmethod
    def diff(har_a: str, har_b: str, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        a = AdvancedHARAnalyzer(har_a, analysis_file="/dev/null", config=cfg)
        b = AdvancedHARAnalyzer(har_b, analysis_file="/dev/null", config=cfg)

        eps_a = {f"{v.method} {v.domain}{v.path_pattern}"
                 for v in a.views if not v.is_tracker and not v.is_static}
        eps_b = {f"{v.method} {v.domain}{v.path_pattern}"
                 for v in b.views if not v.is_tracker and not v.is_static}

        sensitive_a = Counter(s["type"] for s in a.detect_sensitive_data())
        sensitive_b = Counter(s["type"] for s in b.detect_sensitive_data())

        return {
            "har_a": har_a,
            "har_b": har_b,
            "entries_a": len(a.views),
            "entries_b": len(b.views),
            "endpoints_added": sorted(eps_b - eps_a)[:200],
            "endpoints_removed": sorted(eps_a - eps_b)[:200],
            "endpoints_common": len(eps_a & eps_b),
            "sensitive_delta": {
                k: sensitive_b.get(k, 0) - sensitive_a.get(k, 0)
                for k in set(sensitive_a) | set(sensitive_b)
            },
            "findings_a": len(a.generate_security_report()["findings"]),
            "findings_b": len(b.generate_security_report()["findings"]),
            "score_a": a.security_report["score"],
            "score_b": b.security_report["score"],
        }

    # -- persistence -------------------------------------------------------
    def save_advanced_analysis(self) -> str:
        payload = {
            "summary": {
                "har_file": self.har_file,
                "total_entries": len(self.views),
                "api_endpoints": len(self.api_endpoints),
                "tracker_endpoints": len(self.tracker_endpoints),
                "static_entries": sum(1 for v in self.views if v.is_static),
                "tokens_correlated": len(self.token_correlation),
                "sensitive_data_found": len(self.sensitive_data),
                "security_issues": len(self.security_report.get("findings", [])),
            },
            "api_endpoints": {
                k: {
                    "count": v["count"],
                    "methods": sorted(v["methods"]),
                    "statuses": list(v["statuses"]),
                }
                for k, v in list(self.api_endpoints.items())[: self.cfg["top_endpoints"]]
            },
            "tracker_endpoints": {
                k: {
                    "count": v["count"],
                    "methods": sorted(v["methods"]),
                }
                for k, v in list(self.tracker_endpoints.items())[:20]
            },
            "token_correlation": {
                k: v[:10] for k, v in list(self.token_correlation.items())[:20]
            },
            "sensitive_data": self.sensitive_data[:200],
            "session_flow": self.session_flows,
            "timeline": self.entry_timeline,
            "timing": self.timing_stats,
            "cookies": self.cookie_audit,
            "query_params": self.query_analysis,
            "redirects": self.redirect_chains,
            "cache": self.cache_analysis,
            "bandwidth": self.bandwidth,
            "error_rates": self.error_rates,
            "upgrades": self.analyze_upgrades(),
            "security_report": self.security_report,
            "timestamp": datetime.now().isoformat(),
        }
        with open(self.analysis_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        LOG.info("Saved advanced analysis to %s", self.analysis_file)
        return self.analysis_file

    def save_csv(self, out_dir: str) -> List[str]:
        os.makedirs(out_dir, exist_ok=True)
        written: List[str] = []

        fp = os.path.join(out_dir, "findings.csv")
        with open(fp, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["category", "severity", "title", "detail", "url", "evidence"])
            for fd in self.security_report.get("findings", []):
                w.writerow([fd["category"], fd["severity"], fd["title"],
                            fd["detail"], fd["url"], fd["evidence"]])
        written.append(fp)

        ep = os.path.join(out_dir, "endpoints.csv")
        with open(ep, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["endpoint", "calls", "methods", "statuses"])
            for k, v in self.api_endpoints.items():
                w.writerow([k, v["count"], ";".join(sorted(v["methods"])),
                            ";".join(map(str, v["statuses"]))])
        written.append(ep)

        sp = os.path.join(out_dir, "sensitive.csv")
        with open(sp, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["type", "value", "location", "url", "entry"])
            for s in self.sensitive_data:
                w.writerow([s["type"], s["value"], s["location"], s["url"], s["entry"]])
        written.append(sp)

        ck = os.path.join(out_dir, "cookies.csv")
        with open(ck, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "set_count", "secure", "httpOnly", "sameSite",
                        "insecure", "no_httponly", "domains"])
            for name, c in self.cookie_audit.get("cookies", {}).items():
                w.writerow([name, c["set_count"], c["secure"], c["httpOnly"],
                            json.dumps(c["sameSite"]), c["insecure"],
                            c["no_httponly"], ";".join(c["domains"])])
        written.append(ck)

        LOG.info("Wrote CSV exports to %s", out_dir)
        return written

    def save_html(self, path: str) -> str:
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        findings = sorted(
            self.security_report.get("findings", []),
            key=lambda f: sev_order.get(f["severity"], 9),
        )

        def row(f: Dict[str, Any]) -> str:
            return (
                f"<tr class='{f['severity']}'>"
                f"<td>{html.escape(f['severity'])}</td>"
                f"<td>{html.escape(f['category'])}</td>"
                f"<td>{html.escape(f['title'])}</td>"
                f"<td>{html.escape(f['detail'])}</td>"
                f"<td><code>{html.escape(f['url'][:160])}</code></td>"
                "</tr>"
            )

        findings_html = "\n".join(row(f) for f in findings) or \
            "<tr><td colspan='5'>No findings</td></tr>"

        endpoint_rows = "\n".join(
            f"<tr><td>{html.escape(k)}</td><td>{v['count']}</td>"
            f"<td>{html.escape(';'.join(sorted(v['methods'])))}</td>"
            f"<td>{html.escape(str(Counter(v['statuses']).most_common()))}</td></tr>"
            for k, v in list(self.api_endpoints.items())[: self.cfg["top_endpoints"]]
        )

        sensitive_rows = "\n".join(
            f"<tr><td>{html.escape(s['type'])}</td><td>{html.escape(s['value'])}</td>"
            f"<td>{html.escape(s['location'])}</td>"
            f"<td><code>{html.escape(s['url'][:120])}</code></td></tr>"
            for s in self.sensitive_data[:200]
        )

        cookie_rows = "\n".join(
            f"<tr><td>{html.escape(n)}</td><td>{c['set_count']}</td>"
            f"<td>{c['secure']}</td><td>{c['httpOnly']}</td>"
            f"<td>{html.escape(json.dumps(c['sameSite']))}</td></tr>"
            for n, c in sorted(self.cookie_audit.get("cookies", {}).items())
        )

        score = self.security_report.get("score", "n/a")

        doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>HAR Analysis — {html.escape(self.har_file)}</title>
<style>
 body {{ font-family: -apple-system, system-ui, sans-serif; margin: 2rem; color: #222; }}
 h1, h2 {{ border-bottom: 2px solid #eee; padding-bottom: .3rem; }}
 table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }}
 th, td {{ border: 1px solid #ddd; padding: .4rem .6rem; font-size: 13px; text-align: left; }}
 th {{ background: #f5f5f5; }}
 tr.critical {{ background: #ffdddd; }} tr.high {{ background: #ffe6cc; }}
 tr.medium {{ background: #fff5cc; }} tr.low {{ background: #eaffea; }}
 tr.info {{ background: #eef6ff; }}
 .score {{ font-size: 3rem; font-weight: bold; }}
 code {{ font-family: ui-monospace, monospace; font-size: 12px; }}
</style></head><body>
<h1>HAR Analysis Report</h1>
<p><strong>File:</strong> {html.escape(self.har_file)}<br>
<strong>Entries:</strong> {len(self.views)} &nbsp;
<strong>API endpoints:</strong> {len(self.api_endpoints)} &nbsp;
<strong>Tracker endpoints:</strong> {len(self.tracker_endpoints)}<br>
<strong>Sensitive hits:</strong> {len(self.sensitive_data)} &nbsp;
<strong>Cookies:</strong> {self.cookie_audit.get('unique_cookies_set', 0)} &nbsp;
<strong>Findings:</strong> {len(findings)}</p>
<p><strong>Security Score:</strong> <span class="score">{score}</span>/100</p>

<h2>Security Findings</h2>
<table><thead><tr><th>Severity</th><th>Category</th><th>Title</th><th>Detail</th><th>URL</th></tr></thead>
<tbody>{findings_html}</tbody></table>

<h2>Top API Endpoints</h2>
<table><thead><tr><th>Endpoint</th><th>Calls</th><th>Methods</th><th>Statuses</th></tr></thead>
<tbody>{endpoint_rows}</tbody></table>

<h2>Cookies</h2>
<table><thead><tr><th>Name</th><th>Set count</th><th>Secure</th><th>HttpOnly</th><th>SameSite</th></tr></thead>
<tbody>{cookie_rows}</tbody></table>

<h2>Sensitive Data (top 200)</h2>
<table><thead><tr><th>Type</th><th>Value</th><th>Location</th><th>URL</th></tr></thead>
<tbody>{sensitive_rows}</tbody></table>

<p style="margin-top:2rem;color:#888;font-size:12px">
Generated {datetime.now().isoformat()}</p>
</body></html>"""

        with open(path, "w", encoding="utf-8") as f:
            f.write(doc)
        LOG.info("HTML report written to %s", path)
        return path

    # -- orchestration -----------------------------------------------------
    def run_all(self) -> None:
        self.analyze_api_endpoints()
        self.correlate_tokens_with_requests()
        self.detect_sensitive_data()
        self.analyze_session_flow()
        self.generate_timeline()
        self.analyze_timing()
        self.analyze_cookies()
        self.analyze_query_params()
        self.analyze_redirects()
        self.analyze_cache()
        self.analyze_bandwidth()
        self.analyze_error_rates()
        self.generate_security_report()

    def print_summary(self) -> None:
        print("\n" + "=" * 72)
        print("ADVANCED HAR ANALYSIS SUMMARY")
        print("=" * 72)
        print(f"File:               {self.har_file}")
        print(f"Entries:            {len(self.views)}")
        print(f"API endpoints:      {len(self.api_endpoints)}")
        print(f"Tracker endpoints:  {len(self.tracker_endpoints)} (excluded from API list)")
        print(f"Static entries:     {sum(1 for v in self.views if v.is_static)} (excluded)")
        print(f"Tokens:             {len(self.token_correlation)} endpoint(s) with tokens")
        print(f"Sensitive:          {len(self.sensitive_data)} occurrence(s) after filtering")
        print(f"Cookies (unique):   {self.cookie_audit.get('unique_cookies_set', 0)}")
        print(f"Security score:     {self.security_report.get('score', 'n/a')}/100")

        print("\nTop API endpoints:")
        for i, (ep, d) in enumerate(list(self.api_endpoints.items())[:10], 1):
            status_counts = dict(Counter(d["statuses"]))
            print(f"  {i:2d}. {ep}  calls={d['count']}  statuses={status_counts}")

        findings = self.security_report.get("findings", [])
        if findings:
            print("\nSecurity findings (by severity):")
            for sev in ("critical", "high", "medium", "low", "info"):
                group = [f for f in findings if f["severity"] == sev]
                if group:
                    print(f"  [{sev.upper()}] {len(group)}")
                    for f in group[:5]:
                        print(f"     - {f['title']}")

        if self.timing_stats.get("slowest"):
            print("\nSlowest requests:")
            for s in self.timing_stats["slowest"][:5]:
                print(f"  {s['duration_ms']:>8} ms  {s['method']} {s['url']}")

        print("\n" + "=" * 72)
        print(f"JSON: {self.analysis_file}")
        print("=" * 72)


def _human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="advanced_har_analyzer2",
        description="Advanced HAR analysis — patched release (v2).",
    )
    p.add_argument("har_file", nargs="?", help="Path to the input HAR file")
    p.add_argument("-o", "--output", help="Output JSON path (default: <har>_advanced_analysis.json)")
    p.add_argument("--html", help="Write HTML report to this path")
    p.add_argument("--csv", help="Write CSV exports to this directory")
    p.add_argument("--diff", metavar="OTHER_HAR", help="Compare against another HAR file")
    p.add_argument("--config", help="Path to JSON config file")
    p.add_argument("--log-file", help="Write logs to a file")
    p.add_argument("-v", "--verbose", action="count", default=0,
                   help="Increase log verbosity (-v, -vv)")
    return p


def load_config(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.har_file:
        parser.print_help()
        print("\nExamples:")
        print("  python advanced_har_analyzer2.py capture.har")
        print("  python advanced_har_analyzer2.py capture.har --html report.html --csv out_dir")
        print("  python advanced_har_analyzer2.py capture.har --diff other.har")
        print("  python advanced_har_analyzer2.py capture.har --config cfg.json -vv")
        return 0

    configure_logging(args.verbose, args.log_file)

    try:
        cfg = load_config(args.config)
    except Exception as e:
        LOG.error("Failed to load config: %s", e)
        return 2

    try:
        if args.diff:
            result = AdvancedHARAnalyzer.diff(args.har_file, args.diff, cfg)
            out = args.output or f"{args.har_file.rsplit('.', 1)[0]}_diff.json"
            with open(out, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(json.dumps(result, indent=2, default=str))
            return 0

        analyzer = AdvancedHARAnalyzer(
            args.har_file, analysis_file=args.output, config=cfg
        )
        analyzer.run_all()
        analyzer.save_advanced_analysis()

        if args.html:
            analyzer.save_html(args.html)
        if args.csv:
            analyzer.save_csv(args.csv)

        analyzer.print_summary()
        return 0

    except FileNotFoundError as e:
        LOG.error("File not found: %s", e)
        return 1
    except json.JSONDecodeError as e:
        LOG.error("Invalid JSON: %s", e)
        return 1
    except ValueError as e:
        LOG.error("Invalid HAR structure: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
