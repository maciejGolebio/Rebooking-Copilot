"""Command-line entrypoint. Skeleton only: loads the fixtures; the pipeline arrives with /slice."""

import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rebooking-copilot", description=__doc__)
    parser.add_argument("--pnrs", type=Path, default=Path("fixtures/pnrs.json"), help="ticketed bookings")
    parser.add_argument("--fares", type=Path, default=Path("fixtures/fares_feed.json"), help="fare snapshot")
    args = parser.parse_args(argv)

    pnrs = load_json(args.pnrs)["pnrs"]
    offers = load_json(args.fares)["offers"]
    print(f"Loaded {len(pnrs)} bookings and {len(offers)} offers. Recommendations: not implemented yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
