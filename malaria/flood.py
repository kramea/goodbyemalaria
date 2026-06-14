"""Live river-discharge flood signal via the Open-Meteo Flood API (GloFAS-backed).

Free, no key. Raw discharge (m³/s) isn't interpretable on its own, so we pull ~30
days of history alongside the forecast and report the LEVEL relative to that recent
baseline (elevated / above-normal / normal) plus the 7-day TREND (rising / receding).
This is a flood-RISK signal, not flood-extent imagery (no free real-time extent feed).

Stdlib only; returns "" when offline so callers simply omit it.
"""

import urllib.parse
import urllib.request
import json
from statistics import median
from typing import Optional

from . import config

_ENDPOINT = "https://flood-api.open-meteo.com/v1/flood"
_TIMEOUT = config.FETCH_TIMEOUT
_cache: dict = {}


def _fetch(lat: float, lon: float) -> Optional[dict]:
    key = (round(lat, 2), round(lon, 2))
    if key in _cache:
        return _cache[key]
    params = {
        "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
        "daily": "river_discharge", "past_days": 31, "forecast_days": 7,
    }
    url = f"{_ENDPOINT}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MalarIA/1.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _cache[key] = data
        return data
    except Exception:
        return None


def discharge_summary(lat: float, lon: float) -> str:
    """Relative flood level + 7-day trend for the nearest river reach, or ""."""
    data = _fetch(lat, lon)
    if not data:
        return ""
    dd = data.get("daily", {})
    times = dd.get("time", [])
    series = [v for v in dd.get("river_discharge", []) if v is not None]
    if len(series) < 10:
        return ""

    # With past_days=31 + forecast_days=7, "now" is ~31 days in.
    now_i = min(31, len(series) - 7)
    current = series[now_i]
    past = series[:now_i] or series[:1]
    base = median(past)
    week_ahead = series[-1]

    if base <= 0:
        level = "normal"
    elif current >= 1.5 * base:
        level = "ELEVATED — well above the 30-day norm"
    elif current >= 1.1 * base:
        level = "above normal"
    else:
        level = "normal / receding"

    if week_ahead >= current * 1.15:
        trend = "RISING over the next week"
    elif week_ahead <= current * 0.85:
        trend = "receding over the next week"
    else:
        trend = "roughly steady over the next week"

    return (
        "LIVE FLOOD SIGNAL (Open-Meteo / GloFAS river discharge):\n"
        f"- Nearest river reach: {current:.0f} m³/s now ({level}); {trend}.\n"
        "- Note: even as rivers recede, POOLED standing water left behind is the "
        "malaria risk — larvicide it. Rising discharge = worsening flood, prioritize "
        "people + drainage."
    )
