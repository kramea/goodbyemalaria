"""The three agents: Navigator, Adversarial reviewer, Verifier.

Each runs in a fresh context window (a fresh API call with its own system prompt),
per the three-agent architecture in the brief.
"""

import os
from typing import List, Optional

import anthropic
import httpx
from pydantic import BaseModel, Field

from . import config, prompts
from .data import knowledge_block

_client: Optional[anthropic.Anthropic] = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # Strip the key: a trailing newline/space (easy to introduce when pasting
        # into a host's env-var UI, e.g. Railway) makes an illegal HTTP header
        # value and every API call fails with "Connection error" — strip defends
        # against that regardless of how the key was entered.
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        # Custom httpx client: recycle idle keep-alive connections quickly so we
        # never reuse a half-open socket the network silently dropped (the cause of
        # intermittent ~50s stalls), and use a short connect timeout. Combined with
        # max_retries, a stalled call is caught fast and retried on a fresh socket.
        http_client = httpx.Client(
            timeout=httpx.Timeout(config.REQUEST_TIMEOUT, connect=config.CONNECT_TIMEOUT),
            limits=httpx.Limits(max_keepalive_connections=10,
                                keepalive_expiry=config.KEEPALIVE_EXPIRY),
        )
        _client = anthropic.Anthropic(
            api_key=api_key or None,
            max_retries=config.MAX_RETRIES,
            http_client=http_client,
        )
    return _client


def warm_connection() -> None:
    """Open a connection to the API at boot so the first user message reuses a
    warm socket instead of paying TLS setup (or hitting a cold stall). Cheap and
    best-effort — never raises."""
    try:
        client().models.list(limit=1)
    except Exception:
        pass


def _text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text").strip()


def _create(**kwargs):
    """Stream the response and return the final Message.

    Streaming keeps data flowing token-by-token, so the read timeout applies to
    the gap BETWEEN chunks rather than to the whole (possibly long) generation.
    On a flaky connection this is what prevents a request from stalling until the
    timeout fires. Falls back gracefully if 'thinking' is unsupported.
    """
    try:
        with client().messages.stream(**kwargs) as stream:
            return stream.get_final_message()
    except (TypeError, anthropic.BadRequestError) as e:
        if "thinking" in str(e).lower() and "thinking" in kwargs:
            kwargs.pop("thinking", None)
            with client().messages.stream(**kwargs) as stream:
                return stream.get_final_message()
        raise


# ---------------------------------------------------------------------------
# Acknowledger (Haiku) — instant, language-aware holding reply
# ---------------------------------------------------------------------------

ACK_SYSTEM = """\
You are MalarIA's fast first-response assistant for malaria-prevention field
workers in Mozambique and Malawi. A worker just sent a WhatsApp message.

Do ONLY this:
1. Detect the language the worker ACTUALLY WROTE IN (English, Portuguese,
   French, or Chichewa) — judge by the words on the page, NOT by the country.
   "Hi I am in Maputo province today" is ENGLISH even though Maputo is in
   Portuguese-speaking Mozambique → reply in English. Only if the message is too
   short/ambiguous to tell (e.g. just a place name) fall back to Portuguese for
   Mozambique places, English for Malawi places.
2. Reply in 1-2 SHORT sentences, entirely in that language: thank them,
   acknowledge their area/situation if mentioned, and say you are gathering the
   latest malaria data (rainfall, season, resistance, recent interventions) and
   will send a specific recommendation in a moment.

Do NOT give any recommendation, intervention, or clinical advice yet — this is
only a holding reply to keep the worker engaged. Keep acronyms (IRS, ITN, SMC)
as-is. Output ONLY the reply text, nothing else."""


def acknowledger(message: str) -> str:
    """Fast Haiku reply: detect language + engaging holding message."""
    resp = _create(
        model=config.ACK_MODEL,
        max_tokens=300,
        system=ACK_SYSTEM,
        messages=[{"role": "user", "content": message}],
    )
    return _text(resp)


# ---------------------------------------------------------------------------
# Language detection (fast, deterministic single word — locked per conversation)
# ---------------------------------------------------------------------------

_LANGS = {"english", "portuguese", "french", "chichewa"}

_DETECT_SYSTEM = (
    "Identify the language the message is written in. Reply with EXACTLY one "
    "word, no punctuation: English, Portuguese, French, or Chichewa. Judge ONLY "
    "by the words written, NOT by any country or place name mentioned — "
    "'Hi I am in Maputo today' is English. If genuinely unsure, reply English."
)


def detect_language(message: str) -> str:
    """Return one of English/Portuguese/French/Chichewa (defaults to English)."""
    try:
        resp = _create(
            model=config.ACK_MODEL,  # Haiku — this trivial task is reliable + fast
            max_tokens=5,
            system=_DETECT_SYSTEM,
            messages=[{"role": "user", "content": message}],
        )
        w = _text(resp).strip().strip(".").lower()
        if w in _LANGS:
            return w.capitalize()
    except Exception:
        pass
    return "English"


# ---------------------------------------------------------------------------
# Router (Haiku, structured) — classify + detect language in one fast call
# ---------------------------------------------------------------------------

