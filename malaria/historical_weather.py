"""Historical + short-range rainfall context for malaria-vector breeding timing.

Combines the Open-Meteo *Archive* API (past ~90 days of daily rain/temp) with the
*Forecast* API (next 7 days) to answer "is a breeding window open?" / "when will
adult mosquitoes emerge?" / "which upcoming days are dry enough to spray?".

From recent rain we derive a coarse Anopheles development timeline: a peak rain day
seeds egg-laying, larvae peak ~7 days later, adults emerge ~12 days later — the
window in which IRS / larviciding has the most leverage.

Stdlib only (urllib). All network code is wrapped so it NEVER raises; on failure it
returns a graceful ok=False dict so the agent simply falls back to curated
seasonality. Results are disk-cached (knowledge/historical_weather_cache.json) and
honor config.HISTORICAL_TTL.
"""

import json
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config

_ARCHIVE_ENDPOINT = "https://archive-api.open-meteo.com/v1/archive"
_FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
_SOURCE = "Open-Meteo Archive + Forecast API"

# Persisted cache keyed by rounded "lat,lon"; entries hold {"ts", "result"} and are
# reused until older than config.HISTORICAL_TTL.
_CACHE_FILE = config.ROOT / "knowledge" / "historical_weather_cache.json"
_cache: dict | None = None


def _empty_result(error: str | None = None) -> dict:
    return {
        "ok": False,
        "summary": "",
        "data": {},
        "source": _SOURCE,
        "as_of": None,
        "error": error,
    }


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


