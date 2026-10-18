# Rebooking Copilot

Reviews ticketed bookings (`fixtures/pnrs.json`) against a snapshot of available fares
(`fixtures/fares_feed.json`) and produces a structured recommendation per booking: rebook or not, to which
fare, why, how confident, and the estimated net saving. See [DESIGN.md](DESIGN.md) for how and why.

## What to read
- **[DESIGN.md](DESIGN.md)** is the deliverable: the approach, the trade-offs, production concerns and the AI-usage note.
- **This README:** how to run it and what the output looks like.
- **Optional depth:** [docs/adr/](docs/adr/README.md) (one record per architecture decision) and
  [docs/decisions.md](docs/decisions.md) (every product and technical default, with who decided it).
- **Process evidence, not product:** [docs/AI_USAGE_LOG.md](docs/AI_USAGE_LOG.md), [docs/AI_SETUP.md](docs/AI_SETUP.md)
  and `.claude/` (the Claude Code agents, skills and hooks used to build this), plus [docs/framing.md](docs/framing.md)
  and the unsent questions draft [docs/questions-email.md](docs/questions-email.md).

## Run
Requires Python 3.14 and [uv](https://docs.astral.sh/uv/); `uv` fetches Python 3.14 if it's missing.
The install needs the network once. Running needs no network and no API key.

```bash
uv sync
uv run rebooking-copilot
```

This prints a table and a one-line rationale per booking, and writes `out/recommendations.json`.
Options: `--pnrs PATH`, `--fares PATH`, `--out PATH`, `--reasoner stub|claude`.

`uv sync` also installs the dev tools: pytest, hypothesis, and langchain-anthropic for the offline agent tests.
`uv sync --no-dev` installs only what stub mode needs (pydantic).

### Optional: Claude mode
An LLM agent decides the cases that need judgement: review-level trade-offs, or several eligible offers. It runs
inside guardrails, and every other booking stays deterministic. It needs `ANTHROPIC_API_KEY` in the environment
(LangChain's `ChatAnthropic` passes the key explicitly, so `ant auth` profiles aren't used) and **calls a paid API**.

```bash
uv sync --extra llm
uv run --extra llm rebooking-copilot --reasoner claude
```

`REBOOKING_REASONER=claude` works too; the flag wins. Without credentials, or if the agent's answer fails
validation, the booking falls back to the deterministic decision, and the output records why.

Without a key, the run still completes. The CLI says so up front, and the routed booking is marked as a fallback:

```text
Claude mode unavailable (ANTHROPIC_API_KEY is not set (LangChain's ChatAnthropic doesn't read `ant auth` profiles)); falling back to the deterministic stub for every booking.
ZC3N1D   NEEDS_REVIEW   OF-4001      140.00 USD  LOW         stub (fallback)           REFUNDABILITY_LOST
    fallback: claude unavailable: ANTHROPIC_API_KEY is not set (LangChain's ChatAnthropic doesn't read `ant auth` profiles)
```

## Test
```bash
uv run pytest
```
No test touches the network. The agent loop is tested with a scripted fake chat model, and the production
`ChatAnthropic` client is tested offline against canned API responses (request shape, thinking replay, refusals,
the refusal-fallback block).

## Output
`out/recommendations.json` uses camelCase keys and is validated against
[`schemas/recommendations.schema.json`](schemas/recommendations.schema.json) before it is written. Each recommendation has:
- the decision: `action` (`REBOOK` · `DO_NOT_REBOOK` · `NEEDS_REVIEW`), `chosenOfferId`, `estimatedNetSaving`, the full
  money `breakdown`, `confidence` (`LOW` · `MEDIUM` · `HIGH`), `reasons` (machine-readable codes), `rationale`, and `alternatives`;
- for audit: every candidate offer's tier and rule trace, `reasoner`, `promptVersion`, `fallbackReason`, `agentTrace`, `agentCalls`,
  `asOf` / `expiresAt` and a `fingerprint`.

Amounts are exact decimal strings, as computed (`1947.960000`); the table and the rationales round them for display.

## Example output
A real run of `uv run rebooking-copilot` from a fresh shell with no API key (stub mode), unedited:

```text
Loaded 5 bookings (0 rejected) and 6 offers (0 rejected); snapshot 2026-07-08T09:00:00+00:00.

PNR      ACTION         OFFER        NET SAVING  CONFIDENCE  DECIDED BY                REASONS
----------------------------------------------------------------------------------------------
QX7T2A   NEEDS_REVIEW   OF-1001       80.00 USD  LOW         stub                      SAVING_AS_CREDIT
LM9P4C   DO_NOT_REBOOK  -                     -  HIGH        stub                      FEWER_BAGS, NET_SAVING_BELOW_THRESHOLD, CABIN_DOWNGRADE, DIFFERENT_FLIGHT
RT5K8B   REBOOK         OF-3001      252.04 EUR  MEDIUM      stub                      FX_CONVERTED
ZC3N1D   NEEDS_REVIEW   OF-4001      140.00 USD  LOW         stub                      REFUNDABILITY_LOST
HB6W9E   DO_NOT_REBOOK  -                     -  HIGH        stub                      NET_SAVING_BELOW_THRESHOLD, FEWER_BAGS, SCHEDULE_OUTSIDE_WINDOW, ARRIVES_LATER_DAY, CABIN_DOWNGRADE, CARRIER_CHANGE, ADDED_STOP

Why:
  QX7T2A: OF-1001 is the same flight and product, 180.00 USD cheaper in total; after 100.00 USD in change fees the net saving is 80.00 USD. The ticket is non-refundable, so the difference would come back as travel credit, which the cash-only policy doesn't count as a saving. A human should decide.
  LM9P4C: No eligible offer. OF-2001: it includes fewer bags, the counted saving of -90.00 USD is below the 35.00 USD threshold, it is a lower cabin or fare product and it is a different flight.
  RT5K8B: Rebook to OF-3001: 1947.96 EUR per passenger instead of 2200.00 EUR (converted from 2100.00 USD at the USD→EUR rate 0.9276, source mock-fx-v1); after 0.00 EUR in change fees the net saving is 252.04 EUR, at or above the 110.00 EUR threshold; confidence MEDIUM.
  ZC3N1D: OF-4001 would save 140.00 USD net, but the new fare is not refundable. That trade-off needs a human decision.
  HB6W9E: No eligible offer. OF-5001: the counted saving of -90.00 USD is below the 25.00 USD threshold; OF-5002: it includes fewer bags, it departs too far from the booked time, it arrives a day later, the counted saving of -40.00 USD is below the 25.00 USD threshold, it is a lower cabin or fare product, it is on another carrier and it adds a stop.

Wrote 5 recommendations to out/recommendations.json
```

One record from `out/recommendations.json` (RT5K8B), trimmed by a script to the decision fields. Omitted:
`index`, `candidates` (each offer's tier, reasons, breakdown and its 13-step rule trace), `alternatives`, `dataIssues`,
`error`, `promptVersion`, `agentTrace` and `agentCalls`.

```json
{
  "pnr": "RT5K8B",
  "action": "REBOOK",
  "chosenOfferId": "OF-3001",
  "estimatedNetSaving": {
    "amount": "252.040000",
    "currency": "EUR"
  },
  "confidence": "MEDIUM",
  "reasons": [
    "FX_CONVERTED"
  ],
  "breakdown": {
    "passengers": 1,
    "paidPerPassenger": {
      "amount": "2200.00",
      "currency": "EUR"
    },
    "offerPricePerPassenger": {
      "amount": "2100.00",
      "currency": "USD"
    },
    "offerPricePerPassengerInTicketCurrency": {
      "amount": "1947.960000",
      "currency": "EUR"
    },
    "fx": {
      "fromCurrency": "USD",
      "toCurrency": "EUR",
      "rate": "0.9276",
      "asOf": "2026-07-08T09:00:00Z",
      "source": "mock-fx-v1"
    },
    "grossSaving": {
      "amount": "252.040000",
      "currency": "EUR"
    },
    "changeFees": {
      "amount": "0.00",
      "currency": "EUR"
    },
    "netSaving": {
      "amount": "252.040000",
      "currency": "EUR"
    },
    "settlement": "CASH",
    "countedNetSaving": {
      "amount": "252.040000",
      "currency": "EUR"
    },
    "threshold": {
      "amount": "110.0000",
      "currency": "EUR"
    }
  },
  "rationale": "Rebook to OF-3001: 1947.96 EUR per passenger instead of 2200.00 EUR (converted from 2100.00 USD at the USD→EUR rate 0.9276, source mock-fx-v1); after 0.00 EUR in change fees the net saving is 252.04 EUR, at or above the 110.00 EUR threshold; confidence MEDIUM.",
  "reasoner": "stub",
  "policyVersion": "v1",
  "asOf": "2026-07-08T09:00:00Z",
  "expiresAt": "2026-07-09T09:00:00Z",
  "fingerprint": "9fb479aecde2b6c8f9484dd48e8108678e3287a7708b46ecdaea9c68803af23e",
  "fallbackReason": null
}
```

## What is stubbed
- **FX rates:** a mock provider with one illustrative rate, USD→EUR 0.9276, labelled `mock-fx-v1`.
- **The fare snapshot:** a static file, never re-priced.
- **Production-only parts, described in DESIGN.md §5–§6 and not built:** execution and approval, scheduling, caching and shadow mode.

## Design
See [DESIGN.md](DESIGN.md) and the architecture decision records in [docs/adr/](docs/adr/README.md).
