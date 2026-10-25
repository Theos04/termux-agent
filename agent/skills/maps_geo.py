"""Maps geo scrape skill — CDP scripts-library only, no LLM."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

JUNK_NAME_RE = re.compile(
    r"^(results|collapse|sponsored|directions|overview|about|menu)$",
    re.I,
)
PHONE_DIGITS_RE = re.compile(r"\d{10,13}")


class MapsGeoSkill:
    """
    Daily Maps scrape pipeline (script-first):

      dismiss-consent → wait-for-feed → inspect-and-discover
        → get-cards-via-scroll → enrich-phones → quality gate → write

    Aborts early when page content is not extractable so runs are never wasted.
    Only meaningful rows (name + phone/address/maps_url) are kept and written.
    """

    name = "maps_geo"
    DIR = "google-maps"
    SCRIPT_CONSENT = f"{DIR}/dismiss-consent"
    SCRIPT_WAIT = f"{DIR}/wait-for-feed"
    SCRIPT_INSPECT = f"{DIR}/inspect-and-discover"
    SCRIPT_SCROLL = f"{DIR}/get-cards-via-scroll"
    SCRIPT_PHONES = f"{DIR}/enrich-phones"
    SCRIPT_HARVEST = f"{DIR}/harvest-feed"
    SCRIPT_SCROLL_ONCE = f"{DIR}/scroll-once"
    SCRIPT_READ_PHONE = f"{DIR}/read-panel-phone"
    SCRIPT_SEARCH = f"{DIR}/search"

    # Stop agent after this many consecutive URL failures / empty extracts
    MAX_CONSECUTIVE_FAILS = 2
    # First URL must yield at least this many meaningful cards or abort
    MIN_MEANINGFUL_FIRST = 1
    # Jaccard / novelty saturation — stop when successive URLs add almost nothing
    SATURATION_NOVELTY_FLOOR = 0.05   # <5% new keys → count as saturated
    SATURATION_CAUTION_FLOOR = 0.15   # <15% new → caution once, then continue
    MAX_SATURATED_URLS = 2            # consecutive saturated URLs → stop
    SATURATION_JACCARD_STOP = 0.98    # batch ≈ prior batch fingerprint → stop

    def __init__(
        self,
        page_fetcher=None,
        har_manager=None,
        out_dir: Optional[str] = None,
        notify=None,
        db=None,
    ):
        self.fetcher = page_fetcher
        self.har = har_manager
        self.notify = notify or (lambda *_a, **_k: None)
        self.db = db  # optional agent.database.Database instance for DB persistence
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.out_dir = out_dir or os.path.join(root, "agent_runs")
        self.last_selectors: Dict[str, Any] = {}
        self.stop_reason: str = ""

    def _progress(self, **payload) -> None:
        try:
            self.notify("task_progress", payload)
        except Exception:
            pass

    @staticmethod
    def card_key(card: Dict[str, Any]) -> tuple:
        name = (card.get("name") or "").strip().lower()
        maps_url = (card.get("maps_url") or "").strip()
        phone = re.sub(r"\D", "", card.get("phone") or "")
        return (maps_url or name, phone)

    @classmethod
    def jaccard(cls, a: set, b: set) -> float:
        """Jaccard similarity of two key sets (1.0 = identical)."""
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        inter = len(a & b)
        union = len(a | b)
        return inter / union if union else 1.0

    @classmethod
    def novelty_rate(cls, batch_keys: set, seen_keys: set) -> float:
        """Fraction of batch keys not already in the accumulated set."""
        if not batch_keys:
            return 0.0
        return len(batch_keys - seen_keys) / len(batch_keys)

    def _run(self, script: str, args: Optional[Dict] = None, timeout: float = 120.0) -> Any:
        return self.fetcher.run_library_script(script, args=args or {}, timeout=timeout)

    def _seed_maps_results(self, cards: List[Dict[str, Any]]) -> None:
        """Expose harvested cards to enrich-phones.js via window.mapsResults."""
        try:
            payload = json.dumps(cards, ensure_ascii=False)
            self.fetcher.evaluate_js(
                f"window.mapsResults = {payload}; true",
                timeout=15.0,
            )
        except Exception:
            pass

    def scroll_cards_stepwise(
        self,
        *,
        name_css: Optional[str] = None,
        max_scrolls: int = 35,
        scroll_delay_ms: int = 1200,
        max_stable: int = 5,
        max_cards: int = 200,
    ) -> Dict[str, Any]:
        """Harvest + scroll in short CDP evals (survives Maps nav / WS quiet)."""
        merged: Dict[str, Dict[str, Any]] = {}
        last_count = 0
        stable = 0
        scrolls = 0
        ended = False

        for _ in range(max(1, max_scrolls)):
            harvest = self._run(
                self.SCRIPT_HARVEST,
                {"name_css": name_css} if name_css else {},
                timeout=25.0,
            )
            if not isinstance(harvest, dict) or not harvest.get("ok"):
                if merged:
                    break
                return {
                    "ok": False,
                    "error": (harvest or {}).get("error")
                    if isinstance(harvest, dict)
                    else "harvest failed",
                    "data": [],
                    "count": 0,
                }
            for card in harvest.get("data") or []:
                key = (card.get("maps_url") or "").split("?")[0] or (
                    card.get("name") or ""
                ).lower()
                if not key:
                    continue
                prev = merged.get(key) or {}
                merged[key] = {**prev, **{k: v for k, v in card.items() if v}}
            count = len(merged)
            ended = bool(harvest.get("end"))
            if count >= max_cards or ended:
                break
            if count == last_count:
                stable += 1
            else:
                stable = 0
            last_count = count
            if stable >= max_stable:
                break
            step = self._run(self.SCRIPT_SCROLL_ONCE, {}, timeout=15.0)
            scrolls += 1
            if isinstance(step, dict) and step.get("end"):
                ended = True
                break
            time.sleep(max(0.2, scroll_delay_ms / 1000.0))

        data = list(merged.values())
        self._seed_maps_results(data)
        return {
            "ok": True,
            "count": len(data),
            "scrolls": scrolls,
            "end": ended,
            "with_phone": sum(1 for c in data if c.get("phone")),
            "data": data,
        }

    def enrich_phones_stepwise(
        self,
        cards: List[Dict[str, Any]],
        *,
        max_places: int = 50,
        open_delay_ms: int = 1400,
        only_missing: bool = True,
    ) -> Dict[str, Any]:
        """
        Click/open each place and read the phone panel.

        Prefers navigating ``maps_url`` (reliable after feed virtualization);
        falls back to feed-click enrich script for cards still missing URLs.
        Always runs when phones are requested — list cards alone rarely have numbers.
        """
        out = [dict(c) for c in cards]
        enriched = 0
        attempted = 0
        delay = max(0.4, open_delay_ms / 1000.0)

        def _apply_phone(idx: int, phone: Optional[str]) -> None:
            nonlocal enriched
            if not phone:
                return
            prev = out[idx].get("phone")
            out[idx]["phone"] = phone
            if not prev:
                enriched += 1

        # 1) Navigate place URLs one-by-one (short CDP calls)
        for i, card in enumerate(out):
            if attempted >= max_places:
                break
            if only_missing and card.get("phone"):
                continue
            maps_url = (card.get("maps_url") or "").strip()
            if not maps_url or "/maps/place" not in maps_url:
                continue
            attempted += 1
            try:
                self.fetcher.navigate(maps_url)
                time.sleep(delay)
                # consent may reappear on place pages
                self._run(self.SCRIPT_CONSENT, {"delay_ms": 200}, timeout=15.0)
                time.sleep(0.3)
                read = self._run(self.SCRIPT_READ_PHONE, {}, timeout=20.0)
                phone = None
                if isinstance(read, dict):
                    phone = read.get("phone")
                _apply_phone(i, phone)
                self._progress(
                    label="phones",
                    step=attempted,
                    total=max_places,
                    phase=f"phone {attempted}/{max_places}",
                    cards=len(out),
                    phones=sum(1 for c in out if c.get("phone")),
                )
            except Exception as e:
                out[i]["_phone_error"] = str(e)[:120]

        # 2) Library enrich for any still-missing (feed click) if we're on a search page
        still_missing = sum(1 for c in out if not c.get("phone"))
        if still_missing and attempted < max_places:
            self._seed_maps_results(out)
            batch = self._run(
                self.SCRIPT_PHONES,
                {
                    "max_places": min(max_places - attempted, still_missing + 3),
                    "only_missing": True,
                    "open_delay_ms": open_delay_ms,
                },
                timeout=min(300.0, 12.0 * (max_places - attempted + 2)),
            )
            if isinstance(batch, dict) and batch.get("ok"):
                by_key = {}
                for c in batch.get("data") or []:
                    key = (c.get("maps_url") or "").split("?")[0] or (c.get("name") or "").lower()
                    if key:
                        by_key[key] = c
                for i, card in enumerate(out):
                    key = (card.get("maps_url") or "").split("?")[0] or (
                        card.get("name") or ""
                    ).lower()
                    other = by_key.get(key)
                    if other and other.get("phone") and not card.get("phone"):
                        out[i]["phone"] = other["phone"]
                        enriched += 1

        self._seed_maps_results(out)
        with_phone = sum(1 for c in out if c.get("phone"))
        return {
            "ok": with_phone > 0 or attempted == 0,
            "data": out,
            "enriched": enriched,
            "attempted": attempted,
            "with_phone": with_phone,
            "count": len(out),
        }

    # ── quality / meaning ─────────────────────────────────────────────

    @classmethod
    def is_meaningful(cls, card: Dict[str, Any], *, require_phone: bool = False) -> bool:
        name = (card.get("name") or "").strip()
        if len(name) < 2 or JUNK_NAME_RE.match(name):
            return False
        phone = (card.get("phone") or "").strip()
        phone_ok = bool(phone and PHONE_DIGITS_RE.search(re.sub(r"\D", "", phone) or phone))
        if require_phone:
            return phone_ok
        has_signal = bool(
            phone_ok
            or (card.get("address") or "").strip()
            or (card.get("maps_url") or "").strip()
            or card.get("rating") is not None
        )
        return has_signal

    @classmethod
    def filter_meaningful(
        cls,
        cards: List[Dict[str, Any]],
        *,
        require_phone: bool = False,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for c in cards or []:
            if not cls.is_meaningful(c, require_phone=require_phone):
                continue
            key = (
                (c.get("maps_url") or "").strip()
                or (c.get("name") or "").strip().lower(),
                re.sub(r"\D", "", c.get("phone") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    def _validate_batch(
        self,
        cards: List[Dict[str, Any]],
        *,
        require_phone: bool,
        fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        fields = fields or []
        want_phone = require_phone or "phone" in fields
        good = self.filter_meaningful(cards, require_phone=False)
        with_phone = [c for c in good if self.is_meaningful(c, require_phone=True)]
        ok = len(good) >= self.MIN_MEANINGFUL_FIRST
        if want_phone and good and not with_phone:
            # names/addresses ok but no phones yet — soft warn, still ok if maps_url present
            ok = any((c.get("maps_url") or "").strip() for c in good)
        return {
            "ok": ok,
            "raw": len(cards or []),
            "meaningful": len(good),
            "with_phone": len(with_phone),
            "cards": good,
            "reason": (
                None
                if ok
                else "no meaningful cards (need name + phone/address/maps_url)"
            ),
        }

    def _write_extract(
        self,
        *,
        goal: str,
        query: str,
        cards: List[Dict[str, Any]],
        selectors: Dict[str, Any],
        observations: List[str],
        stopped: bool,
        stop_reason: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        os.makedirs(self.out_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.out_dir, f"maps_extract_{stamp}.json")
        payload = {
            "ok": bool(cards) and not (stopped and not cards),
            "written_at": stamp,
            "goal": goal,
            "query": query,
            "count": len(cards),
            "with_phone": sum(1 for c in cards if c.get("phone")),
            "selectors": selectors,
            "stopped": stopped,
            "stop_reason": stop_reason or None,
            "observations": observations[-40:],
            "cards": cards,
            "meta": meta or {},
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
        # also a slim phones-only companion when any exist
        phones = [
            {
                "name": c.get("name"),
                "phone": c.get("phone"),
                "address": c.get("address"),
                "maps_url": c.get("maps_url"),
            }
            for c in cards
            if c.get("phone")
        ]
        if phones:
            phone_path = os.path.join(self.out_dir, f"maps_phones_{stamp}.json")
            with open(phone_path, "w", encoding="utf-8") as f:
                json.dump({"count": len(phones), "phones": phones}, f, indent=2, ensure_ascii=False)
            payload["phones_path"] = phone_path
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

        # ── persist to agent.db places table ──────────────────────────
        if self.db is not None and cards:
            try:
                db_result = self.db.store_places(cards, query=query)
                payload["db_inserted"] = db_result.get("inserted", 0)
                payload["db_updated"] = db_result.get("updated", 0)
                # rewrite JSON with DB stats
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
            except Exception as _db_err:
                import logging
                logging.getLogger(__name__).warning("store_places failed: %s", _db_err)

        return path

    # ── single URL scrape ─────────────────────────────────────────────

    def scrape_url(
        self,
        url: str,
        *,
        enrich_phones: bool = True,
        max_places: int = 25,
        scroll_args: Optional[Dict] = None,
        require_phone: bool = False,
        fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Open one Maps URL: inspect → discover selectors → scroll → validate."""
        observations: List[str] = []
        selectors: Dict[str, Any] = {}

        tab = self.fetcher.create_tab(url)
        if not tab:
            if not self.fetcher.is_connected():
                return {
                    "ok": False,
                    "error": "no CDP / failed create_tab",
                    "cards": [],
                    "url": url,
                    "abort": True,
                }
            self.fetcher.navigate(url)
            observations.append("navigated current tab")
        else:
            self.fetcher.attach_tab(tab["id"])
            observations.append(f"opened tab {tab['id'][:8]}")

        time.sleep(1.5)

        consent = self._run(self.SCRIPT_CONSENT, {"delay_ms": 500}, timeout=30.0)
        if isinstance(consent, dict):
            observations.append(f"consent clicked={consent.get('count', 0)}")
        else:
            observations.append("consent ran")

        wait = self._run(self.SCRIPT_WAIT, {"timeout_ms": 20000}, timeout=30.0)
        observations.append(
            f"wait ok={isinstance(wait, dict) and wait.get('ok')} "
            f"articles={(wait or {}).get('article_count')}"
        )
        if isinstance(wait, dict) and not wait.get("ok"):
            return {
                "ok": False,
                "error": wait.get("error") or "feed not ready",
                "cards": [],
                "url": url,
                "observations": observations,
                "abort": True,
                "selectors": selectors,
            }

        # Inspect page + discover CSS/XPath for name & phone
        inspect = self._run(self.SCRIPT_INSPECT, {"sample_limit": 8}, timeout=30.0)
        if not isinstance(inspect, dict) or not inspect.get("ok"):
            observations.append(f"inspect fail={inspect}")
            return {
                "ok": False,
                "error": (inspect or {}).get("error") if isinstance(inspect, dict) else "inspect failed",
                "cards": [],
                "url": url,
                "observations": observations,
                "abort": True,
                "selectors": selectors,
            }

        selectors = dict(inspect.get("selectors") or {})
        self.last_selectors = selectors
        observations.append(
            f"inspect extractable={inspect.get('extractable')} "
            f"samples={inspect.get('sample_count')} "
            f"name_css={selectors.get('name_css')!r} "
            f"phone_css={selectors.get('phone_css')!r} "
            f"name_xpath={selectors.get('name_xpath')!r}"
        )

        if not inspect.get("extractable"):
            page = inspect.get("page") or {}
            reason = (
                "page not extractable — no business-name hits "
                f"(consent={page.get('consent_like')} feed={page.get('has_feed')} "
                f"body_len={page.get('body_len')})"
            )
            observations.append(reason)
            return {
                "ok": False,
                "error": reason,
                "cards": [],
                "url": url,
                "observations": observations,
                "abort": True,
                "selectors": selectors,
                "inspect": inspect,
            }

        scroll_payload = dict(
            scroll_args
            or {
                "max_scrolls": 30,
                "scroll_delay_ms": 1600,
                "max_stable": 5,
                "max_cards": 200,
            }
        )
        if selectors.get("name_css"):
            scroll_payload["name_css"] = selectors["name_css"]
        if selectors.get("phone_css"):
            scroll_payload["phone_css"] = selectors["phone_css"]

        scroll = self._run(self.SCRIPT_SCROLL, scroll_payload, timeout=180.0)
        raw_cards: List[Dict[str, Any]] = []
        if isinstance(scroll, dict) and scroll.get("ok"):
            raw_cards = list(scroll.get("data") or [])
            observations.append(
                f"scroll count={scroll.get('count')} with_phone={scroll.get('with_phone')} "
                f"selectors_used={scroll.get('selectors_used')}"
            )
            self._seed_maps_results(raw_cards)
        else:
            observations.append(f"scroll fail={scroll} — trying stepwise harvest")
            step = self.scroll_cards_stepwise(
                name_css=selectors.get("name_css"),
                max_scrolls=int(scroll_payload.get("max_scrolls") or 30),
                scroll_delay_ms=int(scroll_payload.get("scroll_delay_ms") or 1200),
                max_stable=int(scroll_payload.get("max_stable") or 5),
                max_cards=int(scroll_payload.get("max_cards") or 200),
            )
            if isinstance(step, dict) and step.get("ok") and step.get("data"):
                raw_cards = list(step.get("data") or [])
                observations.append(
                    f"stepwise_scroll count={step.get('count')} scrolls={step.get('scrolls')}"
                )
            else:
                observations.append(f"stepwise_scroll fail={step}")
                return {
                    "ok": False,
                    "error": (scroll or {}).get("error")
                    if isinstance(scroll, dict)
                    else "scroll failed",
                    "cards": [],
                    "url": url,
                    "observations": observations,
                    "abort": True,
                    "selectors": selectors,
                }

        # Early quality check before expensive phone enrich
        pre = self._validate_batch(raw_cards, require_phone=False, fields=fields)
        if not pre["ok"]:
            observations.append(f"quality_fail_pre_enrich: {pre['reason']} raw={pre['raw']}")
            return {
                "ok": False,
                "error": pre["reason"],
                "cards": [],
                "url": url,
                "observations": observations,
                "abort": True,
                "selectors": selectors,
                "quality": pre,
            }

        cards = list(pre["cards"])
        fields_l = [f.lower() for f in (fields or [])]
        want_phone = enrich_phones or "phone" in fields_l or require_phone

        if want_phone:
            missing = sum(1 for c in cards if not c.get("phone"))
            if missing:
                # Always open each place panel — list cards almost never show phones.
                phones = self.enrich_phones_stepwise(
                    cards,
                    max_places=min(max_places, max(missing, 1)),
                    only_missing=True,
                    open_delay_ms=1400,
                )
                if isinstance(phones, dict):
                    cards = list(phones.get("data") or cards)
                    observations.append(
                        f"enrich_stepwise enriched={phones.get('enriched')} "
                        f"attempted={phones.get('attempted')} "
                        f"with_phone={phones.get('with_phone')}"
                    )
                else:
                    observations.append(f"enrich_stepwise fail={phones}")

        for c in cards:
            c["_search_url"] = url
            if selectors:
                c["_selectors"] = {
                    "name_css": selectors.get("name_css"),
                    "phone_css": selectors.get("phone_css"),
                }

        # When phone was requested, demand at least one number so runs never
        # "succeed" with an all-null phone column.
        quality = self._validate_batch(
            cards,
            require_phone=require_phone,
            fields=fields,
        )
        with_phone = quality["with_phone"]
        observations.append(
            f"quality meaningful={quality['meaningful']} "
            f"with_phone={with_phone} ok={quality['ok']}"
        )

        if want_phone and quality["meaningful"] > 0 and with_phone == 0:
            observations.append("FAIL: phone field requested but 0 phones after enrich")
            return {
                "ok": False,
                "error": "phone enrichment produced 0 numbers — place panels had no phone",
                "cards": quality["cards"],
                "url": url,
                "observations": observations,
                "abort": True,
                "selectors": selectors,
                "quality": quality,
            }

        if not quality["ok"]:
            return {
                "ok": False,
                "error": quality.get("reason") or "extraction quality failed",
                "cards": quality["cards"],
                "url": url,
                "observations": observations,
                "abort": True,
                "selectors": selectors,
                "quality": quality,
            }

        return {
            "ok": True,
            "url": url,
            "cards": quality["cards"],
            "count": quality["meaningful"],
            "with_phone": with_phone,
            "observations": observations,
            "selectors": selectors,
            "quality": quality,
            "abort": False,
        }

    # ── backup pin URLs ───────────────────────────────────────────────

    @staticmethod
    def _has_state_and_area(decision: Any, pin_result: Dict[str, Any]) -> bool:
        """Backup pin searches only when state + area (city/district) exist on the goal."""
        state = (getattr(decision, "state", "") or "").strip()
        city = (getattr(decision, "city", "") or "").strip()
        districts = [d for d in (getattr(decision, "districts", None) or []) if d]
        if not city:
            city = ((pin_result or {}).get("city") or "").strip()
        return bool(state) and bool(city or districts)

    def _backup_pin_urls(
        self,
        decision: Any,
        pin_result: Dict[str, Any],
        query: str,
    ) -> List[str]:
        """Backup Maps queries: ``{pincode} {nature of business}`` when state+area exist."""
        if not self._has_state_and_area(decision, pin_result):
            return []
        sample_n = max(1, int(getattr(decision, "pin_sample", 5) or 5))
        out: List[str] = []
        seen = set()
        for row in (pin_result.get("rows") or [])[:sample_n]:
            pc = str(row.get("pincode") or "").strip()
            if not pc:
                continue
            q = f"{pc} {query}".strip()
            url = f"https://www.google.com/maps/search/{quote_plus(q)}"
            if url in seen:
                continue
            seen.add(url)
            out.append(url)
        return out

    # ── pipeline ──────────────────────────────────────────────────────

    def execute(
        self,
        decision: Any,
        pin_result: Dict[str, Any],
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        urls = list(getattr(decision, "search_urls", None) or [])
        query = getattr(decision, "query", "business")
        fields = list(getattr(decision, "fields", None) or [])
        require_phone = "phone" in fields
        goal = getattr(decision, "goal", "") or query

        backup_urls = self._backup_pin_urls(decision, pin_result, query)
        for url in backup_urls:
            if url not in urls:
                urls.append(url)

        script_plan = [
            self.SCRIPT_CONSENT,
            self.SCRIPT_WAIT,
            self.SCRIPT_INSPECT,
            self.SCRIPT_SCROLL,
            self.SCRIPT_PHONES,
        ]

        if dry_run:
            note = (
                "dry_run: planned script chain only — "
                + " → ".join(s.split("/")[-1] for s in script_plan)
                + " | quality gate: abort if name/phone selectors fail or cards not meaningful"
            )
            if backup_urls:
                note += (
                    f" | backup={len(backup_urls)}× '{{pincode}} {{business}}' "
                    "(state+area matched)"
                )
            else:
                note += " | backup=skipped (need state + area for pincode queries)"
            return {
                "ok": True,
                "dry_run": True,
                "planned_urls": urls,
                "backup_urls": backup_urls,
                "scripts": script_plan,
                "cards": [],
                "note": note,
            }

        if not self.fetcher:
            return {"ok": False, "error": "no page_fetcher", "cards": [], "planned_urls": urls}

        if not self.fetcher.is_connected():
            port = self.fetcher.find_available_port()
            if port:
                self.fetcher.connect(port)
        if not self.fetcher.is_connected():
            return {
                "ok": False,
                "error": "Chrome CDP not connected — start launch-chrome.py",
                "cards": [],
                "planned_urls": urls,
                "scripts": script_plan,
                "stopped": True,
                "stop_reason": "no CDP",
            }

        if self.har:
            try:
                self.har.start_capture(self.fetcher.port)
            except Exception:
                pass

        all_cards: List[Dict[str, Any]] = []
        seen = set()
        observations: List[str] = []
        live_urls = urls[: max(1, int(getattr(decision, "pin_sample", 5)) + 2)]
        consecutive_fails = 0
        consecutive_saturated = 0
        caution_issued = False
        prev_batch_keys: set = set()
        stopped = False
        stop_reason = ""
        extract_path = ""

        self._progress(
            label=query[:48] or "maps",
            step=0,
            total=len(live_urls),
            phase="maps: start",
            cards=0,
            phones=0,
            caution="",
            novelty=None,
            overlap=None,
        )

        for i, url in enumerate(live_urls):
            if stopped:
                break
            self._progress(
                label=query[:48] or "maps",
                step=i,
                total=len(live_urls),
                phase=f"scrape {i + 1}/{len(live_urls)}",
                cards=len(all_cards),
                phones=sum(1 for c in all_cards if c.get("phone")),
            )
            result = self.scrape_url(
                url,
                enrich_phones=True,
                max_places=int(getattr(decision, "max_live_pins", 25) or 25),
                require_phone=require_phone,
                fields=fields,
            )
            observations.extend(result.get("observations") or [])

            if not result.get("ok"):
                consecutive_fails += 1
                observations.append(
                    f"FAIL {url}: {result.get('error')} "
                    f"(consecutive_fails={consecutive_fails})"
                )
                # First URL must work — otherwise stop immediately (don't burn pins).
                # Mid-run abort with existing cards → caution & stop (keep partial).
                hard_fail = i == 0 or consecutive_fails >= self.MAX_CONSECUTIVE_FAILS
                soft_abort = bool(result.get("abort")) and bool(all_cards)
                if hard_fail or (result.get("abort") and not all_cards):
                    stopped = True
                    stop_reason = (
                        f"stopped: extraction failed — {result.get('error')}"
                        if i == 0 or result.get("abort")
                        else f"stopped: {consecutive_fails} consecutive empty/failed URLs"
                    )
                    observations.append(stop_reason)
                    break
                if soft_abort:
                    caution = (
                        f"script/abort on URL {i + 1} with {len(all_cards)} cards kept — "
                        f"{result.get('error')}"
                    )
                    observations.append(f"caution: {caution}")
                    self._progress(
                        label=query[:48] or "maps",
                        step=i + 1,
                        total=len(live_urls),
                        phase="caution",
                        cards=len(all_cards),
                        phones=sum(1 for c in all_cards if c.get("phone")),
                        caution=caution,
                    )
                    stopped = True
                    stop_reason = f"stopped (caution): {caution}"
                    observations.append(stop_reason)
                    break
                continue

            consecutive_fails = 0
            batch = result.get("cards") or []
            batch_keys = {self.card_key(c) for c in batch}
            novelty = self.novelty_rate(batch_keys, seen)
            overlap = 1.0 - novelty
            jaccard_prev = self.jaccard(batch_keys, prev_batch_keys) if prev_batch_keys else 0.0

            new_n = 0
            for card in batch:
                key = self.card_key(card)
                if key in seen:
                    continue
                seen.add(key)
                all_cards.append(card)
                new_n += 1

            observations.append(
                f"ok {url} meaningful={result.get('count')} phones={result.get('with_phone')} "
                f"new={new_n} novelty={novelty:.2f} overlap={overlap:.2f} "
                f"jaccard_prev={jaccard_prev:.2f}"
            )

            # Persist incrementally so partial success is never lost
            extract_path = self._write_extract(
                goal=goal,
                query=query,
                cards=all_cards,
                selectors=result.get("selectors") or self.last_selectors,
                observations=observations,
                stopped=False,
                stop_reason="",
                meta={
                    "last_url": url,
                    "urls_done": i + 1,
                    "urls_planned": len(live_urls),
                    "novelty": round(novelty, 4),
                    "overlap": round(overlap, 4),
                    "jaccard_prev": round(jaccard_prev, 4),
                    "new": new_n,
                },
            )
            observations.append(f"wrote {extract_path} ({len(all_cards)} rows)")

            # If first URL yielded nothing meaningful somehow, stop
            if i == 0 and len(all_cards) < self.MIN_MEANINGFUL_FIRST:
                stopped = True
                stop_reason = "stopped: first URL produced no meaningful data"
                observations.append(stop_reason)
                break

            # ── same-results / JEV diversity gate ──────────────────────
            saturated = (
                (i > 0 and novelty <= self.SATURATION_NOVELTY_FLOOR)
                or (i > 0 and jaccard_prev >= self.SATURATION_JACCARD_STOP)
                or (i > 0 and new_n == 0 and bool(batch_keys))
            )
            caution_hit = (
                i > 0
                and not saturated
                and novelty <= self.SATURATION_CAUTION_FLOOR
            )

            if saturated:
                consecutive_saturated += 1
            else:
                consecutive_saturated = 0

            caution_msg = ""
            if saturated:
                caution_msg = (
                    f"same results: novelty={novelty:.0%} overlap={overlap:.0%} "
                    f"jaccard_prev={jaccard_prev:.0%} ({consecutive_saturated}/"
                    f"{self.MAX_SATURATED_URLS})"
                )
            elif caution_hit and not caution_issued:
                caution_issued = True
                caution_msg = (
                    f"low novelty {novelty:.0%} — proceeding with caution"
                )
                observations.append(f"caution: {caution_msg}")

            self._progress(
                label=query[:48] or "maps",
                step=i + 1,
                total=len(live_urls),
                phase="enrich/write" if new_n else "saturated",
                cards=len(all_cards),
                phones=sum(1 for c in all_cards if c.get("phone")),
                caution=caution_msg,
                novelty=round(novelty, 4),
                overlap=round(overlap, 4),
            )

            if consecutive_saturated >= self.MAX_SATURATED_URLS:
                stopped = True
                stop_reason = (
                    f"stopped: saturation — same results for "
                    f"{consecutive_saturated} URLs "
                    f"(novelty≤{self.SATURATION_NOVELTY_FLOOR:.0%})"
                )
                observations.append(stop_reason)
                break

            # Identical fingerprint to previous batch → stop immediately
            if i > 0 and batch_keys and batch_keys == prev_batch_keys:
                stopped = True
                stop_reason = "stopped: identical JEV fingerprint vs previous URL"
                observations.append(stop_reason)
                break

            prev_batch_keys = batch_keys

        meaningful = self.filter_meaningful(all_cards, require_phone=False)
        if require_phone:
            # Prefer phone rows but keep maps_url-backed names if enrich partially worked
            with_phone = self.filter_meaningful(meaningful, require_phone=True)
            if with_phone:
                meaningful = with_phone

        if not meaningful and not stop_reason:
            stopped = True
            stop_reason = "stopped: run produced no meaningful rows"

        if meaningful or stopped:
            extract_path = self._write_extract(
                goal=goal,
                query=query,
                cards=meaningful,
                selectors=self.last_selectors,
                observations=observations,
                stopped=stopped,
                stop_reason=stop_reason,
                meta={
                    "planned_urls": live_urls,
                    "backup_urls": backup_urls,
                    "require_phone": require_phone,
                },
            )

        self.stop_reason = stop_reason
        ok = bool(meaningful) and not (stopped and not meaningful)
        phone_count = sum(1 for c in meaningful if c.get("phone"))

        self._progress(
            label=query[:48] or "maps",
            step=len(live_urls) if not stopped else max(1, sum(1 for _ in observations if _.startswith("ok "))),
            total=len(live_urls),
            phase="done" if ok and not stopped else ("stopped" if stopped else "done"),
            cards=len(meaningful),
            phones=phone_count,
            caution=stop_reason if stopped else "",
        )

        return {
            "ok": ok,
            "dry_run": False,
            "planned_urls": urls,
            "backup_urls": backup_urls,
            "scripts": script_plan,
            "cards": meaningful,
            "phone_count": phone_count,
            "observations": observations,
            "selectors": self.last_selectors,
            "stopped": stopped,
            "stop_reason": stop_reason or None,
            "extract_path": extract_path,
        }
