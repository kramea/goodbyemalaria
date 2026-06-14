"""Live humanitarian health alerts from the ReliefWeb API (free, no API key).

ReliefWeb (run by UN OCHA) publishes situation reports, outbreak notices and
health bulletins. We pull the most recent Health-theme reports for a country so
the agent can surface "is there anything active right now?" context alongside
the curated district status and the annual WHO baseline.

Stdlib only (urllib); never raises out of the module — on any network/parse
failure it returns a graceful ok=False result so the caller just omits it.
Successful results are persisted to knowledge/reliefweb_cache.json so repeated
turns within the TTL window cost no network call.
"""

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import config

# v1 was decommissioned (HTTP 410); v2 is current. Both require an `appname`
# query param; v2 additionally requires a ReliefWeb-approved appname, so make it
# configurable (register one at https://apidoc.reliefweb.int/parameters#appname).
_ENDPOINT = os.getenv("MALARIA_RELIEFWEB_ENDPOINT", "https://api.reliefweb.int/v2/reports")
_APPNAME = os.getenv("MALARIA_RELIEFWEB_APPNAME", "malaria-ia")
_BODY_TRIM = 140  # chars of each report body kept in the one-line summary

# Persisted cache keyed by country: {"ts": epoch, "result": <result dict>}.
_CACHE_FILE = config.ROOT / "knowledge" / "reliefweb_cache.json"


def _load_cache() -> dict:
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _build_url(country: str) -> str:
    # Repeated keys (fields[include][], sort[]) require a list of tuples + doseq.
    params = [
        ("appname", _APPNAME),
        ("filter[conditions][0][field]", "country.name"),
        ("filter[conditions][0][value]", country),
        ("filter[conditions][1][field]", "theme.name"),
        ("filter[conditions][1][value]", "Health"),
        ("filter[operator]", "AND"),
        ("limit", "3"),
        ("sort[]", "date:desc"),
        ("fields[include][]", "title"),
        ("fields[include][]", "body"),
        ("fields[include][]", "date"),
    ]
    return f"{_ENDPOINT}?{urllib.parse.urlencode(params, doseq=True)}"


def _trim_body(body) -> str:
    if not body:
        return ""
    text = " ".join(str(body).split())
    if len(text) > _BODY_TRIM:
        text = text[:_BODY_TRIM].rstrip() + "…"
    return text


def _parse_date(fields: dict) -> str:
    # date can be a dict ({"created": ..., "original": ...}) or a plain string.
    raw = fields.get("date")
    iso = None
    if isinstance(raw, dict):
        iso = raw.get("created") or raw.get("original") or raw.get("changed")
    elif isinstance(raw, str):
        iso = raw
    if not iso:
        return ""
    # Keep just the YYYY-MM-DD prefix for the summary line.
    return str(iso)[:10]


def alerts(country: str) -> dict:
    """Most recent ReliefWeb Health-theme reports for a country.

    Returns the contract dict described in the module docstring. Serves a cached
    result without any network call when one was fetched within RELIEFWEB_TTL.
    Never raises: any failure yields ok=False with a short error string.
    """
    cache = _load_cache()
    entry = cache.get(country)
    if isinstance(entry, dict) and "result" in entry:
        ts = entry.get("ts", 0)
        try:
            fresh = (time.time() - float(ts)) < config.RELIEFWEB_TTL
        except Exception:
            fresh = False
        if fresh:
            return entry["result"]

    as_of = datetime.now(timezone.utc).isoformat()
    try:
        url = _build_url(country)
        req = urllib.request.Request(url, headers={"User-Agent": "MalarIA/1.0"})
        with urllib.request.urlopen(req, timeout=config.FETCH_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        rows = payload.get("data") or []
        alerts_list = []
        for row in rows:
            fields = row.get("fields") or {}
            title = (fields.get("title") or "").strip()
            body = _trim_body(fields.get("body"))
            d = _parse_date(fields)
            alerts_list.append({"title": title, "date": d, "body": body})

        if alerts_list:
            lines = []
            for a in alerts_list:
                prefix = f"{a['date']} — " if a["date"] else ""
                if a["body"]:
                    lines.append(f"{prefix}{a['title']}: {a['body']}")
                else:
                    lines.append(f"{prefix}{a['title']}")
            summary = "\n".join(lines)
        else:
            summary = "No active alerts in last 72h."

        result = {
            "ok": True,
            "summary": summary,
            "data": {"alerts": alerts_list},
            "source": "ReliefWeb API",
            "as_of": as_of,
            "error": None,
        }
        cache[country] = {"ts": time.time(), "result": result}
        _save_cache(cache)
        return result
    except Exception as exc:
        return {
            "ok": False,
            "summary": "No active alerts in last 72h.",
            "data": {"alerts": []},
            "source": "ReliefWeb API",
            "as_of": None,
            "error": f"{type(exc).__name__}: {exc}"[:200],
        }


if __name__ == "__main__":
    print(alerts("Mozambique"))
    print(alerts("Malawi"))
