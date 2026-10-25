"""Decision-building skill — plan geo/Maps scrapes without an LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

from .pincodes import STATE_ALIASES


# Business / place query hints (ordered longer phrases first)
QUERY_PATTERNS = [
    (r"\bhedge\s*funds?\b", "hedge funds"),
    (r"\bventure\s*capitals?\b", "venture capital"),
    (r"\bprivate\s*equitys?\b", "private equity"),
    (r"\bjeweller(?:y|ies|s)?\b", "jewellers"),
    (r"\bjeweler(?:y|ies|s)?\b", "jewellers"),
    # longer phrases first so "pharmacy college" ≠ bare "pharmacy"
    (r"\bpharmacy\s+colleges?\b", "pharmacy college"),
    (r"\bpharmac(?:y|ies)\s+colleges?\b", "pharmacy college"),
    (r"\bengineering\s+colleges?\b", "engineering college"),
    (r"\bmedical\s+colleges?\b", "medical college"),
    (r"\bcolleges?\b", "college"),
    (r"\bpharmac(?:y|ies)\b", "pharmacy"),
    (r"\bchemists?\b", "chemist"),
    (r"\brestaurants?\b", "restaurant"),
    (r"\bhospitals?\b", "hospital"),
    (r"\bstartups?\b", "startup"),
    (r"\bhotels?\b", "hotel"),
    (r"\bschools?\b", "school"),
    (r"\bcafes?\b", "cafe"),
    # generic local-business listings → Maps (keep after specifics)
    (r"\bautomation\s+compan(?:y|ies)\b", "automation companies"),
    (r"\bcompan(?:y|ies)\b", "companies"),
    (r"\bbusiness(?:es)?\b", "businesses"),
    (r"\bfirms?\b", "firms"),
    (r"\bshops?\b", "shops"),
    (r"\bstores?\b", "stores"),
]

FIELD_HINTS = {
    "phone": ("phone", "mobile", "contact number", "telephone", "call", "number"),
    "email": ("email", "e-mail", "mail id"),
    "address": ("address", "location", "where"),
    "website": ("website", "site", "url"),
    "rating": ("rating", "review"),
}

# city → (state, district aliases for CSV)
CITY_META: Dict[str, Tuple[str, List[str]]] = {
    "hinjewadi": ("Maharashtra", ["Pune"]),
    "hinjawadi": ("Maharashtra", ["Pune"]),
    "pune": ("Maharashtra", ["Pune"]),
    "mumbai": ("Maharashtra", ["Mumbai", "Mumbai Suburban", "Thane"]),
    "ahmedabad": ("Gujarat", ["Ahmedabad"]),
    "surat": ("Gujarat", ["Surat"]),
    "vadodara": ("Gujarat", ["Vadodara"]),
    "rajkot": ("Gujarat", ["Rajkot"]),
    "gandhinagar": ("Gujarat", ["Gandhinagar"]),
    "bangalore": ("Karnataka", ["Bangalore", "Bengaluru Urban", "Bengaluru"]),
    "bengaluru": ("Karnataka", ["Bangalore", "Bengaluru Urban", "Bengaluru"]),
    "hyderabad": ("Telangana", ["Hyderabad"]),
    "delhi": ("Delhi", ["New Delhi", "Central Delhi", "South Delhi", "North Delhi"]),
}

GEO_CITY_HINTS = tuple(CITY_META.keys())

# Natural-language schedule → 5-field cron
CRON_PRESETS: Dict[str, str] = {
    "every minute": "* * * * *",
    "hourly": "0 * * * *",
    "every hour": "0 * * * *",
    "daily": "0 9 * * *",
    "every day": "0 9 * * *",
    "every morning": "0 9 * * *",
    "every night": "0 21 * * *",
    "weekly": "0 9 * * 1",
    "every week": "0 9 * * 1",
    "weekdays": "0 9 * * 1-5",
}

FILLER_RE = re.compile(
    r"\b("
    r"go\s+to|open|navigate|browse|scrape|scrap|fetch|find|get|give|gimme|we|me|my|"
    r"please|the|a|an|of|for|from|all|and|with|using|"
    r"google\s+maps|google|maps|"
    r"phone|phones|number|numbers|contact|contacts|email|address|"
    r"live|dry"
    r")\b",
    re.I,
)


@dataclass
class ScrapeDecision:
    """Structured plan produced by DecisionBuilderSkill."""

    goal: str
    query: str
    state: str = ""
    city: str = ""
    districts: List[str] = field(default_factory=list)
    fields: List[str] = field(default_factory=list)
    strategy: str = "maps_pincode_coverage"
    dry_run: bool = True
    pin_sample: int = 5
    max_live_pins: int = 25
    search_urls: List[str] = field(default_factory=list)
    steps: List[Dict[str, str]] = field(default_factory=list)
    rationale: str = ""
    suggested_cron: str = ""
    cron_label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def as_plan_tasks(self) -> List[Dict[str, str]]:
        tasks = [
            {
                "name": "decision",
                "goal": self.rationale or f"Plan: scrape {self.query} in {self.state or self.city}",
            },
            {
                "name": "pincodes",
                "goal": (
                    f"Load pincode CSV for {self.state or self.city or 'region'} "
                    f"(sample={self.pin_sample if self.dry_run else self.max_live_pins})"
                ),
            },
        ]
        if self.suggested_cron:
            tasks.append({
                "name": "cron",
                "goal": f"Suggested schedule: {self.cron_label or self.suggested_cron} → {self.suggested_cron}",
            })
        for i, url in enumerate(self.search_urls[:8]):
            tasks.append({
                "name": f"maps_{i}",
                "goal": f"Maps search #{i + 1}",
                "hint_url": url,
            })
        return tasks


class DecisionBuilderSkill:
    """
    Parse a natural-language scrape goal into an executable plan.
    Used instead of LLM for Maps / phone / geo intents.
    """

    name = "decision_builder"

    def can_handle(self, goal: str) -> bool:
        """
        Route local business / contact / Maps goals into the skills pipeline.
        Fetching business details (lists, companies, phones) in a place → Google Maps.
        """
        low = (goal or "").lower()
        contact = any(k in low for k in ("phone", "number", "contact", "email", "address"))
        mapsish = any(k in low for k in ("maps", "scrape", "scrap", "google maps", "pincode"))
        biz = any(re.search(p, low) for p, _ in QUERY_PATTERNS)
        listing = bool(
            re.search(
                r"\b(list|lists|listing|directory|compan(?:y|ies)|business(?:es)?|"
                r"shops?|stores?|firms?)\b",
                low,
            )
        )
        geo = (
            any(a in low for a in STATE_ALIASES)
            or any(c in low for c in GEO_CITY_HINTS)
            or bool(re.search(r"\bin\s+[a-z]{3,}", low))
        )
        # Business details / directories in a place always prefer Maps skills
        return (
            (contact and (biz or geo or listing))
            or (mapsish and (biz or geo or listing))
            or (biz and geo)
            or (listing and geo)
        )

    def build(self, goal: str, dry_run: bool = True) -> ScrapeDecision:
        low = (goal or "").lower()
        query = self._extract_query(low)
        state = self._extract_state(low)
        city = self._extract_city(low)
        districts: List[str] = []

        if city:
            meta = CITY_META.get(city.lower())
            if meta:
                city_state, dists = meta
                if not state:
                    state = city_state
                districts = list(dists)

        fields = self._extract_fields(low)
        if not fields:
            fields = ["name", "phone", "address"]

        cron_label, suggested_cron = self._extract_cron(low)

        pin_sample = 5 if dry_run else 25
        search_urls: List[str] = []
        where = city or state or "India"
        search_urls.append(
            f"https://www.google.com/maps/search/{quote_plus(f'{query} in {where}')}"
        )

        if city and state:
            search_urls.append(
                f"https://www.google.com/maps/search/{quote_plus(f'{query} in {city} {state}')}"
            )
        elif state and state.lower() == "gujarat":
            for dist in ("Ahmedabad", "Surat", "Vadodara", "Rajkot", "Gandhinagar"):
                search_urls.append(
                    f"https://www.google.com/maps/search/{quote_plus(f'{query} in {dist} Gujarat')}"
                )
                if dry_run and len(search_urls) >= 3:
                    break

        # de-dupe preserve order
        seen = set()
        uniq = []
        for u in search_urls:
            if u not in seen:
                seen.add(u)
                uniq.append(u)
        search_urls = uniq

        steps = [
            {"skill": "decision_builder", "action": "plan", "detail": f"query={query!r} state={state} city={city}"},
            {"skill": "pincodes", "action": "load_csv", "detail": f"filter state={state or '(none)'} districts={districts}"},
            {
                "skill": "maps_geo",
                "action": "dry_plan" if dry_run else "scrape",
                "detail": (
                    f"{len(search_urls)} city/state URLs; fields={fields}; "
                    "inspect→discover CSS/XPath→scroll; "
                    "abort if not extractable; "
                    "backup={{pincode}} {{business}} when state+area exist"
                ),
            },
        ]
        if suggested_cron:
            steps.append({
                "skill": "cron",
                "action": "suggest",
                "detail": f"{cron_label} → {suggested_cron}",
            })
        steps.append({"skill": "decision_builder", "action": "finish", "detail": "aggregate phones/cards"})

        rationale = (
            f"Skill plan (no LLM): extract {', '.join(fields)} for "
            f"'{query}' across {where}"
            + (f" [{state} / {', '.join(districts)}]" if districts else "")
            + " using city/state Maps search"
            + (
                " + backup '{pincode} {business}' when state+area match CSV"
                if (state and (city or districts))
                else " (no pin backup — need state and area)"
            )
            + (" [DRY — plan + pin sample only]" if dry_run else " [LIVE CDP]")
            + (f" · cron hint: {cron_label} ({suggested_cron})" if suggested_cron else "")
        )

        return ScrapeDecision(
            goal=goal,
            query=query,
            state=state,
            city=city,
            districts=districts,
            fields=fields,
            strategy="maps_pincode_coverage",
            dry_run=dry_run,
            pin_sample=pin_sample,
            max_live_pins=25,
            search_urls=search_urls,
            steps=steps,
            rationale=rationale,
            suggested_cron=suggested_cron,
            cron_label=cron_label,
        )

    def _extract_query(self, low: str) -> str:
        for pat, label in QUERY_PATTERNS:
            if re.search(pat, low):
                return label

        # "… of <thing> in <place>"
        m = re.search(r"\b(?:of|for)\s+(.+?)\s+in\s+", low)
        if m:
            chunk = FILLER_RE.sub(" ", m.group(1))
            chunk = re.sub(r"\s+", " ", chunk).strip(" .,-")
            if chunk and chunk not in ("business",):
                return chunk[:60]

        cleaned = FILLER_RE.sub(" ", low)
        for tok in list(STATE_ALIASES) + list(GEO_CITY_HINTS):
            cleaned = re.sub(rf"\b{re.escape(tok)}\b", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-")
        return cleaned[:60] or "business"

    def _extract_state(self, low: str) -> str:
        for alias in sorted(STATE_ALIASES.keys(), key=len, reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", low):
                return STATE_ALIASES[alias]
        return ""

    def _extract_city(self, low: str) -> str:
        for c in sorted(GEO_CITY_HINTS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(c)}\b", low):
                return c.title() if c not in ("hinjewadi", "hinjawadi") else "Hinjewadi"
        return ""

    def _extract_fields(self, low: str) -> List[str]:
        fields: List[str] = []
        for fname, keys in FIELD_HINTS.items():
            if any(k in low for k in keys):
                fields.append(fname)
        if fields and "name" not in fields:
            fields.insert(0, "name")
        return fields

    def _extract_cron(self, low: str) -> Tuple[str, str]:
        # Explicit 5-field cron in goal
        m = re.search(r"cron\s*[:=]?\s*([0-9*/, -]{5,40})", low)
        if m:
            expr = re.sub(r"\s+", " ", m.group(1).strip())
            if len(expr.split()) == 5:
                return ("custom", expr)
        for label, expr in sorted(CRON_PRESETS.items(), key=lambda x: -len(x[0])):
            if label in low:
                return (label, expr)
        if "schedule" in low or "recurring" in low or "cron" in low:
            return ("daily", CRON_PRESETS["daily"])
        return ("", "")