def _get_json(endpoint: str, params: dict) -> dict | None:
    url = f"{endpoint}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MalarIA/1.0"})
        with urllib.request.urlopen(req, timeout=config.FETCH_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _round1(x: float) -> float:
    return round(float(x), 1)


def _add_days(iso: str, n: int) -> str | None:
    try:
        return (date.fromisoformat(iso) + timedelta(days=n)).isoformat()
    except Exception:
        return None


def historical(lat: float, lon: float) -> dict:
    """Past-90-day rainfall + 7-day outlook with a derived breeding timeline.

    Returns the dict contract below. ok=True if the ARCHIVE fetch succeeded (the
    forecast failing only drops spray_safe_days and adds a note). Never raises.

        {"ok", "summary", "data", "source", "as_of", "error"}
    """
    key = f"{round(lat, 2)},{round(lon, 2)}"
    cache = _load_cache()
    entry = cache.get(key)
    if entry and isinstance(entry, dict):
        ts = entry.get("ts", 0)
        if (time.time() - ts) < config.HISTORICAL_TTL and isinstance(entry.get("result"), dict):
            return entry["result"]

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    start = today - timedelta(days=90)

    archive = _get_json(
        _ARCHIVE_ENDPOINT,
        {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "start_date": start.isoformat(),
            "end_date": yesterday.isoformat(),
            "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
        },
    )

    daily = (archive or {}).get("daily") or {}
    times = daily.get("time") or []
    precip = daily.get("precipitation_sum") or []
    if not times or not precip:
        return _empty_result("archive fetch failed or returned no daily data")

    # Pair (date, mm) and keep chronological order; treat null mm as 0.
    pairs = []
    for i, iso in enumerate(times):
        mm = precip[i] if i < len(precip) else None
        pairs.append((iso, float(mm) if mm is not None else 0.0))

    last10 = pairs[-10:]
    last30 = pairs[-30:]

    rain_10d_mm = _round1(sum(mm for _, mm in last10))
    rain_30d_mm = _round1(sum(mm for _, mm in last30))
    # Proxy climatological normal for a 10-day window: expected total from the
    # 30-day daily mean. Coarse but transparent given only ~90 days of data.
    n30 = len(last30) or 1
    rain_10d_normal_mm = _round1((rain_30d_mm / n30) * 10)

    peak_iso, peak_mm = max(last30, key=lambda p: p[1]) if last30 else (None, 0.0)
    rain_peak_mm = _round1(peak_mm)
    rain_peak_date = peak_iso

    # --- Forecast (next 7 days): spray-safe days + breeding-window lookahead ---
    forecast = _get_json(
        _FORECAST_ENDPOINT,
        {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "daily": "precipitation_probability_max,precipitation_sum",
            "forecast_days": 7,
            "timezone": "auto",
        },
    )
    fdaily = (forecast or {}).get("daily") or {}
    ftimes = fdaily.get("time") or []
    fprob = fdaily.get("precipitation_probability_max") or []
    fprecip = fdaily.get("precipitation_sum") or []

    forecast_ok = bool(ftimes)
    forecast_7d_mm = 0.0
    spray_safe_days: list[str] = []
    open_in_days = 3  # default N if we never cross the 15mm threshold
    if forecast_ok:
        for i, iso in enumerate(ftimes):
            mm = fprecip[i] if i < len(fprecip) else None
            forecast_7d_mm += float(mm) if mm is not None else 0.0
            pp = fprob[i] if i < len(fprob) else None
            if pp is not None and float(pp) < 30:
                spray_safe_days.append(iso)
        # First forecast day index where cumulative rain crosses 15mm.
        cum = 0.0
        for i, iso in enumerate(ftimes):
            mm = fprecip[i] if i < len(fprecip) else None
            cum += float(mm) if mm is not None else 0.0
            if cum > 15:
                open_in_days = i + 1
                break
    forecast_7d_mm = _round1(forecast_7d_mm)

    # --- Breeding window status ---
    if rain_10d_mm > 25:
        breeding_window_status = "open"
    elif forecast_ok and forecast_7d_mm > 25:
        breeding_window_status = f"opening_in_{open_in_days}d"
    else:
        breeding_window_status = "closed"

    # --- Vector development timeline anchored on the peak rain day ---
    eggs_laid_date = rain_peak_date
    larvae_peak_date = _add_days(eggs_laid_date, 7) if eggs_laid_date else None
    adult_emerge_date = _add_days(eggs_laid_date, 12) if eggs_laid_date else None

    note = None if forecast_ok else "forecast fetch failed; spray_safe_days unavailable"

    data = {
        "rain_10d_mm": rain_10d_mm,
        "rain_30d_mm": rain_30d_mm,
        "rain_10d_normal_mm": rain_10d_normal_mm,
        "rain_peak_mm": rain_peak_mm,
        "rain_peak_date": rain_peak_date,
        "breeding_window_status": breeding_window_status,
        "eggs_laid_date": eggs_laid_date,
        "larvae_peak_date": larvae_peak_date,
        "adult_emerge_date": adult_emerge_date,
        "spray_safe_days": spray_safe_days,
        "forecast_7d_rain_mm": forecast_7d_mm,
        "note": note,
    }

    # --- Human-readable summary ---
    vs_normal = "above" if rain_10d_mm > rain_10d_normal_mm else (
        "below" if rain_10d_mm < rain_10d_normal_mm else "near")
    lines = [
        "HISTORICAL RAINFALL & BREEDING TIMELINE (Open-Meteo archive + forecast):",
        f"- Last 10 days: {rain_10d_mm} mm rain ({vs_normal} the ~{rain_10d_normal_mm} mm "
        f"10-day normal proxy); last 30 days: {rain_30d_mm} mm.",
        f"- Heaviest day in last 30: {rain_peak_mm} mm on {rain_peak_date}.",
        f"- Breeding window: {breeding_window_status}.",
    ]
    if eggs_laid_date:
        lines.append(
            f"- Vector timeline from peak rain ({eggs_laid_date}): larvae peak ~{larvae_peak_date}, "
            f"adults emerge ~{adult_emerge_date} (best IRS/larviciding leverage before then).")
    if forecast_ok:
        if spray_safe_days:
            lines.append(f"- Spray-safe days (next 7, <30% rain chance): {', '.join(spray_safe_days)}.")
        else:
            lines.append("- No spray-safe days in the next 7 (rain chance >=30% every day).")
    else:
        lines.append("- Forecast unavailable, so spray-safe days could not be computed.")
    summary = "\n".join(lines)

    result = {
        "ok": True,
        "summary": summary,
        "data": data,
        "source": _SOURCE,
        "as_of": yesterday.isoformat(),
        "error": note,
    }

    cache[key] = {"ts": time.time(), "result": result}
    _save_cache()
    return result


if __name__ == "__main__":
    for name, (la, lo) in {"Gaza": (-24.7, 33.2), "Zomba": (-15.35, 35.45)}.items():
        print(f"\n===== {name} ({la}, {lo}) =====")
        r = historical(la, lo)
        print("ok:", r["ok"], "| as_of:", r["as_of"], "| error:", r["error"])
        print(json.dumps(r["data"], ensure_ascii=False, indent=2))
        print(r["summary"])
