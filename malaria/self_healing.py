"""Self-healing data-quality layer.

Before the specialist reasons, we check every live fetcher's result. If one or
more came back empty/errored (MISSING) we run a lightweight data-quality agent
that decides which documented fallback to apply and what uncertainty to surface
to the specialist. The mechanical fallback (substituting curated-KB proxies into
the situation brief) happens in service.build_enriched_context; this module
produces the human-readable quality report + the agent's advisory verdict.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from . import agents, config, prompts

# Sources we expect in a turn -> friendly label for the report.
_LABELS = {
    "who": "WHO national baseline",
    "reliefweb": "ReliefWeb alerts",
    "dhis2": "DHIS2 case counts",
    "historical": "Historical rainfall",
    "weather": "Rain forecast",
    "pmi": "PMI operational intel",
}


class SelfHealResult(BaseModel):
    data_ok: bool = Field(description="true if no critical gaps remain")
    fallbacks_applied: List[str] = Field(default_factory=list)
    conflicts_resolved: List[str] = Field(default_factory=list)
    uncertainty_flags: List[str] = Field(default_factory=list)
    specialist_warning: Optional[str] = Field(
        default=None, description="one sentence to prepend to the specialist context, or null")


def build_quality_report(results: dict) -> dict:
    """results: {source_key: <fetcher contract dict or None>}.

    Returns {"has_issues": bool, "report": str, "statuses": {src: "OK"|"MISSING"}}.
    A source is OK when its contract dict has ok=True; otherwise MISSING.
    """
    statuses, lines = {}, []
    for key, label in _LABELS.items():
        r = results.get(key)
        if r is None:
            continue  # source not relevant this turn (e.g. weather not requested)
        ok = bool(isinstance(r, dict) and r.get("ok"))
        status = "OK" if ok else "MISSING"
        statuses[key] = status
        detail = "" if ok else f" — {(r or {}).get('error') or 'no data'}"
        lines.append(f"{label} [{key}]: {status}{detail}")
    has_issues = any(s != "OK" for s in statuses.values())
    return {"has_issues": has_issues, "statuses": statuses,
            "report": "\n".join(lines) or "(no live sources this turn)"}


def run(report_text: str) -> Optional[SelfHealResult]:
    """Run the data-quality agent on a report string. Returns None on failure
    (caller then proceeds without a healing warning — fail-open)."""
    try:
        resp = agents.client().messages.parse(
            model=config.REVIEW_MODEL,
            max_tokens=700,
            system=prompts.SELF_HEALING_SYSTEM,
            messages=[{"role": "user", "content": f"=== DATA QUALITY REPORT ===\n{report_text}"}],
            output_format=SelfHealResult,
        )
        return resp.parsed_output
    except Exception:
        return None
