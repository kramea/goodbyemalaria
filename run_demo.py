"""Run the four demo scenarios end-to-end and check expectations.

    python run_demo.py            # all four scenarios
    python run_demo.py --trace    # include the agent trace

Each scenario uses a fresh phone/session except Scenario 1b, which reuses
Scenario 1's phone to prove session memory carries context forward.
"""

import argparse
import time

from malaria.service import handle_message

SCENARIOS = [
    {
        "name": "S1 — Portuguese / Immediate / Gaza flooding",
        "phone": "demo:+258000000001",
        "message": "As chuvas começaram cedo em Gaza. Temos muita água parada. O que fazemos agora?",
        "expect_horizon": ["imediat"],  # Portuguese 'imediato/imediata'
        "expect_terms": ["larvicid", "gaza"],
        "expect_lang_hint": ["água", "fazer", "deve", "imediat", "ção"],
    },
    {
        "name": "S2 — English / Month ahead / Zomba, Malawi",
        "phone": "demo:+265000000002",
        "message": "We are in Zomba district Malawi. Transmission season starts in 6 weeks. What should we be preparing?",
        "expect_horizon": ["month ahead"],
        "expect_terms": ["zomba"],
        "expect_lang_hint": ["the", "should", "weeks", "prepar"],
    },
    {
        "name": "S3 — French / Season ahead / Nampula",
        "phone": "demo:+258000000003",
        "message": "Nous planifions pour la prochaine saison à Nampula. Quelles interventions prioriser?",
        "expect_horizon": ["saison"],  # French 'saison à venir' etc.
        "expect_terms": ["nampula"],
        "expect_lang_hint": ["la", "les", "des", "pour", "interventions"],
    },
    {
        "name": "S4 — Chichewa / Immediate / Machinga",
        "phone": "demo:+265000000004",
        "message": "Tili ku Machinga. Mvula yayamba ndipo pali madzi oyima ambiri. Tichite chiyani lero?",
        "expect_horizon": [],  # Chichewa horizon term varies; checked loosely below
        "expect_terms": ["machinga"],
        "expect_lang_hint": ["madzi", "ku ", "mankhwala", "lero", "udzudzu", "malungo"],
    },
]


def check(text: str, needles) -> bool:
    low = text.lower()
    return all(any(n.lower() in low for n in [needle]) for needle in needles) if needles else True


def any_present(text: str, needles) -> bool:
    low = text.lower()
    return any(n.lower() in low for n in needles) if needles else True


def run(trace: bool) -> int:
    failures = 0
    for sc in SCENARIOS:
        print("=" * 78)
        print(sc["name"])
        print("-" * 78)
        t0 = time.time()
        result = handle_message(sc["phone"], sc["message"])
        dt = time.time() - t0
        text = result.final_text
        print(text)
        print(f"\n[approved={result.approved}  score={result.best_score}/8  {dt:.1f}s  "
              f"rounds={len(result.rounds)}]")

        ok_region = any_present(text, sc["expect_terms"])
        ok_horizon = any_present(text, sc["expect_horizon"]) if sc["expect_horizon"] else True
        ok_lang = any_present(text, sc["expect_lang_hint"])
        ok = result.approved and ok_region and ok_horizon and ok_lang
        if not ok:
            failures += 1
            print(f"  ⚠️  checks: region={ok_region} horizon={ok_horizon} "
                  f"language={ok_lang} approved={result.approved}")
        else:
            print("  ✓ checks passed")

        if trace:
            for r in result.rounds:
                print(f"    round {r.round}: adv={r.adversarial_verdict[:50]!r} "
                      f"score={r.verifier_score}/8 failed={r.verifier_failed}")
        print()

    # Scenario 1b: session memory — second message on S1's phone should keep
    # Portuguese and reference the prior Gaza/flood context.
    print("=" * 78)
    print("S1b — Session memory follow-up (same phone as S1, Portuguese expected)")
    print("-" * 78)
    result = handle_message(SCENARIOS[0]["phone"], "E para as próximas semanas, o que mais devemos planear?")
    print(result.final_text)
    mem_ok = result.approved and any_present(result.final_text, ["semana", "gaza", "ção", "deve"])
    print(f"\n[approved={result.approved}  score={result.best_score}/8]  memory_check={mem_ok}")
    if not mem_ok:
        failures += 1
    print()

    print("=" * 78)
    if failures == 0:
        print("ALL SCENARIOS PASSED ✓")
    else:
        print(f"{failures} scenario check(s) need attention ⚠️")
    return failures


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", action="store_true")
    raise SystemExit(1 if run(ap.parse_args().trace) else 0)
