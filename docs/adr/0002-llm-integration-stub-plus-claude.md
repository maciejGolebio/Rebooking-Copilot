# ADR-0002: LLM integration: deterministic stub by default, optional Claude
- **Status:** Accepted · **Date:** 2026-10-18 · **Decided by:** user · **Log:** D-02

## Context
The brief makes the model optional: no committed keys, and the program must run, or degrade cleanly, without one.
It scores the structure and the prompt(s), not whether a live model ran.

## Decision
A `Reasoner` interface with two implementations:
- a deterministic **stub**, the default;
- an optional **Claude** adapter, enabled when `ANTHROPIC_API_KEY` is set *and* LLM mode is selected explicitly.
  The exact switch is D-37 ([ADR-0009](0009-claude-mode-runtime.md)).

Both share one input and output schema. A missing key, a timeout, an API error or schema-invalid output all fall
back to the stub, and the output records the fallback reason. The prompt is a versioned file. The model's decision
authority is defined in ADR-0004.

## Depends on (team & context)
- **Provider approval and data protection:** PNRs contain personal data. Which LLM providers and regions are allowed,
  and under which data-processing terms.
- **Cost and latency budget** per booking at production volume.
- **The team's LLM-ops maturity:** evals, prompt versioning, monitoring of fallback and overturn rates.

## Consequences
- The offline, no-key run always works, and the default output is reproducible.
- There are two paths to test: the stub, and the adapter's contract tests against a fake client (no network in tests).
- Output records which reasoner produced each decision.

## Alternatives considered
- **Stub only:** least risk, but no live behaviour to show.
- **Real Claude as the main path:** more demo value, more moving parts, and it still needs the fallback.

## Revisit when
A provider is approved for production PNR data, or evals show the model adds no value over the deterministic policy.
