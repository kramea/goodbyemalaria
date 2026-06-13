"""Interactive local CLI — talk to MalarIA without WhatsApp.

    python cli.py                       # interactive REPL (one phone session)
    python cli.py --phone +258...       # set the phone (session) id
    python cli.py "message here"        # one-shot
    python cli.py --trace               # print the agent trace each turn
"""

import argparse
import sys

from malaria import memory
from malaria.orchestrator import run_pipeline
from malaria.service import handle_message


def _print_trace(result):
    print("\n  ── agent trace ──")
    for r in result.rounds:
        print(f"  round {r.round}: adversarial={r.adversarial_verdict[:60]!r} "
              f"score={r.verifier_score}/8 passed={r.verifier_passed} failed={r.verifier_failed}")
        if r.verifier_fix:
            print(f"           fix={r.verifier_fix[:80]!r}")
    print(f"  final: approved={result.approved} best_score={result.best_score}/8\n")


def run_once(phone: str, message: str, trace: bool, force_loop: bool = False) -> None:
    if force_loop:
        # Demo: force a weak first draft so the self-correction loop fires.
        session = memory.load(phone)
        ctx = memory.context_for_navigator(session)
        result = run_pipeline(message, session_context=ctx, demo_force_weak=True)
        memory.record_turn(session, message, result.final_text, result.approved, result.best_score)
        memory.save(phone, session)
    else:
        result = handle_message(phone, message)
    print("\n" + result.final_text + "\n")
    if trace or force_loop:
        _print_trace(result)


def main() -> None:
    ap = argparse.ArgumentParser(description="MalarIA local CLI")
    ap.add_argument("message", nargs="*", help="message to send (omit for interactive)")
    ap.add_argument("--phone", default="cli:+10000000000", help="phone/session id")
    ap.add_argument("--trace", action="store_true", help="print agent trace")
    ap.add_argument("--force-loop", action="store_true",
                    help="demo: force a weak first draft so the self-correction loop fires")
    args = ap.parse_args()

    if args.message:
        run_once(args.phone, " ".join(args.message), args.trace, args.force_loop)
        return

    print("MalarIA — type a field-worker message (Ctrl-D / 'quit' to exit). "
          f"Session: {args.phone}")
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line.lower() in {"quit", "exit"}:
            break
        if not line:
            continue
        run_once(args.phone, line, args.trace, args.force_loop)


if __name__ == "__main__":
    sys.exit(main())
