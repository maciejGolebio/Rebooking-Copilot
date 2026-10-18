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

## Example output
_Added in /finalize from a real run._

## What is stubbed
- **FX rates:** a mock provider with one illustrative rate, USD→EUR 0.9276, labelled `mock-fx-v1`.
- **The fare snapshot:** a static file, never re-priced.
- **Production-only parts, described in DESIGN.md §5–§6 and not built:** execution and approval, scheduling, caching and shadow mode.

## Design
See [DESIGN.md](DESIGN.md) and the architecture decision records in [docs/adr/](docs/adr/README.md).
