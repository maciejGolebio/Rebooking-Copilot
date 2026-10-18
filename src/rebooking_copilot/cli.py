"""Command-line entrypoint: loads and validates the fixtures; recommendations arrive with /slice decision."""

import argparse
import sys
from pathlib import Path

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
    print("Recommendations: not implemented yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
