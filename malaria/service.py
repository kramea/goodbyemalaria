"""High-level entry point for the conversational agent.

Pipeline per turn:
  route -> resolve area -> FETCH live data in parallel -> self-healing data check
  -> build enriched situation brief -> (pre-reasoned skeleton if available)
  -> specialist draft -> adversarial review (devil's advocate + field realism
  -> orchestrator) -> final reply -> persist memory.

An optional on_step callback receives each stage (used by DEMO_MODE streaming).
Everything is fail-open: a failed fetcher/agent degrades gracefully, never blocks
the reply.
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Tuple

from . import (adversarial, agents, config, data, dhis2, flood,
               historical_weather, memory, pmi, prompts, reliefweb,
               self_healing, weather, who)

log = logging.getLogger("malaria.service")


# Conversational holding line shown when we go fetch a LIVE signal the worker's
# question needs but we don't pull by default (live rain forecast, current flood
# levels). Sent in the worker's language before the fetch, then the answer follows.
_LIVE_NOTICE = {
    "English":    "⏳ Let me pull the latest live data for {area} — one moment…",
    "Portuguese": "⏳ Vou buscar os dados ao vivo mais recentes para {area} — um momento…",
    "French":     "⏳ Je récupère les dernières données en direct pour {area} — un instant…",
    "Chichewa":   "⏳ Ndikutenga deta yaposachedwa ya {area} — dikirani pang'ono…",
}


def _live_notice(language: str, area: str) -> str:
    tpl = _LIVE_NOTICE.get(language, _LIVE_NOTICE["English"])
    return tpl.format(area=area)


_CLOSING_HINTS = (
    "thank", "thanks", "that's all", "thats all", "that is all", "all set",
    "we're good", "were good", "no more", "appreciate", "bye", "goodbye", "cheers",
    "obrigad", "adeus", "é tudo", "e tudo", "tchau", "chau",
    "merci", "au revoir", "c'est tout", "c est tout",
    "zikomo", "tsalani", "ndapita", "basi",
)


def _is_closing(message: str) -> bool:
    m = (message or "").lower().strip()
    return any(h in m for h in _CLOSING_HINTS)


def _noop(*_a, **_k):
    return None


@dataclass
class Reply:
    text: str
    region_key: Optional[str] = None
    intervention: Optional[str] = None
    language: Optional[str] = None
    show_map: bool = False
    urgency: Optional[str] = None
    used_pre_reasoned: bool = False
    data_quality: Optional[dict] = field(default=None)


# ---------------------------------------------------------------------------
# Parallel live-data fetch
# ---------------------------------------------------------------------------

def _fetch_all(country, coords, rec, needs_weather, is_triage) -> dict:
    """Run all relevant fetchers concurrently. Each returns its own contract dict
    (or a string for weather/who, which we normalise). Self-timed + fail-open."""
    org_unit = (rec or {}).get("dhis2_org_unit")
    tasks = {}
    if coords and needs_weather:
        tasks["weather"] = lambda: weather.forecast_summary(*coords)
    if coords:
        tasks["historical"] = lambda: historical_weather.historical(*coords)
    if org_unit:
        tasks["dhis2"] = lambda: dhis2.cases(org_unit)
    if country:
        tasks["reliefweb"] = lambda: reliefweb.alerts(country)
        tasks["pmi"] = lambda: pmi.profile(country)
        if is_triage:
            tasks["who"] = lambda: who.country_summary(country)

    results = {}
    if tasks:
        # Hard overall deadline: a single slow source (e.g. a PMI cache miss that
        # falls back to a 30s download) must not stall the whole turn. Whatever
        # hasn't returned by the deadline is treated as MISSING; build_enriched_
        # context then substitutes curated-KB proxies for it. We don't block on
        # shutdown — stragglers finish (or hit their own socket timeout) detached.
        deadline = config.FETCH_TIMEOUT + 1.0
        ex = ThreadPoolExecutor(max_workers=len(tasks))
        futs = {ex.submit(fn): name for name, fn in tasks.items()}
        try:
            for fut in as_completed(futs, timeout=deadline):
                name = futs[fut]
                try:
                    results[name] = fut.result()
                except Exception as e:  # pragma: no cover
                    results[name] = {"ok": False, "summary": "", "data": {}, "error": str(e)}
        except FuturesTimeout:
            pass
        for fut, name in futs.items():
            results.setdefault(name, {"ok": False, "summary": "", "data": {},
                                      "error": "fetch deadline exceeded"})
        ex.shutdown(wait=False, cancel_futures=True)
    # Normalise the string-returning sources into the contract shape.
    for k in ("weather", "who"):
        v = results.get(k)
        if isinstance(v, str):
            results[k] = {"ok": bool(v.strip()), "summary": v, "data": {}, "error": None}
    return results


# ---------------------------------------------------------------------------
# Enriched situation brief (the block injected into the specialist)
# ---------------------------------------------------------------------------

def _na(label="[DATA UNAVAILABLE — see self-healing log]"):
    return label


def build_enriched_context(region_key, country, rec, results, heal_warning="") -> str:
    """Assemble the LIVE SITUATION BRIEF. Missing sources fall back to curated-KB
    proxies (noted inline) rather than silently empty fields."""
    cs = (rec or {}).get("current_status") or {}
    zone_name = (region_key or country or "the area").replace("_", " ").title()
    # Mozambique & Malawi are both Central Africa Time (UTC+2, no DST). Give the
    # worker's LOCAL day-of-week explicitly so the model never has to compute a
    # weekday from a date (it gets that wrong — e.g. "Friday" when it's Sunday).
    now_cat = datetime.now(timezone.utc) + timedelta(hours=2)
    today = now_cat.strftime("%A %d %B %Y, %H:%M")
    L = []
    if heal_warning:
        L += [f"⚠️ {heal_warning}", ""]
    L += [f"=== LIVE SITUATION BRIEF — {zone_name}, {country or 'national'} ===",
          f"TODAY is {today} (Central Africa Time). Use THIS exact day and date for any "
          f"day-of-week or 'today/tomorrow' reference — never infer the weekday yourself.",
          ""]

    # District status (curated KB)
    L += ["── DISTRICT STATUS (curated KB) ──"]
    if rec:
        L += [f"Alert level    : {cs.get('alert_level','unknown')}",
              f"Headline       : {cs.get('headline','—')}",
              f"Season         : {rec.get('season','—')}",
              f"Vectors        : {', '.join(rec.get('vectors', [])) or '—'}",
              f"Known resistance: {rec.get('resistance_profile','—')}",
              f"Last intervention: {rec.get('last_intervention','—')}",
              f"LLIN coverage  : {rec.get('llin_coverage_pct','—')}%"]
    elif country:
        # No single district named — give the per-district curated status for every
        # zone we track in this country so the specialist CAN compare/rank districts
        # by current burden (instead of saying it has no data). Local KB, ~0 latency.
        rows = []
        for rkey, rr in data.regions().items():
            if rr.get("country") != country:
                continue
            rcs = rr.get("current_status") or {}
            rows.append(
                f"• {rkey.replace('_', ' ').title()}: [{rcs.get('alert_level', 'unknown')}] "
                f"{rcs.get('headline', '—')} (trend: {rcs.get('trend', '—')}; "
                f"season: {rr.get('season', '—')}; resistance: {rr.get('resistance_profile', '—')})")
        if rows:
            L += [f"National view — {country}. These are the districts we track; rank/compare "
                  f"them by the status below to answer burden questions, and name them:"]
            L += rows
        else:
            L += [f"(National view — no district data for {country}.)"]
    else:
        L += ["(National view — no single district named.)"]
    L += [""]

    # National context (WHO World Malaria Report 2025, curated)
    profile = (data.meta().get("country_profiles") or {}).get(country or "")
    if profile:
        L += [f"── NATIONAL CONTEXT — {country} (WHO WMR {profile.get('year', 2025)}) ──",
              f"Burden        : {profile.get('estimated_cases', '—')}",
              f"Incidence trend: {profile.get('incidence_trend_2015_2024', '—')}",
              f"Vector control: {profile.get('vector_control', '—')}",
              f"Chemoprevention: {profile.get('chemoprevention', '—')}",
              f"Vaccine       : {profile.get('vaccine', '—')}",
              "[Source: WHO World Malaria Report 2025]", ""]

    # ReliefWeb
    rw = results.get("reliefweb") or {}
    L += ["── RELIEFWEB LIVE ALERTS (last 72h) ──"]
    L += [rw.get("summary") if rw.get("ok") else
          "No active alerts retrieved (ReliefWeb unavailable — assume none).",
          "[Source: ReliefWeb API]", ""]

    # DHIS2 (fallback: KB alert level as case-trend proxy)
    dh = results.get("dhis2") or {}
    L += ["── DHIS2 WEEKLY CASE COUNTS ──"]
    if dh.get("ok"):
        d = dh.get("data", {})
        L += [f"Recent periods : w0={d.get('w0')}, w1={d.get('w1')}, w2={d.get('w2')} "
              f"(WoW {d.get('wow_pct')}%)", "[Source: DHIS2 HMIS]"]
    else:
        L += [f"[DHIS2 unavailable — using KB alert level '{cs.get('alert_level','unknown')}' "
              f"as case-trend proxy]"]
    L += [""]

    # Rainfall — historical
    hist = results.get("historical") or {}
    L += ["── RAINFALL — HISTORICAL 90 DAYS ──"]
    if hist.get("ok"):
        d = hist.get("data", {})
        L += [f"Last 10d       : {d.get('rain_10d_mm')}mm (normal ~{d.get('rain_10d_normal_mm')}mm)",
              f"Last 30d       : {d.get('rain_30d_mm')}mm",
              f"Peak daily     : {d.get('rain_peak_mm')}mm on {d.get('rain_peak_date')}",
              f"Breeding window: {d.get('breeding_window_status')}",
              f"  → eggs ~{d.get('eggs_laid_date')}, larvae ~{d.get('larvae_peak_date')}, "
              f"adults emerge ~{d.get('adult_emerge_date')}",
              "[Source: Open-Meteo Archive API]"]
    else:
        L += [_na()]
    L += [""]

    # Rainfall — forecast
    wx = results.get("weather") or {}
    spray = (hist.get("data") or {}).get("spray_safe_days")
    L += ["── RAINFALL — FORECAST 7 DAYS ──"]
    L += [wx.get("summary") if wx.get("ok") else "(forecast not requested this turn)"]
    if spray:
        L += [f"Spray-safe days: {', '.join(spray)}"]
    L += ["[Source: Open-Meteo Forecast API]", ""]

    # Live flood signal (river discharge) — only present when fetched this turn.
    fl = results.get("flood_signal") or {}
    if fl.get("ok") and fl.get("summary"):
        L += ["── LIVE FLOOD SIGNAL (river discharge, fetched now) ──",
              fl["summary"], "[Source: GloFAS / Open-Meteo Flood API]", ""]

    # PMI (fallback: KB resistance)
    pm = results.get("pmi") or {}
    L += ["── PMI OPERATIONAL INTELLIGENCE (FY2024) ──"]
    if pm.get("ok"):
        d = pm.get("data", {})
        L += [f"Pyrethroid resistance: {d.get('pyrethroid_resistance')}",
              f"Recommended net : {d.get('recommended_net_type')}",
              f"IRS insecticide : {d.get('irs_insecticide')}",
              f"SMC eligible    : {d.get('smc_eligible')}",
              f"Supply-chain risk: {d.get('supply_chain_risk')}",
              f"Stockout flag   : {d.get('stockout_flag')}",
              "[Source: PMI FY2024 Malaria Profile]"]
    else:
        L += [f"[PMI unavailable — using KB resistance: {(rec or {}).get('resistance_profile','unknown')}]"]
    L += [""]

    # WHO baseline
    wh = results.get("who") or {}
    if wh.get("summary"):
        L += ["── WHO NATIONAL BASELINE ──", wh["summary"], "[Source: WHO GHO]", ""]

    # Vector & insecticide-resistance guidance (WHO WMR 2025, curated reference)
    mv = data.meta().get("mosquito_vectors") or {}
    ir = mv.get("insecticide_resistance") or {}
    steph = mv.get("anopheles_stephensi") or {}
    if ir or steph:
        L += ["── VECTOR & RESISTANCE GUIDANCE (WHO WMR 2025) ──"]
        if ir.get("net_choice"):
            L += [f"Nets : {ir['net_choice']}"]
        if ir.get("irs_choice"):
            L += [f"IRS  : {ir['irs_choice']}"]
        if steph.get("status_mozambique_malawi"):
            L += [f"An. stephensi: {steph['status_mozambique_malawi']}"]
        L += ["[Source: WHO World Malaria Report 2025]", ""]

    L += ["=== END SITUATION BRIEF ==="]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Deterministic signals (computed in code, not asked of an LLM)
# ---------------------------------------------------------------------------

def _compute_urgency(alert, flooding, results) -> str:
    rw = ((results.get("reliefweb") or {}).get("summary") or "").lower()
    wow = ((results.get("dhis2") or {}).get("data") or {}).get("wow_pct")
    if alert == "outbreak" or (isinstance(wow, (int, float)) and wow > 30) or "outbreak" in rw:
        return "outbreak"
    if flooding or "flood" in rw:
        return "flood"
    hd = (results.get("historical") or {}).get("data") or {}
    r10, norm = hd.get("rain_10d_mm"), hd.get("rain_10d_normal_mm")
    if alert == "elevated" or (isinstance(r10, (int, float)) and isinstance(norm, (int, float))
                               and norm > 0 and r10 > 2 * norm):
        return "elevated"
    return alert or "normal"


def _resistance_key(rec, results) -> str:
    pm = ((results.get("pmi") or {}).get("data") or {}).get("pyrethroid_resistance")
    if pm in ("confirmed", "suspected"):
        return f"pyrethroid_{pm}"
    prof = ((rec or {}).get("resistance_profile") or "").lower()
    if "confirm" in prof and "pyrethroid" in prof:
        return "pyrethroid_confirmed"
    if "suspect" in prof:
        return "pyrethroid_suspected"
    return "unknown"


_PRETRAINED = None


def _pretrained_regions() -> dict:
    """Lazily load the offline-trained skeletons from regions_pretrained.json."""
    global _PRETRAINED
    if _PRETRAINED is None:
        try:
            _PRETRAINED = json.loads(config.PRE_REASONED_FILE.read_text()).get("regions", {})
        except Exception:
            _PRETRAINED = {}
    return _PRETRAINED


def _get_pre_reasoned(region_key, rec, urgency, resistance_key):
    """Return a validated pre-reasoned decision for (urgency, resistance) if present
    and fresh (< PRE_REASONED_MAX_AGE_DAYS). Reads the trained file first, then any
    inline KB entry. Empty until run_training.py populates it."""
    trained = (_pretrained_regions().get(region_key, {}) or {}).get("pre_reasoned", {})
    inline = (rec or {}).get("pre_reasoned") or {}
    pr = (trained.get(urgency, {}).get(resistance_key)
          or inline.get(urgency, {}).get(resistance_key))
    if not pr:
        return None
    try:
        ts = datetime.fromisoformat(pr.get("validated_at", "").replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - ts).total_seconds() / 86400
        if age_days > config.PRE_REASONED_MAX_AGE_DAYS:
            return None
    except Exception:
        return None
    return pr


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def handle_message(
    phone: str,
    message: str,
    pin: Optional[Tuple[float, float]] = None,
    pin_region: Optional[str] = None,
    precomputed_route: "Optional[agents.Route]" = None,
    on_step: Optional[Callable[[str, dict], None]] = None,
    on_token: Optional[Callable[[str], None]] = None,
    on_notice: Optional[Callable[[str], None]] = None,
) -> Reply:
    step = on_step or _noop
    session = memory.load(phone)
    first = memory.is_first_contact(session)
    context = memory.context_for(session)
    _t0 = time.perf_counter()

    # 1) Resolve the area DETERMINISTICALLY (text match, no model). Doing this
    #    first means the live-data fetch no longer has to wait on the router —
    #    the two slowest steps can run concurrently (see step 2).
    explicit_region = pin_region or data.match_region_by_text(message)
    explicit_country = data.match_country_by_text(message)
    if explicit_region:
        region_key = explicit_region
        country = (data.region_record(region_key) or {}).get("country")
    elif explicit_country:
        region_key, country = None, explicit_country
    else:
        region_key = session.get("region_key")
        country = session.get("country") or (
            (data.region_record(region_key) or {}).get("country") if region_key else None)
    session["region_key"], session["country"] = region_key, country
    country_level = bool(country and not region_key)

    coords: Optional[Tuple[float, float]] = None
    if pin:
        coords = pin
    elif region_key:
        center = (data.region_geo(region_key) or {}).get("center")
        if center:
            coords = (center[0], center[1])

    rec = data.region_record(region_key) if region_key else None
    cs = (rec or {}).get("current_status") or {}
    alert = cs.get("alert_level", "")
    flooding = bool(cs.get("flooding_now"))

    # 2) Router + FAST live-data fetch IN PARALLEL. The fast sources are cached/
    #    quick (<1s); the live rain FORECAST is the one slow source (~5s), and most
    #    questions ("how's the situation?") don't need it — curated seasonality
    #    covers them. So we fetch everything-but-weather alongside the router, then
    #    fetch weather serially ONLY when the router flags the question needs it.
    #    This takes a "situation" turn's pre-answer wait from ~4s down to ~1s.
    _tf = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_route = ex.submit(
            lambda: precomputed_route or agents.route(message, session_context=context))
        f_fetch = ex.submit(_fetch_all, country, coords, rec, False, True)
        r = f_route.result()
        results = f_fetch.result()

    language = session.get("language") or r.language
    session["language"] = language

    # ON-DEMAND LIVE PULLS — signals we skip by default. If the question needs the
    # live rain forecast or a current flood reading, tell the worker we're pulling
    # live data (in their language), THEN fetch it. (A KB-flagged active flood is
    # fetched silently as before — the worker didn't ask for it.)
    want_weather = bool(r.needs_weather and coords)
    want_flood_live = bool(r.needs_flood and coords)
    if (want_weather or want_flood_live) and on_notice:
        area_label = (region_key or country or "your area").replace("_", " ").title()
        try:
            on_notice(_live_notice(language, area_label))
        except Exception:  # pragma: no cover — narration must never block the answer
            log.exception("on_notice failed")

    if want_weather:
        # Hard-cap the slow forecast so it can't blow the turn; KB seasonality is
        # the fallback. Detached shutdown so a slow socket never blocks us.
        wex = ThreadPoolExecutor(max_workers=1)
        fut = wex.submit(weather.forecast_summary, *coords)
        try:
            wx = fut.result(timeout=config.FETCH_TIMEOUT)
            results["weather"] = {"ok": bool((wx or "").strip()), "summary": wx,
                                  "data": {}, "error": None}
        except Exception:
            results["weather"] = {"ok": False, "summary": "", "data": {},
                                  "error": "forecast slow/unavailable"}
        wex.shutdown(wait=False, cancel_futures=True)

    if (want_flood_live or flooding) and coords:  # live river-discharge signal
        # Hard-cap like the forecast: flood makes two upstream calls, so bound the
        # whole operation rather than each request. Detached so it never blocks.
        fex = ThreadPoolExecutor(max_workers=1)
        ffut = fex.submit(flood.discharge_summary, *coords)
        try:
            fs = ffut.result(timeout=config.FETCH_TIMEOUT)
            if fs:
                results["flood_signal"] = {"ok": True, "summary": fs, "data": {}}
        except Exception:
            pass
        fex.shutdown(wait=False, cancel_futures=True)
    _t_fetch = time.perf_counter() - _tf

    is_triage = (r.intent == "triage" or r.intervention == "triage")
    step("route", {"language": language, "intent": r.intent, "intervention": r.intervention,
                   "needs_weather": r.needs_weather})
    step("fetch", {"sources": {k: bool(v.get("ok")) for k, v in results.items()},
                   "seconds": round(_t_fetch, 1)})

    # 4) Self-healing data-quality check. The quality report is computed in code
    #    (cheap) and the situation brief already substitutes curated-KB proxies
    #    for any missing source inline, so on the live path we SKIP the extra
    #    LLM advisory call — it only adds latency. DEMO_MODE still runs it to
    #    narrate the self-healing reasoning.
    quality = self_healing.build_quality_report(results)
    heal = None
    heal_warning = ""
    if config.DEMO_MODE:
        heal = self_healing.run(quality["report"])
        if heal and heal.specialist_warning:
            heal_warning = heal.specialist_warning
    step("self_heal", {"report": quality["report"],
                       "has_issues": quality["has_issues"],
                       "warning": heal_warning,
                       "fallbacks": (heal.fallbacks_applied if heal else [])})

    # 5) Enriched brief + deterministic signals.
    brief = build_enriched_context(region_key, country, rec, results, heal_warning)
    urgency = _compute_urgency(alert, flooding, results)
    resistance_key = _resistance_key(rec, results)
    pre = _get_pre_reasoned(region_key, rec, urgency, resistance_key)
    use_pre_reasoned = pre is not None
    step("brief", {"urgency": urgency, "resistance": resistance_key,
                   "use_pre_reasoned": use_pre_reasoned, "chars": len(brief)})

    # 6) Playbook + urgency directives.
    key = "triage" if is_triage else r.intervention
    playbook = prompts.PLAYBOOKS.get(key) or prompts.PLAYBOOKS["triage"]
    directives = []
    if country_level:
        directives.append(prompts.COUNTRY_DIRECTIVE)
    if urgency == "outbreak":
        directives.append(prompts.OUTBREAK_DIRECTIVE)
    if urgency == "flood" or flooding:
        directives.append(prompts.FLOOD_DIRECTIVE)
    if directives:
        playbook = "\n\n".join(directives) + "\n\n" + playbook

    # Pre-reasoned skeleton (prepended to the data block) when available.
    data_block = brief
    if use_pre_reasoned:
        preamble = prompts.PRE_REASONED_PREAMBLE.format(
            priority_intervention=pre.get("priority_intervention", "—"),
            product=pre.get("product", "—"),
            fallback_intervention=pre.get("fallback_intervention", "—"),
            contraindications=pre.get("contraindications", "—"),
            validated_at=pre.get("validated_at", "—"))
        data_block = preamble + "\n\n" + brief

    # 7) Specialist draft.
    _ts = time.perf_counter()
    # Stream specialist tokens to the caller only on the live path: in DEMO_MODE
    # the adversarial reviewer may rewrite the draft, so streaming the draft would
    # then be replaced by a different final answer — confusing. There we keep the
    # draft un-streamed and emit the (possibly revised) final at the end.
    draft = agents.specialist(
        message, playbook=playbook, data_block=data_block, weather_summary="",
        session_context=context, first_contact=first, language=language,
        on_token=(None if config.DEMO_MODE else on_token))
    _t_spec = time.perf_counter() - _ts
    step("specialist", {"draft": draft, "seconds": round(_t_spec, 1)})

    # 8) Adversarial review (devil's advocate + field realism + orchestrator).
    #    This is 3 extra model calls AFTER we already have a good answer — the
    #    single biggest latency cost on the live path — so production SKIPS it.
    #    DEMO_MODE still runs it as the multi-agent showpiece.
    final = draft
    devil = realism = None
    run_adv = config.DEMO_MODE
    if run_adv:
        _ta = time.perf_counter()
        final, devil, realism = adversarial.review(draft, brief, language)
        _t_adv = time.perf_counter() - _ta
        step("adversarial", {
            "devil": devil.model_dump() if devil else None,
            "realism": realism.model_dump() if realism else None,
            "changed": final.strip() != draft.strip(),
            "final": final, "seconds": round(_t_adv, 1)})

    log.info("TIMING lang=%s interv=%s urgency=%s pre=%s | fetch=%.1fs spec=%.1fs total=%.1fs",
             language, key, urgency, use_pre_reasoned, _t_fetch, _t_spec,
             time.perf_counter() - _t0)

    memory.record_turn(session, message=message, reply=final, region_key=region_key)
    memory.save(phone, session)

    show_map = first or _is_closing(message)
    step("final", {"text": final})
    return Reply(text=final, region_key=region_key, intervention=key, language=language,
                 show_map=show_map, urgency=urgency, used_pre_reasoned=use_pre_reasoned,
                 data_quality=quality["statuses"])
