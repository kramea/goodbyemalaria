"""PMI (President's Malaria Initiative) FY2024 country malaria profiles.

These profiles (hosted by MESA) are PDF documents giving the operational picture
for a country: insecticide resistance status, recommended net type, IRS chemical,
SMC eligibility, supply-chain / stockout risk, and ITN/LLIN coverage. We download
the PDF once, parse the text heuristically, and cache the PARSED result to disk
(knowledge/pmi_cache_<country>.json) for a week — this is a startup / weekly
operation, NOT in the request path.

Stdlib urllib for the download; pdfminer.six for text extraction. Everything is
wrapped so a missing dependency or a network/parse failure degrades gracefully to
ok=False and NEVER raises out of the module.
"""

import io
import json
import re
import time
import urllib.request
from typing import Optional

from .config import PMI_TTL, ROOT

# pdfminer.six is an optional dependency: a missing install degrades to ok=False
# rather than breaking the import of this module.
try:
    from pdfminer.high_level import extract_text  # type: ignore

    _HAVE_PDFMINER = True
except ImportError:
    extract_text = None  # type: ignore
    _HAVE_PDFMINER = False

# Generous download timeout: this is a weekly-cached startup op, not request-path.
_DOWNLOAD_TIMEOUT = 30
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_SOURCE = "PMI FY2024 Malaria Profile"

_URLS = {
    "Mozambique": "https://mesamalaria.org/wp-content/uploads/2025/04/MOZAMBIQUE-Malaria-Profile-PMI-FY-2024.pdf",
    "Malawi": "https://mesamalaria.org/wp-content/uploads/2025/04/MALAWI-Malaria-Profile-PMI-FY-2024.pdf",
}

# Candidate product / chemical names searched for in the (lowercased) PDF text.
_NET_PRODUCTS = [
    "Interceptor G2",
    "PermaNet",
    "Royal Guard",
    "Olyset",
    "PBO",
    "dual-active",
    "chlorfenapyr",
]
_IRS_CHEMICALS = [
    "Actellic",
    "SumiShield",
    "Fludora",
    "pirimiphos-methyl",
    "clothianidin",
    "deltamethrin",
]


def _cache_file(country: str):
    return ROOT / "knowledge" / f"pmi_cache_{country.lower()}.json"


def _load_cached(country: str) -> Optional[dict]:
    """Return the cached parsed result if present and within PMI_TTL, else None."""
    try:
        path = _cache_file(country)
        blob = json.loads(path.read_text(encoding="utf-8"))
        ts = float(blob.get("ts", 0))
        if (time.time() - ts) <= PMI_TTL:
            return blob.get("result")
    except Exception:
        pass
    return None


def _save_cached(country: str, result: dict) -> None:
    try:
        path = _cache_file(country)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"ts": time.time(), "result": result}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _download_pdf(url: str) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
            return resp.read()
    except Exception:
        return None


def _extract(pdf_bytes: bytes) -> Optional[str]:
    if not _HAVE_PDFMINER:
        return None
    try:
        return extract_text(io.BytesIO(pdf_bytes)) or ""
    except Exception:
        return None


def _near(text: str, anchor: str, words: list, window: int = 200) -> bool:
    """True if any of `words` appears within `window` chars of `anchor` in text."""
    start = 0
    while True:
        idx = text.find(anchor, start)
        if idx == -1:
            return False
        seg = text[max(0, idx - window): idx + len(anchor) + window]
        if any(w in seg for w in words):
            return True
        start = idx + len(anchor)


