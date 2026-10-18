# ADR-0009: Claude-mode runtime: Sonnet 5.5, explicit LangChain loop, validator
- **Status:** Accepted (refines ADR-0007 and ADR-0008) · **Date:** 2026-10-18 · **Decided by:** user, plus defaults · **Log:** D-36, D-37, D-38, D-39, D-40, D-41

## Context
ADR-0007 chose an agent over deterministic tools and ADR-0008 chose LangChain. Building the reasoner meant settling the
model, the effort, the switch and the shape of the loop. The current Claude API (checked against the API reference
on 2026-10-18) shapes the answer:
- Claude Sonnet 5.5 rejects forced `tool_choice` (`any` or `tool`) and non-default sampling parameters.
- Thinking can't be switched off; effort is the control, and Sonnet 5.5's default is `high`.
- The Anthropic guidance is to call Claude through the official SDK. `langchain-anthropic` wraps that SDK.

## Decision
- **Model and effort** (D-36): `claude-sonnet-5-5` at `output_config.effort = "medium"`, set explicitly. Adaptive
  thinking is left on (it is the default). The server-side refusal fallback is on by default
  (`server-side-fallback-2026-07-01`, `fallbacks: "default"`). If the whole chain refuses, the validator falls back to
  the deterministic decision.
- **Switch** (D-37): `--reasoner claude` or `REBOOKING_REASONER=claude`; the flag wins. Credentials: `ANTHROPIC_API_KEY`
  only. `ChatAnthropic` passes the key explicitly (an empty string when unset), so `ant auth` profiles aren't read (D-41).
  If Claude mode can't run (missing extra or key), every routed booking falls back, and the CLI says so.
- **Loop** (D-38): an explicit loop on LangChain primitives: `ChatAnthropic.bind_tools(TOOLS, tool_choice="auto", strict=True)`.
  - Five strict tools: four read-only, id-only lookups, plus `submit_recommendation`, which has no numeric fields.
  - The loop is append-only, so thinking blocks are passed back as returned.
  - Its budget is 6 turns and 30 s; a call starts only if its 10 s timeout still fits, and SDK retries are off.
  - A text-only reply gets one reminder. A missing submission, a refusal (its category recorded), `max_tokens`, an
    API error or invalid output → fallback.
  - LangChain stores the refusal-fallback block as `from_`; it is resent as `from`, which the API expects. The model
    that actually served is recorded as the reasoner (D-41).
  - Prompt caching is requested with top-level `cache_control`.
  - Only `langchain-anthropic` (and `langchain-core`) are needed. The `langchain` meta-package is not.
- **Validator** (D-39):
  - The agent works on the booking's seat-feasible eligible set after the ledger.
  - It accepts a submission only if the offer is in that set, REBOOK passes the settlement gate, the offer isn't a
    `PRICE_ANOMALY` (D-40), and every amount in the rationale matches an (amount, currency) pair from this booking's
    facts (D-41). The check can't catch a real amount attributed to the wrong thing, so the code's own summary comes first.
  - Confidence: a review-level REBOOK is capped at MEDIUM, and the agent's ceiling can only lower confidence.
  - Declining a clean saving escalates to NEEDS_REVIEW (D-22).
  - A REBOOK onto another offer moves the seat for later bookings, and a seat it frees is re-offered to bookings the
    agent didn't decide (D-41).
  - A declined credit saving stays visible as NEEDS_REVIEW, and every non-REBOOK carries a reason (D-41).
- **Prompt:** `src/rebooking_copilot/prompts/rebooking_agent_v2.md` (v1 kept), versioned and hashed into the fingerprint.
  FACTS are delimited, `<` and `>` are escaped, and offer ids follow a strict pattern, so data can't close the block.

## Depends on (team & context)
- **Cost and quality trade-off:** Sonnet 5.5 is about half Opus 5.5's price. A team with a measured quality gap on hard
  trade-offs, or a different budget, may pick another model. The choice is one constant plus an eval.
- **Framework familiarity:** a team comfortable with LangChain's agent runtime (`create_agent`) might prefer it. A team
  that wants the fewest dependencies might use the SDK's Tool Runner (the documented alternative).
- **Credential and data policy:** which credential sources are allowed in CI and production, and whether the refusal
  fallback model is approved for PNR data.
- **Latency budget:** 6 turns and 30 s per routed booking. Interactive use needs tighter limits; batch sweeps could use the Batches API.

## Consequences
- With the fixtures, only ZC3N1D is routed (D-21). Multi-offer and seat cases are covered by scripted fake-agent tests.
- Every Claude-mode recommendation records the reasoner (`claude:<serving model>`), the prompt version, the tool
  trace, a per-call log and any fallback reason. Stub-mode determinism is unchanged (D-23).
- No test calls the network. The real `ChatAnthropic` runs offline against canned API responses
  (`tests/test_review2_regressions.py`): request shape, thinking replay, refusal, `max_tokens`, the fallback block.

## Alternatives considered
- **Claude Opus 5.5:** the API reference's default, with the strongest judgement, at twice the price.
- **LangChain `create_agent`:** less code, but it would need checking that it never forces tool choice.
- **The Anthropic SDK Tool Runner:** the official helper. It would supersede D-20.

## Revisit when
An eval shows the model or effort level is wrong for the review-level cases, or LangChain churn costs more than the loop saves.
