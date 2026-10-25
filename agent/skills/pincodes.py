"""Pincode lookup skill — load / filter India PIN CSV (no LLM)."""

from __future__ import annotations

import csv
import os
import re
from collections import OrderedDict
from typing import Any, Dict, List, Optional

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DEFAULT_CSV = os.path.join(_REPO_ROOT, "data", "pincodes.csv")

DEFAULT_PINCODE_CSV = os.environ.get("PINCODE_CSV", _DEFAULT_CSV)

# Common misspellings / aliases → CSV State value
STATE_ALIASES = {
    "gujrat": "Gujarat",
    "gujarat": "Gujarat",
    "gj": "Gujarat",
    "maharashtra": "Maharashtra",
    "mh": "Maharashtra",
    "karnataka": "Karnataka",
    "ka": "Karnataka",
    "delhi": "Delhi",
    "nct of delhi": "Delhi",
    "rajasthan": "Rajasthan",
    "tamil nadu": "Tamil Nadu",
    "tamilnadu": "Tamil Nadu",
}


class PincodeSkill:
    """Import and filter pincode CSV for geo scrape coverage."""

    name = "pincodes"

    def __init__(self, csv_path: str = DEFAULT_PINCODE_CSV):
        self.csv_path = csv_path
        self._cache: Optional[OrderedDict[str, Dict[str, str]]] = None

    def load_all(self) -> "OrderedDict[str, Dict[str, str]]":
        if self._cache is not None:
            return self._cache
        path = self.csv_path
        if not os.path.isfile(path):
            raise FileNotFoundError(f"pincode CSV not found: {path}")

        pincodes: OrderedDict[str, Dict[str, str]] = OrderedDict()
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                with open(path, "r", encoding=encoding, newline="") as f:
                    reader = csv.DictReader(f)
                    if not reader.fieldnames:
                        continue
                    pincode_col = district_col = state_col = office_col = city_col = None
                    for col in reader.fieldnames:
                        cl = col.lower().strip()
                        if any(x in cl for x in ("pincode", "pin code", "postal", "postcode")) or cl == "pin":
                            pincode_col = col
                        elif "district" in cl:
                            district_col = col
                        elif "state" in cl:
                            state_col = col
                        elif "office" in cl or "postoffice" in cl.replace(" ", ""):
                            office_col = col
                        elif cl == "city":
                            city_col = col
                    if not pincode_col:
                        raise ValueError(f"No pincode column in {reader.fieldnames}")
                    for row in reader:
                        pc = re.sub(r"\D", "", str(row.get(pincode_col) or "").strip())
                        if not pc or len(pc) < 4 or pc in pincodes:
                            continue
                        pincodes[pc] = {
                            "pincode": pc,
                            "district": (row.get(district_col) or "").strip() if district_col else "",
                            "state": (row.get(state_col) or "").strip() if state_col else "",
                            "office": (row.get(office_col) or "").strip() if office_col else "",
                            "city": (row.get(city_col) or "").strip() if city_col else "",
                        }
                if pincodes:
                    self._cache = pincodes
                    return pincodes
            except Exception:
                continue
        raise ValueError(f"Could not load pincodes from {path}")

    @staticmethod
    def normalize_state(name: str) -> str:
        key = (name or "").strip().lower()
        if not key:
            return ""
        if key in STATE_ALIASES:
            return STATE_ALIASES[key]
        # Title-case fallback matching CSV
        return name.strip().title()

    def filter(
        self,
        state: str = "",
        districts: Optional[List[str]] = None,
        city: str = "",
        limit: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        all_pins = self.load_all()
        want_state = self.normalize_state(state).lower() if state else ""
        want_dists = {d.strip().lower() for d in (districts or []) if d and d.strip()}
        want_city = (city or "").strip().lower()
        out: List[Dict[str, str]] = []
        for info in all_pins.values():
            st = (info.get("state") or "").strip().lower()
            dist = (info.get("district") or "").strip().lower()
            cty = (info.get("city") or "").strip().lower()
            if want_state and st != want_state:
                continue
            if want_dists:
                # district match OR city column contains any alias
                if dist not in want_dists and not any(d in cty or d in dist for d in want_dists):
                    if want_city and want_city not in dist and want_city not in cty:
                        continue
                    if not want_city:
                        continue
            elif want_city and want_city not in dist and want_city not in cty:
                continue
            out.append(info)
            if limit and len(out) >= limit:
                break
        return out

    def districts_for_state(self, state: str) -> List[Dict[str, Any]]:
        rows = self.filter(state=state)
        counts: Dict[str, int] = {}
        for r in rows:
            d = r.get("district") or "Unknown"
            counts[d] = counts.get(d, 0) + 1
        return [
            {"name": name, "count": counts[name]}
            for name in sorted(counts, key=lambda n: (-counts[n], n))
        ]

    def load_for_decision(self, decision: Any) -> Dict[str, Any]:
        """Load pins matching a ScrapeDecision (supports dry sample limits)."""
        state = getattr(decision, "state", "") or ""
        districts = getattr(decision, "districts", None) or []
        city = getattr(decision, "city", "") or ""
        dry = bool(getattr(decision, "dry_run", False))
        sample_n = int(getattr(decision, "pin_sample", 5) or 5)

        total = len(self.load_all())
        if not state and not districts and not city:
            return {
                "ok": True,
                "csv": self.csv_path,
                "total": total,
                "filtered": 0,
                "rows": [],
                "sample_pins": [],
                "districts": [],
            }

        full = self.filter(
            state=state,
            districts=districts or None,
            city=city,
        )
        max_live = int(getattr(decision, "max_live_pins", 25) or 25)

        def _diverse(src: List[Dict[str, str]], n: int) -> List[Dict[str, str]]:
            seen_d: set = set()
            sample: List[Dict[str, str]] = []
            for row in src:
                d = row.get("district") or row.get("city") or ""
                if d in seen_d and len(sample) >= 1:
                    continue
                seen_d.add(d)
                sample.append(row)
                if len(sample) >= n:
                    break
            if len(sample) < n:
                for row in src:
                    if row not in sample:
                        sample.append(row)
                    if len(sample) >= n:
                        break
            return sample

        rows = _diverse(full, sample_n) if dry else full[:max_live]

        return {
            "ok": True,
            "csv": self.csv_path,
            "total": total,
            "filtered": len(full),
            "rows": rows,
            "sample_pins": [r["pincode"] for r in rows[:20]],
            "districts": self.districts_for_state(state) if state else [],
            "state": self.normalize_state(state),
            "city": city,
        }
