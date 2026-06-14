"""Offline training pipeline for MalarIA (train/inference split).

Runs OFFLINE (e.g. a weekly cron) — NOT in the request path. For each
zone × urgency × resistance-profile it synthesises a realistic situation brief,
runs the specialist + the full adversarial loop, then distils the adversarially
validated decision into a compact "pre_reasoned" skeleton. At runtime the
specialist loads that skeleton and only ADAPTS it to live data — cutting a
~45s adversarial turn down to a ~10s adaptation.

Usage:
  python run_training.py                      # full matrix (slow; weekly cron)
  python run_training.py --zones gaza,zomba   # subset of zones
  python run_training.py --urgencies outbreak # subset of urgency states
  python run_training.py --quick              # 1 zone × 1 urgency × 1 resistance (smoke)

Output: knowledge/regions_pretrained.json  (a copy of regions.json with pre_reasoned filled)
"""

import argparse
import json
import sys
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from malaria import adversarial, agents, config, prompts

URGENCY_STATES = ["outbreak", "flood", "elevated", "normal", "dry"]
RESISTANCE_PROFILES = ["pyrethroid_confirmed", "pyrethroid_suspected", "none", "unknown"]

# Likely lead intervention per urgency — gives the specialist the right playbook.
_PLAYBOOK_FOR = {
    "outbreak": "emergency_irs", "flood": "larviciding", "elevated": "itn_distribution",
    "normal": "triage", "dry": "annual_irs",
}

_URGENCY_BRIEF = {
    "outbreak": "DHIS2 week-on-week cases +45% (rising fast); ReliefWeb flags an active outbreak alert.",
    "flood": "Active flooding; GloFAS river discharge above the 90th percentile; extensive new standing water.",
    "elevated": "Rainfall last 10 days ~2.5× the seasonal normal; breeding window open.",
    "normal": "Dry-season trough; transmission low and stable; no acute signals.",
    "dry": "Deep dry season; minimal breeding habitat; this is a planning window, not a response window.",
}


class Decision(BaseModel):
    priority_intervention: str = Field(description="the single lead intervention")
    product: str = Field(description="specific product/insecticide/net, or 'n/a'")
    fallback_intervention: str = Field(description="what to do if the primary is unavailable")
    contraindications: str = Field(description="what NOT to do here and why (e.g. resistance)")


def synth_brief(zone_key, rec, urgency, resistance):
    cs = (rec or {}).get("current_status") or {}
    res_text = {
        "pyrethroid_confirmed": "Confirmed pyrethroid resistance — pyrethroid-only tools are ineffective.",
        "pyrethroid_suspected": "Suspected pyrethroid resistance — treat pyrethroid-only tools as risky.",
        "none": "No significant insecticide resistance detected — standard tools work.",
        "unknown": "Resistance status unknown — assume risk and prefer resistance-robust tools.",
    }[resistance]
    return (
        f"=== SYNTHETIC TRAINING BRIEF — {zone_key.replace('_',' ').title()}, "
        f"{rec.get('country')} ===\n"
        f"Scenario urgency: {urgency.upper()}\n"
        f"{_URGENCY_BRIEF[urgency]}\n"
        f"Season: {rec.get('season','—')}\n"
        f"Vectors: {', '.join(rec.get('vectors', [])) or '—'}\n"
        f"Resistance: {res_text}\n"
        f"Last intervention: {rec.get('last_intervention','—')}\n"
        f"LLIN coverage: {rec.get('llin_coverage_pct','—')}%\n"
        f"Low-lying / flood-prone: {cs.get('headline','—')}\n"
        "=== END BRIEF ==="
    )


def distil(final_reply) -> Decision:
    """Extract the structured decision from the adversarially-validated reply."""
    resp = agents.client().messages.parse(
        model=config.REVIEW_MODEL, max_tokens=400,
        system=("Extract the core decision from this malaria field recommendation into "
                "the structured fields. Be concise; use the reply's own wording."),
        messages=[{"role": "user", "content": final_reply}],
        output_format=Decision,
    )
    return resp.parsed_output


def train_one(zone_key, rec, urgency, resistance):
    brief = synth_brief(zone_key, rec, urgency, resistance)
    playbook_key = _PLAYBOOK_FOR.get(urgency, "triage")
    playbook = prompts.PLAYBOOKS.get(playbook_key, prompts.PLAYBOOKS["triage"])
    draft = agents.specialist(
        f"What is the priority malaria intervention right now in {zone_key}?",
        playbook=playbook, data_block=brief, weather_summary="",
        session_context="", first_contact=False, language="English")
    final, devil, realism = adversarial.review(draft, brief, "English")
    decision = distil(final)
    passed = (devil is None) or (devil.challenge_severity in ("none", "minor"))
    return {
        "priority_intervention": decision.priority_intervention,
        "product": decision.product,
        "fallback_intervention": decision.fallback_intervention,
        "contraindications": decision.contraindications,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "adversarial_passed": bool(passed),
        "skeleton_reply": final,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zones", default="")
    ap.add_argument("--urgencies", default="")
    ap.add_argument("--resistances", default="")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    regions = json.loads(config.KNOWLEDGE_FILE.read_text())
    all_zones = list(regions["regions"].keys())

    zones = [z for z in (args.zones.split(",") if args.zones else all_zones) if z in regions["regions"]]
    urgencies = args.urgencies.split(",") if args.urgencies else list(URGENCY_STATES)
    resistances = args.resistances.split(",") if args.resistances else list(RESISTANCE_PROFILES)
    if args.quick:
        zones, urgencies, resistances = zones[:1], urgencies[:1], resistances[:1]

    total = len(zones) * len(urgencies) * len(resistances)
    print(f"Training {len(zones)} zones × {len(urgencies)} urgencies × "
          f"{len(resistances)} resistances = {total} combos\n")
    n = 0
    for zk in zones:
        rec = regions["regions"][zk]
        rec.setdefault("pre_reasoned", {})
        for urg in urgencies:
            for res in resistances:
                n += 1
                try:
                    entry = train_one(zk, rec, urg, res)
                    rec["pre_reasoned"].setdefault(urg, {})[res] = entry
                    flag = "✓" if entry["adversarial_passed"] else "⚠ (challenged)"
                    print(f"[{n}/{total}] {zk}/{urg}/{res}: "
                          f"{entry['priority_intervention'][:50]} {flag}")
                except Exception as e:
                    print(f"[{n}/{total}] {zk}/{urg}/{res}: FAILED — {e}")
                # Persist after each combo so a long run is resumable/safe.
                config.PRE_REASONED_FILE.write_text(
                    json.dumps(regions, indent=2, ensure_ascii=False) + "\n")

    print(f"\nTraining complete → {config.PRE_REASONED_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
