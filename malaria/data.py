"""Regional malaria knowledge base loader + formatting for prompt injection.

The full knowledge base is small enough to hand to the navigator in one block,
which lets the agent itself decide which region the message refers to and reason
across every signal simultaneously (incidence, rainfall, season, last
intervention, resistance) rather than us pre-filtering for it.
"""

import json
import math
from functools import lru_cache
from typing import Optional, Tuple

from .config import KNOWLEDGE_FILE


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def meta() -> dict:
    return _load()["_meta"]


def regions() -> dict:
    return _load()["regions"]


def format_region(key: str, r: dict) -> str:
    cs = r.get("current_status") or {}
    status_line = ""
    if cs:
        status_line = (
            f"- CURRENT STATUS [{cs.get('alert_level', 'unknown').upper()}] "
            f"(as of {cs.get('as_of', 'n/a')}): {cs.get('headline', '')} "
            f"Trend: {cs.get('trend', '')} (Source: {cs.get('source', 'n/a')})\n"
        )
    return (
        f"### {key.upper()}  (country: {r['country']}; default language: {r['language_default']})\n"
        f"- Also referred to as: {', '.join(r['names'])}\n"
        f"{status_line}"
        f"- Incidence trend: {r['incidence_trend']}\n"
        f"- Rainfall / flood status: {r['rainfall_flood_status']}\n"
        f"- Seasonal timing: {r['season']}\n"
        f"- Elevation / flood-proneness: {r.get('elevation_flood', 'n/a')}\n"
        f"- Last known intervention: {r['last_intervention']}\n"
        f"- Insecticide resistance profile: {r['resistance_profile']}\n"
        f"- Infrastructure / feasibility: {r['infrastructure']}\n"
        f"- Dominant vectors: {', '.join(r['vectors'])}\n"
    )


def region_block(key: str) -> str:
    """Curated data for ONE area only — the fast path for the conversational
    advisor once a region is known. Falls back to the full block if unknown."""
    r = regions().get(key)
    if not r:
        return knowledge_block()
    m = meta()
    return "\n".join([
        "DATA SIGNALS for the worker's area (curated reference).",
        f"As of: {m['as_of']}.",
        f"Seasonality note: {m['season_note']}",
        "",
        format_region(key, r),
    ])


def knowledge_block() -> str:
    """Full data-signal reference block for the navigator/adversarial prompts."""
    m = meta()
    out = [
        "DATA SIGNALS (sub-national reference — reason across these simultaneously).",
        f"As of: {m['as_of']}.",
        f"Sources: {'; '.join(m['sources'])}.",
        f"Seasonality note: {m['season_note']}",
        "",
    ]
    for key, r in regions().items():
        out.append(format_region(key, r))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Geo helpers (maps + location-pin matching)
# ---------------------------------------------------------------------------

def region_geo(key: str) -> Optional[dict]:
    r = regions().get(key)
    return r.get("geo") if r else None


def region_record(key: str) -> Optional[dict]:
    return regions().get(key)


def region_alert(key: str) -> str:
    """Current alert level for a region: 'outbreak' | 'elevated' | 'normal' | ''."""
    r = regions().get(key) or {}
    return (r.get("current_status") or {}).get("alert_level", "")


def match_region_by_text(text: str) -> Optional[str]:
    """Best-effort: find the region key whose name appears in free text.

    Used to attach the right map to an agent reply. Matches the longest name
    first so 'Machinga' wins over a short alias, and so on.
    """
    if not text:
        return None
    low = text.lower()
    candidates = []
    for key, r in regions().items():
        for name in r.get("names", []) + [key.replace("_", " ")]:
            n = name.lower()
            if n and n in low:
                candidates.append((len(n), key))
    if not candidates:
        return None
    candidates.sort(reverse=True)  # longest match wins
    return candidates[0][1]


_COUNTRY_HINTS = {
    "Mozambique": ("mozambique", "moçambique", "mocambique"),
    "Malawi": ("malawi", "lilongwe", "blantyre", "mzuzu", "mangochi", "kasungu", "salima"),
}


def match_country_by_text(text: str) -> Optional[str]:
    """Detect an explicit country (or well-known city) mention in free text."""
    low = (text or "").lower()
    for country, hints in _COUNTRY_HINTS.items():
        if any(h in low for h in hints):
            return country
    return None


def country_block(country: str) -> str:
    """Curated data for ALL zones in one country — the fast path for a
    country-level question (e.g. 'how is malaria in Malawi?')."""
    m = meta()
    out = [
        f"DATA SIGNALS for {country} (curated, country-level — these are the zones "
        f"tracked in {country}; reason across them and name them where useful).",
        f"As of: {m['as_of']}.",
        f"Seasonality note: {m['season_note']}",
        "",
    ]
    found = False
    for key, r in regions().items():
        if r.get("country") == country:
            out.append(format_region(key, r))
            found = True
    return "\n".join(out) if found else knowledge_block()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_region(lat: float, lon: float, max_km: float = 250.0) -> Optional[Tuple[str, float]]:
    """Return (region_key, distance_km) for the nearest region center, or None
    if every region is farther than max_km (likely outside the service area)."""
    best = None
    for key, r in regions().items():
        geo = r.get("geo") or {}
        center = geo.get("center")
        if not center:
            continue
        d = _haversine_km(lat, lon, center[0], center[1])
        if best is None or d < best[1]:
            best = (key, d)
    if best and best[1] <= max_km:
        return best
    return best  # still return nearest even if far, caller can warn