class Route(BaseModel):
    language: str = Field(description="English, Portuguese, French, or Chichewa")
    intent: str = Field(description='"triage" or "specific"')
    timeline: str = Field(description="immediate, month, season, or mixed")
    intervention: str = Field(description="an intervention key, or 'triage'/'general'")
    needs_weather: bool = Field(description="true if the rain forecast is needed")
    rationale: str = Field(description="<=12 words")


def route(message: str, session_context: str = "") -> Route:
    """Fast classifier: language + intent + intervention + whether weather is needed."""
    content = message
    if session_context:
        content = f"PRIOR CONVERSATION:\n{session_context}\n\nLATEST MESSAGE:\n{message}"
    try:
        resp = client().messages.parse(
            model=config.ROUTER_MODEL,
            max_tokens=200,
            system=prompts.ROUTER_SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_format=Route,
        )
        r = resp.parsed_output
        if r is not None:
            return _normalize_route(r)
    except Exception:
        pass
    # Fallback: safe default (triage, no weather, English) so the turn still works.
    return Route(language="English", intent="triage", timeline="mixed",
                 intervention="triage", needs_weather=False, rationale="fallback")


def _normalize_route(r: Route) -> Route:
    r.language = (r.language or "English").strip().capitalize()
    if r.language not in {"English", "Portuguese", "French", "Chichewa"}:
        r.language = "English"
    valid = set(prompts.INTERVENTIONS) | {"triage", "general"}
    if r.intervention not in valid:
        r.intervention = "triage"
    return r


# ---------------------------------------------------------------------------
# Specialist (Sonnet) — answers as the expert for the routed intervention
# ---------------------------------------------------------------------------

def specialist(
    message: str,
    playbook: str,
    data_block: str,
    weather_summary: str = "",
    session_context: str = "",
    first_contact: bool = True,
    language: str = "",
) -> str:
    parts: List[str] = []
    if language:
        parts += [f"REPLY LANGUAGE: {language}. Write your ENTIRE reply in {language} "
                  f"only — every word, including section headers. Do NOT mix in words "
                  f"from any other language, even though the area data may be written "
                  f"in another language.", ""]
    parts += [data_block]
    if weather_summary:
        parts += ["", weather_summary]
    if session_context:
        parts += ["", "PRIOR CONVERSATION (same worker — continue in the same "
                  "language, build on it):", session_context]
    parts += ["", ("This is the worker's FIRST substantive reply — give the situation "
                   "and the ⚡/📅/🌧️ options. Do NOT greet (already done).")
              if first_contact else
              ("This is a FOLLOW-UP in an ongoing chat — answer the specific question "
               "directly and concretely; do NOT re-greet or restate the whole triage.")]
    parts += ["", "LENGTH: keep it focused and WhatsApp-friendly — aim for ~180 "
              "words, and use a little more only when the question genuinely needs "
              "the detail. Lead with the key action; trim hedging. Always finish "
              "your last sentence — never trail off mid-thought."]
    parts += ["", f'FIELD WORKER MESSAGE:\n"{message}"']

    system = prompts.SPECIALIST_SYSTEM.replace("{playbook}", playbook)
    resp = _create(
        model=config.SPECIALIST_MODEL,
        max_tokens=1100,
        system=system,
        messages=[{"role": "user", "content": "\n".join(parts)}],
    )
    return _text(resp)


# ---------------------------------------------------------------------------
# Advisor (single conversational agent — legacy single-call path, kept as fallback)
# ---------------------------------------------------------------------------

def advisor(
    message: str,
    data_block: str,
    weather_summary: str = "",
    session_context: str = "",
    first_contact: bool = True,
    language: str = "",
) -> str:
    """One fast call: detect language, triage or answer, in the worker's language.

    Replaces the navigator/adversarial/verifier loop on the live path. The model
    sees the curated data for the worker's area plus (when available) a live rain
    forecast, and replies conversationally.
    """
    parts: List[str] = []
    if language:
        parts += [f"REPLY LANGUAGE: {language}. Write your ENTIRE reply in "
                  f"{language} only — every word, including the section headers. "
                  f"Do NOT mix in words from any other language, even though the "
                  f"area data below may be written in another language.", ""]
    parts += [data_block]

    if weather_summary:
        parts += ["", weather_summary]

    if session_context:
        parts += ["", "PRIOR CONVERSATION (same worker — continue in the same "
                  "language and build on it):", session_context]

    if first_contact:
        parts += ["", "This is the worker's FIRST message — open with the 🦟 "
                  "MalarIA greeting and the three timeline options."]
    else:
        parts += ["", "This is a FOLLOW-UP — skip the greeting/banner; just answer "
                  "the question directly."]

    parts += ["", f'FIELD WORKER MESSAGE:\n"{message}"']

    # No extended thinking here: this is a fast conversational reply over curated
    # data ("simple rules"), and Twilio's webhook timeout (~15s) is the budget.
    resp = _create(
        model=config.ADVISOR_MODEL,
        max_tokens=1200,
        system=prompts.ADVISOR_SYSTEM,
        messages=[{"role": "user", "content": "\n".join(parts)}],
    )
    return _text(resp)


