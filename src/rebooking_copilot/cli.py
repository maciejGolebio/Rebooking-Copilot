"""Command-line entrypoint: load and validate the fixtures, then print one recommendation per booking (stub mode)."""

import argparse
import sys
from pathlib import Path

from rebooking_copilot.decision import Recommendation, evaluate
from rebooking_copilot.loader import LoaderError, load_fare_snapshot, load_pnrs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rebooking-copilot", description=__doc__)
    parser.add_argument("--pnrs", type=Path, default=Path("fixtures/pnrs.json"), help="ticketed bookings")
    parser.add_argument("--fares", type=Path, default=Path("fixtures/fares_feed.json"), help="fare snapshot")
    args = parser.parse_args(argv)

    try:
        bookings = load_pnrs(args.pnrs)
        snapshot = load_fare_snapshot(args.fares)
    except LoaderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"Loaded {len(bookings.pnrs)} bookings ({len(bookings.rejected)} rejected) and "
        f"{len(snapshot.offers)} offers ({len(snapshot.rejected)} rejected); snapshot {snapshot.captured_at.isoformat()}."
    )
    for rej in bookings.rejected:
        print(f"  rejected booking #{rej.index} {rej.pnr or '?'}: " + "; ".join(f"{i.code}: {i.detail}" for i in rej.issues))
    for rej in snapshot.rejected:
        print(f"  rejected offer #{rej.index} {rej.offer_id or '?'}: " + "; ".join(f"{i.code}: {i.detail}" for i in rej.issues))
    print()
    print_table(evaluate(bookings, snapshot))
    print("\n(stub reasoner; recommendations.json and rationales arrive with /slice reasoner)")
    return 0


def print_table(recommendations: tuple[Recommendation, ...]) -> None:
    header = f"{'PNR':<8} {'ACTION':<14} {'OFFER':<8} {'NET SAVING':>14}  {'CONFIDENCE':<10}  REASONS"
    print(header)
    print("-" * len(header))
    for r in recommendations:
        saving = str(r.estimated_net_saving) if r.estimated_net_saving is not None else "-"
        print(f"{r.pnr or '?':<8} {r.action:<14} {r.chosen_offer_id or '-':<8} {saving:>14}  {r.confidence:<10}  {', '.join(r.reasons) or '-'}")


if __name__ == "__main__":
    raise SystemExit(main())
