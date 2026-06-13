"""High-level entry point for the conversational advisor.

Resolve the worker's area -> pull curated data + a live rain forecast for it ->
one fast advisor call -> persist session memory. No multi-agent loop.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from . import agents, data, flood, memory, prompts, weather, who


# Multilingual closing phrases — when the worker signals they're wrapping up we
# re-attach the map (a handy parting reference), but NOT on every middle turn.
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


@dataclass
class Reply:
    text: str
    region_key: Optional[str] = None
    intervention: Optional[str] = None
    language: Optional[str] = None
    show_map: bool = False


def handle_message(
    phone: str,
    message: str,
    pin: Optional[Tuple[float, float]] = None,
    pin_region: Optional[str] = None,
    precomputed_route: "Optional[agents.Route]" = None,
) -> Reply:
    """Route the message, then answer as the relevant intervention specialist.

    precomputed_route lets the webhook reuse the route it already ran to pick the
    instant greeting, so we don't classify twice.
    """
    session = memory.load(phone)
    first = memory.is_first_contact(session)
    context = memory.context_for(session)

    # 1) Router (Haiku): language + intent + intervention + whether weather is needed.
    r = precomputed_route or agents.route(message, session_context=context)

    # Lock language for the whole conversation so replies never drift into the
    # area's default language (e.g. Portuguese).
    language = session.get("language") or r.language
    session["language"] = language

    # Resolve the area. Precedence: GPS pin > a region named in THIS message >
    # a COUNTRY named in this message > continuity from the session. A fresh
    # country/region mention overrides stale session state, so saying "Malawi"
    # after discussing Mozambique switches countries instead of sticking.
    explicit_region = pin_region or data.match_region_by_text(message)
    explicit_country = data.match_country_by_text(message)
    if explicit_region:
        region_key = explicit_region
        country = (data.region_record(region_key) or {}).get("country")
    elif explicit_country:
        region_key = None
        country = explicit_country
    else:
        region_key = session.get("region_key")
        country = session.get("country") or (
            (data.region_record(region_key) or {}).get("country") if region_key else None)
    session["region_key"] = region_key
    session["country"] = country
    country_level = bool(country and not region_key)

    # Data block: a single district if known, else the whole country, else everything.
    if region_key:
        data_block = data.region_block(region_key)
    elif country:
        data_block = data.country_block(country)
    else:
        data_block = data.knowledge_block()

    # Area coords (pin, else region center) — used for live weather + flood lookups.
    coords: Optional[Tuple[float, float]] = None
    if pin:
        coords = pin
    elif region_key:
        center = (data.region_geo(region_key) or {}).get("center")
        if center:
            coords = (center[0], center[1])

    # Current situation: district-level alert/flood only apply when a district is known.
    rec = data.region_record(region_key) if region_key else None
    cs = (rec or {}).get("current_status") or {}
    alert = cs.get("alert_level", "")
    flooding = bool(cs.get("flooding_now"))

    # WHO national figure on broad "situation" (triage) turns; skip on specific follow-ups.
    if country and (r.intent == "triage" or r.intervention == "triage"):
        who_summary = who.country_summary(country)
        if who_summary:
            data_block = f"{data_block}\n{who_summary}\n"

    # Live flood signal only when the area is actively flooding (keeps latency down).
    if flooding and coords:
        fs = flood.discharge_summary(*coords)
        if fs:
            data_block = f"{data_block}\n{fs}\n"

    # 2) Pick the specialist playbook. Broad openers -> triage (the 3 buckets);
    # a specific question -> that intervention's specialist. The 🦟 greeting is
    # handled separately via first_contact, so a specific opener still gets greeted.
    key = "triage" if r.intent == "triage" or r.intervention == "triage" else r.intervention
    playbook = prompts.PLAYBOOKS.get(key) or prompts.PLAYBOOKS["triage"]

    # Urgency cascade: country-level overview, then outbreak / active flooding.
    directives = []
    if country_level:
        directives.append(prompts.COUNTRY_DIRECTIVE)
    if alert == "outbreak":
        directives.append(prompts.OUTBREAK_DIRECTIVE)
    if flooding:
        directives.append(prompts.FLOOD_DIRECTIVE)
    if directives:
        playbook = "\n\n".join(directives) + "\n\n" + playbook

    # 3) Live rain forecast only when the router says the question needs it.
    weather_summary = ""
    if r.needs_weather and coords:
        weather_summary = weather.forecast_summary(*coords)

    # 4) Specialist (Sonnet) writes the reply.
    text = agents.specialist(
        message,
        playbook=playbook,
        data_block=data_block,
        weather_summary=weather_summary,
        session_context=context,
        first_contact=first,
        language=language,
    )

    memory.record_turn(session, message=message, reply=text, region_key=region_key)
    memory.save(phone, session)

    # Attach the map only on the first message and on a closing message — not on
    # every middle turn.
    show_map = first or _is_closing(message)
    return Reply(text=text, region_key=region_key, intervention=key,
                 language=language, show_map=show_map)