# ---------------------------------------------------------------------------
# Navigator
# ---------------------------------------------------------------------------

def navigator(
    message: str,
    session_context: str = "",
    revision_note: str = "",
    previous_output: str = "",
    weak_first_draft: bool = False,
    model: str = "",
) -> str:
    """Generate (or revise) a recommendation for a field worker message.

    weak_first_draft is a DEMO-ONLY switch: it forces a deliberately vague first
    draft (no product/quantity/timing) so the adversarial+verifier loop visibly
    has to challenge and self-correct. Never used in normal operation.
    """
    parts: List[str] = [knowledge_block(), ""]

    if session_context:
        parts.append("PRIOR SESSION CONTEXT (this phone number — pick up where you left off):")
        parts.append(session_context)
        parts.append("")

    parts.append(f'FIELD WORKER MESSAGE:\n"{message}"')

    if revision_note and previous_output:
        parts.append("")
        parts.append("YOUR PREVIOUS DRAFT:")
        parts.append(previous_output)
        parts.append("")
        parts.append(
            "REVISE the draft to fix this specific issue, keeping everything else "
            f"that was correct and staying in the same language:\n{revision_note}"
        )
    elif weak_first_draft:
        parts.append("")
        parts.append(
            "DEMO CONSTRAINT for THIS draft only: produce a brief, GENERIC first "
            "pass. Name the time horizon and the intervention CATEGORY, but do NOT "
            "include product names, quantities, coverage targets, or timing, and "
            "keep [WHY] to one vague sentence with no specific data signal. (A "
            "reviewer will push you to make it specific.)"
        )

    resp = _create(
        model=model or config.NAVIGATOR_MODEL,
        max_tokens=2000,
        thinking={"type": "adaptive"},
        output_config={"effort": config.EFFORT},
        system=prompts.NAVIGATOR_SYSTEM,
        messages=[{"role": "user", "content": "\n".join(parts)}],
    )
    return _text(resp)


# ---------------------------------------------------------------------------
# Adversarial reviewer (fresh context)
# ---------------------------------------------------------------------------

def adversarial(message: str, recommendation: str) -> str:
    """Return 'APPROVED' or 'CHALLENGE: <issue>'."""
    content = (
        f"{knowledge_block()}\n\n"
        f'FIELD WORKER MESSAGE:\n"{message}"\n\n'
        f"RECOMMENDATION UNDER REVIEW:\n{recommendation}"
    )
    resp = _create(
        model=config.ADVERSARIAL_MODEL,
        max_tokens=2000,
        thinking={"type": "adaptive"},
        output_config={"effort": config.EFFORT},
        system=prompts.ADVERSARIAL_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    return _text(resp)


# ---------------------------------------------------------------------------
# Verifier (fresh context, structured output)
# ---------------------------------------------------------------------------

class RubricScore(BaseModel):
    score: int = Field(description="Total rubric score, 0-8")
    passed: List[int] = Field(description="Criterion numbers (1-8) that passed")
    failed: List[int] = Field(description="Criterion numbers (1-8) that failed")
    fix_needed: str = Field(description="One specific instruction to fix failures; empty if none")
    approved: bool = Field(description="True if score meets the threshold")


def verifier(message: str, recommendation: str) -> RubricScore:
    content = (
        f"{knowledge_block()}\n\n"
        f'FIELD WORKER MESSAGE:\n"{message}"\n\n'
        f"RECOMMENDATION TO SCORE:\n{recommendation}"
    )
    system = prompts.VERIFIER_SYSTEM.replace("{threshold}", str(config.RUBRIC_THRESHOLD))

    result: Optional[RubricScore] = None
    try:
        resp = client().messages.parse(
            model=config.VERIFIER_MODEL,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=RubricScore,
        )
        result = resp.parsed_output
    except Exception:
        # Fall back to a plain JSON request if structured-output parsing is
        # unavailable on this SDK/model combination.
        result = _verify_via_json(system, content)

    if result is None:
        # Last-resort: treat unparseable verifier output as a fail so the loop
        # forces a regeneration rather than shipping unscored output.
        return RubricScore(
            score=0, passed=[], failed=list(range(1, 9)),
            fix_needed="Verifier could not parse output; regenerate cleanly.",
            approved=False,
        )
    # Enforce the threshold authoritatively on our side.
    result.approved = result.score >= config.RUBRIC_THRESHOLD
    return result


def _verify_via_json(system: str, content: str) -> Optional[RubricScore]:
    import json
    import re

    resp = _create(
        model=config.VERIFIER_MODEL,
        max_tokens=1500,
        system=system + "\n\nReturn ONLY a JSON object with keys: "
                        "score (int), passed (int[]), failed (int[]), "
                        "fix_needed (str), approved (bool). No prose, no code fences.",
        messages=[{"role": "user", "content": content}],
    )
    raw = _text(resp)
    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not m:
        return None
    try:
        return RubricScore(**json.loads(m.group(0)))
    except Exception:
        return None