def _parse(text: str) -> dict:
    """Heuristic parse of the (raw) PDF text into the data contract."""
    low = text.lower()

    # --- pyrethroid resistance ---
    pyrethroid_resistance = "unknown"
    if "pyrethroid resistance" in low:
        if _near(low, "pyrethroid resistance", ["confirmed", "high", "widespread"]):
            pyrethroid_resistance = "confirmed"
        elif _near(low, "pyrethroid resistance", ["suspected", "possible"]):
            pyrethroid_resistance = "suspected"
        elif "susceptib" in low:
            pyrethroid_resistance = "none"
    elif "susceptib" in low and "pyrethroid" in low:
        pyrethroid_resistance = "none"

    # --- recommended net type ---
    recommended_net_type = "unknown"
    for prod in _NET_PRODUCTS:
        if prod.lower() in low:
            recommended_net_type = prod
            break

    # --- IRS insecticide ---
    irs_insecticide = "unknown"
    for chem in _IRS_CHEMICALS:
        if chem.lower() in low:
            irs_insecticide = chem
            break

    # --- SMC eligibility ---
    smc_eligible: Optional[bool] = None
    has_smc = "seasonal malaria chemoprevention" in low or re.search(r"\bsmc\b", low)
    if has_smc:
        if ("not eligible" in low) or ("not recommended" in low):
            smc_eligible = False
        else:
            smc_eligible = True

    # --- supply chain risk ---
    supply_chain_risk = "unknown"
    supply_mentioned = (
        "supply chain" in low or "stockout" in low or "stock-out" in low
    )
    risk_words = ["risk", "challenge", "disruption"]
    if (
        ("stockout" in low or "stock-out" in low or "supply chain" in low)
        and any(w in low for w in risk_words)
    ):
        supply_chain_risk = "high"
    elif "no stockout" in low or "no stock-out" in low or "adequate supply" in low:
        supply_chain_risk = "low"
    elif supply_mentioned:
        supply_chain_risk = "medium"

    # --- stockout flag ---
    stockout_flag = "unknown"
    if "no stockout" in low or "no stock-out" in low:
        stockout_flag = "no"
    elif "stockout" in low or "stock-out" in low:
        if _near(low, "stockout", risk_words, window=80) or _near(low, "stock-out", risk_words, window=80):
            stockout_flag = "risk"
        else:
            stockout_flag = "yes"

    # --- LLIN / ITN coverage % ---
    llin_coverage_pct: Optional[int] = None
    for kw in ("llin", "itn", "net", "coverage"):
        for m in re.finditer(re.escape(kw), low):
            seg = low[max(0, m.start() - 60): m.end() + 60]
            for pm in re.finditer(r"(\d{1,3})\s?%", seg):
                val = int(pm.group(1))
                if 20 <= val <= 100:
                    llin_coverage_pct = val
                    break
            if llin_coverage_pct is not None:
                break
        if llin_coverage_pct is not None:
            break

    return {
        "pyrethroid_resistance": pyrethroid_resistance,
        "recommended_net_type": recommended_net_type,
        "irs_insecticide": irs_insecticide,
        "smc_eligible": smc_eligible,
        "supply_chain_risk": supply_chain_risk,
        "stockout_flag": stockout_flag,
        "llin_coverage_pct": llin_coverage_pct,
    }


def _summarize(country: str, data: dict) -> str:
    return "\n".join(
        [
            f"PMI FY2024 Malaria Profile — {country}:",
            f"- Pyrethroid resistance: {data['pyrethroid_resistance']}",
            f"- Recommended net type: {data['recommended_net_type']}",
            f"- IRS insecticide: {data['irs_insecticide']}",
            f"- SMC eligible: {data['smc_eligible']}",
            f"- Supply-chain risk: {data['supply_chain_risk']}",
            f"- Stockout flag: {data['stockout_flag']}",
            f"- LLIN/ITN coverage: "
            + (f"{data['llin_coverage_pct']}%" if data["llin_coverage_pct"] is not None else "unknown"),
        ]
    )


def _empty_data() -> dict:
    return {
        "pyrethroid_resistance": "unknown",
        "recommended_net_type": "unknown",
        "irs_insecticide": "unknown",
        "smc_eligible": None,
        "supply_chain_risk": "unknown",
        "stockout_flag": "unknown",
        "llin_coverage_pct": None,
    }


def profile(country: str) -> dict:
    """Download + parse the PMI FY2024 malaria profile for `country`.

    `country` is "Mozambique" or "Malawi". Returns the fixed contract dict; the
    parsed result is disk-cached for a week. NEVER raises.
    """
    try:
        # Cache hit within TTL: return without downloading.
        cached = _load_cached(country)
        if cached is not None:
            return cached

        if not _HAVE_PDFMINER:
            return {
                "ok": False,
                "summary": "PMI profile unavailable: pdfminer.six is not installed.",
                "data": _empty_data(),
                "source": _SOURCE,
                "as_of": None,
                "error": "pdfminer.six not installed",
            }

        url = _URLS.get(country)
        if not url:
            return {
                "ok": False,
                "summary": f"No PMI profile URL configured for {country!r}.",
                "data": _empty_data(),
                "source": _SOURCE,
                "as_of": None,
                "error": f"unknown country: {country!r}",
            }

        pdf_bytes = _download_pdf(url)
        if not pdf_bytes:
            return {
                "ok": False,
                "summary": f"PMI profile download failed for {country}.",
                "data": _empty_data(),
                "source": _SOURCE,
                "as_of": None,
                "error": "download failed",
            }

        text = _extract(pdf_bytes)
        if text is None or not text.strip():
            return {
                "ok": False,
                "summary": f"PMI profile text extraction failed for {country}.",
                "data": _empty_data(),
                "source": _SOURCE,
                "as_of": None,
                "error": "text extraction failed",
            }

        data = _parse(text)
        result = {
            "ok": True,
            "summary": _summarize(country, data),
            "data": data,
            "source": _SOURCE,
            "as_of": "FY2024",
            "error": None,
        }
        _save_cached(country, result)
        return result
    except Exception as e:  # never raise out of the module
        return {
            "ok": False,
            "summary": f"PMI profile lookup failed for {country}.",
            "data": _empty_data(),
            "source": _SOURCE,
            "as_of": None,
            "error": f"{type(e).__name__}: {e}",
        }


if __name__ == "__main__":
    import pprint

    for _c in ("Mozambique", "Malawi"):
        print("=" * 60)
        pprint.pprint(profile(_c))
