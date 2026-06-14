"""Live confirmed-malaria-case counts from a DHIS2 HMIS instance.

DHIS2 is the routine health-information backbone used by most national malaria
programs (Mozambique/Malawi included). This pulls the last three weeks of
confirmed malaria cases for an org unit from the DHIS2 Web API analytics endpoint
so the agent can cite a recent week-over-week trend ("cases up 30% on last
week") alongside the curated district status.

For the demo we hit the public play.dhis2.org instance (admin/district). Swap
config.DHIS2_BASE / DHIS2_USER / DHIS2_PASS for the national HMIS in production.

Stdlib only (urllib + base64). Every network path is wrapped so we NEVER raise:
on any failure we return the same contract dict with ok=False, so the caller can
degrade gracefully to curated data.
"""

import base64
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from . import config

_ENDPOINT = f"{config.DHIS2_BASE}/analytics.json"
_DX = "fbfJHSPpUQD"  # data element: confirmed malaria cases (demo instance)
_SOURCE = "DHIS2 HMIS (demo instance)"

# Persisted cache (knowledge/dhis2_cache.json): keyed by org_unit, honoring
# config.DHIS2_TTL so we don't re-hit the (slow) demo instance every turn.
_CACHE_FILE = config.ROOT / "knowledge" / "dhis2_cache.json"


def _result(ok: bool, summary: str, data: dict, as_of: Optional[str],
            error: Optional[str]) -> dict:
    return {
        "ok": ok,
        "summary": summary,
        "data": data,
        "source": _SOURCE,
        "as_of": as_of,
        "error": error,
    }


def _empty_data(org_unit: str) -> dict:
    return {"w0": None, "w1": None, "w2": None, "wow_pct": None, "org_unit": org_unit}


def _load_cache() -> dict:
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _fetch(org_unit: str) -> Optional[dict]:
    """Raw DHIS2 analytics JSON for the org unit, or None on any failure."""
    query = urllib.parse.urlencode(
        [
            ("dimension", f"dx:{_DX}"),
            ("dimension", "pe:LAST_3_WEEKS"),
            ("dimension", f"ou:{org_unit}"),
            ("displayProperty", "NAME"),
        ],
        doseq=True,
    )
    url = f"{_ENDPOINT}?{query}"
    token = base64.b64encode(
        f"{config.DHIS2_USER}:{config.DHIS2_PASS}".encode("utf-8")).decode("ascii")
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Basic {token}",
                "Accept": "application/json",
                "User-Agent": "MalarIA/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=config.FETCH_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _parse(payload: dict, org_unit: str) -> dict:
    """Turn a DHIS2 analytics response into the data dict (generically).

    Finds the period ("pe") and "value" header indices, sorts rows by ISO-week
    period descending, and assigns w0 (latest), w1, w2 from the value column.
    """
    data = _empty_data(org_unit)
    try:
        headers = payload.get("headers", []) or []
        rows = payload.get("rows", []) or []
        pe_idx = None
        val_idx = None
        for i, h in enumerate(headers):
            name = h.get("name")
            if name == "pe":
                pe_idx = i
            elif name == "value":
                val_idx = i
        if pe_idx is None or val_idx is None or not rows:
            return data

        # Collect (period, value) pairs, skipping anything we can't parse.
        pairs = []
        for row in rows:
            try:
                period = row[pe_idx]
                value = int(float(row[val_idx]))
            except Exception:
                continue
            pairs.append((period, value))
        if not pairs:
            return data

        # ISO week strings like "2026W24" sort lexicographically the same as
        # chronologically (year then zero-padded-ish week); sort descending.
        pairs.sort(key=lambda p: p[0], reverse=True)
        weeks = [v for _, v in pairs[:3]]
        labels = ["w0", "w1", "w2"]
        for label, value in zip(labels, weeks):
            data[label] = value
    except Exception:
        return _empty_data(org_unit)

    w0, w1 = data["w0"], data["w1"]
    if w0 is not None and w1 is not None and w1 > 0:
        data["wow_pct"] = round((w0 - w1) / w1 * 100, 1)
    return data


def _summarize(data: dict) -> str:
    w0, w1, w2 = data["w0"], data["w1"], data["w2"]
    if w0 is None and w1 is None and w2 is None:
        return "DHIS2 returned no case data for this unit."
    wow = data["wow_pct"]
    wow_str = f"{wow:+}%" if wow is not None else "n/a"
    return (f"Confirmed malaria cases — week-0: {w0}, week-1: {w1}, "
            f"week-2: {w2} (WoW {wow_str} )")


def cases(org_unit: str) -> dict:
    """Last-3-weeks confirmed malaria cases + WoW trend for a DHIS2 org unit.

    Disk-cached (knowledge/dhis2_cache.json, TTL config.DHIS2_TTL). Never raises:
    on any error returns the contract dict with ok=False and an error string.
    """
    now = time.time()

    # Serve a fresh cache hit without touching the network.
    cache = _load_cache()
    entry = cache.get(org_unit)
    if entry and isinstance(entry, dict):
        ts = entry.get("ts", 0)
        cached = entry.get("result")
        if isinstance(cached, dict) and (now - ts) < config.DHIS2_TTL:
            return cached

    payload = _fetch(org_unit)
    if payload is None:
        return _result(
            ok=False,
            summary="DHIS2 returned no case data for this unit.",
            data=_empty_data(org_unit),
            as_of=None,
            error="fetch failed (DHIS2 unreachable, slow, or auth error)",
        )

    data = _parse(payload, org_unit)
    ok = any(data[k] is not None for k in ("w0", "w1", "w2"))
    summary = _summarize(data)
    as_of = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)) if ok else None
    result = _result(ok=ok, summary=summary, data=data, as_of=as_of, error=None)

    # Only cache a successful parse, so a bad/empty response doesn't get pinned
    # for the whole TTL.
    if ok:
        cache[org_unit] = {"ts": now, "result": result}
        _save_cache(cache)
    return result


if __name__ == "__main__":
    for ou in ("O6uvpzGd5pu", "fdc6uOvgoji"):
        print(f"=== {ou} ===")
        print(json.dumps(cases(ou), ensure_ascii=False, indent=2))
