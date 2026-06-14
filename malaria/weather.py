"""Live rain forecast via Open-Meteo (free, no API key).

Used to answer field-worker timing questions like "can I spray tomorrow?" with
a real short-range precipitation outlook for their area. Uses only the standard
library (urllib) so there is no extra dependency, and degrades gracefully to an
empty string when offline so the agent simply falls back to curated seasonality.
"""

import json
import time
import urllib.parse
import urllib.request
from datetime import date
from typing import Optional

from . import config

_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT = config.FETCH_TIMEOUT  # single knob (MALARIA_FETCH_TIMEOUT) for all live fetchers

# Disk cache keyed by rounded "lat,lon,days"; entries hold {"ts", "data"} and are
# reused until older than config.FORECAST_TTL. Persisted so repeat spray-timing
# questions for an area answer instantly and survive restarts. Loaded once into
# the module global, then kept in sync on write.
_CACHE_FILE = config.ROOT / "knowledge" / "forecast_cache.json"
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
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _fetch(lat: float, lon: float, days: int = 4) -> Optional[dict]:
    key = f"{round(lat, 2)},{round(lon, 2)},{days}"
    cache = _load_cache()
    entry = cache.get(key)
    if isinstance(entry, dict):
        ts = entry.get("ts", 0)
        if (time.time() - ts) < config.FORECAST_TTL and isinstance(entry.get("data"), dict):
            return entry["data"]
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "daily": "precipitation_sum,precipitation_probability_max,temperature_2m_max",
        "forecast_days": days,
        "timezone": "auto",
    }
    url = f"{_ENDPOINT}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MalarIA/1.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        cache[key] = {"ts": time.time(), "data": data}
        _save_cache()
        return data
    except Exception:
        # Network slow/down (e.g. the 3s cap fired): a slightly stale forecast
        # beats none for spray timing, so serve the last cached one if we have it.
        if isinstance(entry, dict) and isinstance(entry.get("data"), dict):
            return entry["data"]
        return None


def _day_label(iso: str, today_iso: str) -> str:
    if iso == today_iso:
        return "Today"
    try:
        d0 = date.fromisoformat(today_iso)
        d1 = date.fromisoformat(iso)
        delta = (d1 - d0).days
    except Exception:
        return iso
    if delta == 1:
        return "Tomorrow"
    return date.fromisoformat(iso).strftime("%a %d %b")


def forecast_summary(lat: float, lon: float) -> str:
    """Compact, language-neutral rain outlook for prompt injection.

    Returns "" if the forecast can't be fetched (offline) so the caller just
    omits it. The agent translates / interprets these facts in its reply.
    """
    data = _fetch(lat, lon)
    if not data or "daily" not in data:
        return ""
    d = data["daily"]
    times = d.get("time", [])
    rain = d.get("precipitation_sum", [])
    prob = d.get("precipitation_probability_max", [])
    tmax = d.get("temperature_2m_max", [])
    if not times:
        return ""
    today_iso = times[0]
    lines = ["LIVE RAIN FORECAST (Open-Meteo, for spray-timing / rain questions):"]
    for i, iso in enumerate(times):
        mm = rain[i] if i < len(rain) else None
        pp = prob[i] if i < len(prob) else None
        tx = tmax[i] if i < len(tmax) else None
        label = _day_label(iso, today_iso)
        wet = "rain likely" if (pp is not None and pp >= 50) else (
            "some rain possible" if (pp is not None and pp >= 25) else "mostly dry")
        bits = []
        if mm is not None:
            bits.append(f"{mm:.0f} mm")
        if pp is not None:
            bits.append(f"{pp:.0f}% chance")
        if tx is not None:
            bits.append(f"max {tx:.0f}°C")
        lines.append(f"- {label} ({iso}): {wet} ({', '.join(bits)})")
    lines.append(
        "Use this for timing advice: spraying (IRS) and larviciding work best on "
        "dry days; fresh rain/standing water raises larval-source urgency.")
    return "\n".join(lines)
