"""Command-line entrypoint: load and validate the fixtures, recommend per booking, write recommendations.json.

Stub mode (default) is deterministic and needs no network or key. Claude mode (`--reasoner claude`, or
REBOOKING_REASONER=claude; the flag wins) needs langchain-anthropic and ANTHROPIC_API_KEY, calls a paid API, and
falls back to the stub per booking whenever the agent can't be used.
"""

import argparse
import os
import sys
from pathlib import Path

from rebooking_copilot.decision import Recommendation, evaluate
from rebooking_copilot.loader import LoaderError, load_fare_snapshot, load_pnrs
from rebooking_copilot.output import build_file, write_file
from rebooking_copilot.reasoning import UnavailableReasoner

REASONERS = ("stub", "claude")


def make_claude_reasoner():
    """Imported lazily so that stub mode never loads LangChain or the Anthropic SDK (ADR-0003)."""
    try:
        from rebooking_copilot.agent import make_claude_reasoner as make
    except ImportError as exc:
        return UnavailableReasoner(f"the 'llm' extra is not installed ({exc}); run `uv sync --extra llm`")
    return make()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rebooking-copilot", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pnrs", type=Path, default=Path("fixtures/pnrs.json"), help="ticketed bookings")
    parser.add_argument("--fares", type=Path, default=Path("fixtures/fares_feed.json"), help="fare snapshot")
    parser.add_argument("--out", type=Path, default=Path("out/recommendations.json"), help="where to write the JSON output")
    parser.add_argument("--reasoner", choices=REASONERS, default=None, help="stub (default) or claude; overrides REBOOKING_REASONER")
    args = parser.parse_args(argv)

    mode = args.reasoner or os.environ.get("REBOOKING_REASONER", "stub").strip().lower()
    if mode not in REASONERS:
        print(f"error: REBOOKING_REASONER must be one of {', '.join(REASONERS)}, got {mode!r}", file=sys.stderr)
        return 2

    try:
        bookings = load_pnrs(args.pnrs)
        snapshot = load_fare_snapshot(args.fares)
    except LoaderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    reasoner = make_claude_reasoner() if mode == "claude" else None
    if isinstance(reasoner, UnavailableReasoner):
        print(f"Claude mode unavailable ({reasoner.reason}); falling back to the deterministic stub for every booking.")

    print(
        f"Loaded {len(bookings.pnrs)} bookings ({len(bookings.rejected)} rejected) and "
        f"{len(snapshot.offers)} offers ({len(snapshot.rejected)} rejected); snapshot {snapshot.captured_at.isoformat()}."
    )
    for rej in bookings.rejected:
        print(f"  rejected booking #{rej.index} {rej.pnr or '?'}: " + "; ".join(f"{i.code}: {i.detail}" for i in rej.issues))
    for rej in snapshot.rejected:
        print(f"  rejected offer #{rej.index} {rej.offer_id or '?'}: " + "; ".join(f"{i.code}: {i.detail}" for i in rej.issues))

    recommendations = evaluate(bookings, snapshot, reasoner=reasoner)
    print()
    print_table(recommendations)
    print()
    print_rationales(recommendations)
    path = write_file(args.out, build_file(recommendations, snapshot, reasoner_id=reasoner.id if reasoner else "stub"))
    print(f"\nWrote {len(recommendations)} recommendations to {path}")
    return 0


def print_table(recommendations: tuple[Recommendation, ...]) -> None:
    header = f"{'PNR':<8} {'ACTION':<14} {'OFFER':<8} {'NET SAVING':>14}  {'CONFIDENCE':<10}  {'DECIDED BY':<24}  REASONS"
    print(header)
    print("-" * len(header))
    for r in recommendations:
        saving = str(r.estimated_net_saving) if r.estimated_net_saving is not None else "-"
        decided = r.reasoner + (" (fallback)" if r.fallback_reason else "")
        print(f"{r.pnr or '?':<8} {r.action:<14} {r.chosen_offer_id or '-':<8} {saving:>14}  {r.confidence:<10}  {decided:<24}  {', '.join(r.reasons) or '-'}")


def print_rationales(recommendations: tuple[Recommendation, ...]) -> None:
    print("Why:")
    for r in recommendations:
        print(f"  {r.pnr or '?'}: {r.rationale}")
        if r.fallback_reason:
            print(f"    fallback: {r.fallback_reason}")


if __name__ == "__main__":
    raise SystemExit(main())
