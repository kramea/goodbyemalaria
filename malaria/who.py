"""Live country-level malaria figures from the WHO Global Health Observatory.

The GHO OData API is free and needs no key, but it is COUNTRY-LEVEL and ANNUAL —
it gives the latest estimated incidence and case burden for Mozambique / Malawi,
which we cite as "latest WHO data". The district-level "right now / outbreak"
signal comes from the curated current_status layer in regions.json, not from here.

Stdlib only (urllib); degrades to "" when offline so the agent simply omits it.
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from . import config
from .config import ROOT

_BASE = "https://ghoapi.azureedge.net/api"
_TIMEOUT = config.FETCH_TIMEOUT
_ISO = {"Mozambique": "MOZ", "Malawi": "MWI"}

# Persisted cache: WHO national figures change annually, so fetch once and reuse
# across restarts (knowledge/who_cache.json). No live call once populated.
_CACHE_FILE = ROOT / "knowledge" / "who_cache.json"
_cache: Optional[dict] = None


def _load_cache() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            _cache = {}
    return _cache


def _save_cache() -> None:
    try:
        _CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _latest(indicator: str, iso: str) -> Optional[dict]:
    qs = urllib.parse.urlencode({"$filter": f"SpatialDim eq '{iso}'"})
    url = f"{_BASE}/{indicator}?{qs}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MalarIA/1.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        rows = [v for v in data.get("value", []) if v.get("TimeDim")]
        if not rows:
            return None
        rows.sort(key=lambda v: int(v["TimeDim"]))
        return rows[-1]
    except Exception:
        return None


def country_summary(country: str, refresh: bool = False) -> str:
    """Latest WHO GHO national figure for the country, from disk cache.

    Fetches live only if the country isn't cached yet (or refresh=True), then
    persists it. After the first run there is NO network call.
    """
    iso = _ISO.get(country)
    if not iso:
        return ""
    cache = _load_cache()
    if country in cache and not refresh:
        return cache[country]

    inc = _latest("MALARIA_EST_INCIDENCE", iso)
    cases = _latest("MALARIA_EST_CASES", iso)
    parts = []
    year = None
    if inc and inc.get("NumericValue") is not None:
        year = inc.get("TimeDim")
        parts.append(f"estimated incidence {float(inc['NumericValue']):.0f} per 1,000 at risk")
    if cases and cases.get("NumericValue") is not None:
        year = cases.get("TimeDim") or year
        parts.append(f"~{float(cases['NumericValue'])/1e6:.1f}M estimated cases/yr")

    summary = ""
    if parts:
        summary = (f"WHO (GHO, latest {year}) — {country} national: " + "; ".join(parts) +
                   ". National annual baseline; see current_status for the district situation now.")

    # Only persist a successful fetch, so a transient network failure doesn't cache "".
    if summary:
        cache[country] = summary
        _save_cache()
    return summary
