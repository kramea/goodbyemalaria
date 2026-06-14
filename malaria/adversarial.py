"""Adversarial review layer.

After the specialist drafts a reply, two reviewers challenge it IN PARALLEL:
  - Devil's Advocate (epidemiologist): resistance/timing/data/operational flaws.
  - Field Realism (ops manager): specificity, resources, skill, clarity.
An orchestrator then merges the draft + both verdicts into the final reply.

All three reuse agents.client()/agents._create. Everything is fail-open: if a
reviewer errors, we treat it as "no challenge"; if the orchestrator errors, we
send the original draft. The review never blocks a reply from going out.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from . import agents, config, prompts


class DevilVerdict(BaseModel):
    challenge_severity: str = Field(description='"critical" | "moderate" | "minor" | "none"')
    challenge_type: Optional[str] = None
    challenge_detail: str = ""
    suggested_correction: Optional[str] = None


class RealismVerdict(BaseModel):
    feasibility: str = Field(description='"executable" | "needs_clarification" | "not_executable"')
    missing_elements: List[str] = Field(default_factory=list)
    resource_flag: Optional[str] = None
    skill_escalation: Optional[str] = None
    clarity_flag: Optional[str] = None
    suggested_addition: Optional[str] = None


def _review_block(draft: str, brief: str) -> str:
    return (f"=== SPECIALIST RECOMMENDATION (draft) ===\n{draft}\n\n"
            f"=== SITUATION DATA ===\n{brief}")


def devils_advocate(draft: str, brief: str) -> Optional[DevilVerdict]:
    try:
        resp = agents.client().messages.parse(
            model=config.REVIEW_MODEL, max_tokens=600,
            system=prompts.DEVILS_ADVOCATE_SYSTEM,
            messages=[{"role": "user", "content": _review_block(draft, brief)}],
            output_format=DevilVerdict,
        )
        return resp.parsed_output
    except Exception:
        return None


def field_realism(draft: str, brief: str) -> Optional[RealismVerdict]:
    try:
        resp = agents.client().messages.parse(
            model=config.REVIEW_MODEL, max_tokens=600,
            system=prompts.FIELD_REALISM_SYSTEM,
            messages=[{"role": "user", "content": _review_block(draft, brief)}],
            output_format=RealismVerdict,
        )
        return resp.parsed_output
    except Exception:
        return None


def _is_clean(devil: Optional[DevilVerdict], realism: Optional[RealismVerdict]) -> bool:
    """True when neither reviewer wants a change — we can send the draft as-is."""
    devil_ok = (devil is None) or (devil.challenge_severity in ("none", "minor"))
    realism_ok = (realism is None) or (realism.feasibility == "executable")
    return devil_ok and realism_ok


def orchestrate(draft: str, devil: Optional[DevilVerdict],
                realism: Optional[RealismVerdict], language: str = "") -> str:
    """Merge the draft + verdicts into the final reply. Fail-open to the draft."""
    if _is_clean(devil, realism):
        return draft  # nothing to change — skip the extra LLM call
    try:
        d = devil.model_dump_json() if devil else "{}"
        r = realism.model_dump_json() if realism else "{}"
        user = (f"WORKER LANGUAGE: {language or 'the language of the draft'}\n\n"
                f"=== SPECIALIST REPLY (draft) ===\n{draft}\n\n"
                f"=== DEVIL'S ADVOCATE CHALLENGE ===\n{d}\n\n"
                f"=== FIELD REALISM CHECK ===\n{r}")
        resp = agents._create(
            model=config.REVIEW_MODEL, max_tokens=900,
            system=prompts.ORCHESTRATOR_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        out = agents._text(resp).strip()
        return out or draft
    except Exception:
        return draft


def review(draft: str, brief: str, language: str = "") -> Tuple[str, Optional[DevilVerdict], Optional[RealismVerdict]]:
    """Run both reviewers in parallel, then orchestrate. Returns
    (final_reply, devil_verdict, realism_verdict) — verdicts exposed for DEMO_MODE."""
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_devil = ex.submit(devils_advocate, draft, brief)
        f_realism = ex.submit(field_realism, draft, brief)
        devil = f_devil.result()
        realism = f_realism.result()
    final = orchestrate(draft, devil, realism, language)
    return final, devil, realism
