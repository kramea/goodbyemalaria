"""Orchestration loop:

    navigator generates
      -> adversarial challenges; if CHALLENGE, navigator revises
      -> verifier scores; if score < threshold, navigator fixes
      -> repeat up to MAX_ROUNDS
      -> surface best output to the worker

Returns a PipelineResult carrying the final text plus a full trace so judges /
logs can see the agents actually disagreeing and self-correcting.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from . import agents, config


@dataclass
class RoundTrace:
    round: int
    recommendation: str
    adversarial_verdict: str
    verifier_score: int
    verifier_passed: List[int]
    verifier_failed: List[int]
    verifier_fix: str
    approved: bool


@dataclass
class PipelineResult:
    final_text: str
    approved: bool
    rounds: List[RoundTrace] = field(default_factory=list)
    best_score: int = 0


def run_pipeline(message: str, session_context: str = "", demo_force_weak: bool = False) -> PipelineResult:
    """Run the three-agent loop and return the best recommendation.

    demo_force_weak forces a weak first navigator draft so the challenge/score/
    fix loop visibly fires (demo only).
    """
    result = PipelineResult(final_text="", approved=False)

    recommendation = agents.navigator(
        message, session_context=session_context, weak_first_draft=demo_force_weak
    )
    best_text = recommendation
    best_score = -1

    for rnd in range(1, config.MAX_ROUNDS + 1):
        # 1) Adversarial review (fresh context).
        verdict = agents.adversarial(message, recommendation)
        challenged = verdict.strip().upper().startswith("CHALLENGE")

        # If challenged, let the navigator revise BEFORE scoring.
        if challenged:
            issue = verdict.split(":", 1)[1].strip() if ":" in verdict else verdict
            recommendation = agents.navigator(
                message,
                session_context=session_context,
                revision_note=f"A senior advisor challenged: {issue}",
                previous_output=recommendation,
            )

        # 2) Verifier scores (fresh context, structured).
        score = agents.verifier(message, recommendation)

        result.rounds.append(
            RoundTrace(
                round=rnd,
                recommendation=recommendation,
                adversarial_verdict=verdict.strip(),
                verifier_score=score.score,
                verifier_passed=score.passed,
                verifier_failed=score.failed,
                verifier_fix=score.fix_needed,
                approved=score.approved,
            )
        )

        # Track the best draft seen so far.
        if score.score > best_score:
            best_score = score.score
            best_text = recommendation

        if score.approved:
            result.final_text = recommendation
            result.approved = True
            result.best_score = score.score
            return result

        # 3) Not approved -> navigator fixes per the verifier instruction.
        if rnd < config.MAX_ROUNDS:
            fix = score.fix_needed or "Improve specificity, correct horizon, and language fidelity."
            # Adaptive escalation: if the fast model couldn't pass by the final
            # fix, hand the last attempt to the stronger (Opus) model.
            escalate = (rnd == config.MAX_ROUNDS - 1)
            recommendation = agents.navigator(
                message,
                session_context=session_context,
                revision_note=f"Rubric score {score.score}/8. Fix: {fix}",
                previous_output=recommendation,
                model=config.ESCALATION_MODEL if escalate else "",
            )

    # Exhausted rounds without hitting threshold: surface the best draft.
    result.final_text = best_text
    result.best_score = best_score
    result.approved = best_score >= config.RUBRIC_THRESHOLD
    return result
