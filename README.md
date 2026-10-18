# Rebooking Copilot

Reviews ticketed bookings (`fixtures/pnrs.json`) against a snapshot of available fares
(`fixtures/fares_feed.json`) and produces a structured recommendation per booking: rebook or not, to which
fare, why, how confident, and the estimated net saving.

> Status: skeleton. The recommendation pipeline is being built. See [DESIGN.md](DESIGN.md) once it exists.

## Run
Requires Python 3.14 and [uv](https://docs.astral.sh/uv/). `uv` fetches Python 3.14 if it's missing.
The install needs the network once; running needs no network and no API key.

```bash
uv sync
uv run rebooking-copilot
```

## Test
```bash
uv run pytest
```

## Output
_To be defined in the build: `recommendations.json` (validated against a JSON Schema) plus a summary table on stdout._

## What is stubbed
_Filled in as slices land._

## Design
See [DESIGN.md](DESIGN.md) and the architecture decision records in [docs/adr/](docs/adr/README.md).
