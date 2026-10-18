# Rebooking Copilot: Design

> Status: draft · Policy version: v1 · Last updated: YYYY-MM-DD
>
> **TL;DR** (≤5 lines): what it does · the key LLM/deterministic boundary decision · the money-safety
> stance (abstain by default) · autonomy level · what is built vs. stubbed vs. only described.

## 1. Problem framing
- Our definition of a *genuinely beneficial and safe* rebooking (cite D-xx).
- What we deliberately left for the business to decide, and the defaults we chose meanwhile.
- Fixture walk-through: one line per PNR → outcome and the deciding reason (matches the README example output).

## 2. Approach & architecture
- Flow: input → validate/normalise → match candidates → hard constraints (policy vN) → money calc →
  decide / abstain → reasoner (stub | LLM) → output + audit record. (A diagram helps.)
- Components and their responsibilities: one table.
- Considered alternatives, and why we didn't pick them.

## 3. Where the LLM is, and isn't
| Step | Owner (code / LLM) | Why | Failure mode → guard |
|---|---|---|---|
- Prompt(s): file, version, inputs (precomputed FACTS only), output schema, validation, faithfulness check, fallback.
- Confidence: how it's computed, and why it isn't the model's self-report.

## 4. Correctness & money safety
- Money model: currency-tagged decimals, per-pax vs total, which fee applies, FX policy.
- Equivalence and hard constraints (versioned policy): a table of rule → hard or soft → rationale.
- How we avoid acting on a wrong or hallucinated saving: recompute, invariants, the LLM decides only inside the code-built eligible set and is re-validated, abstain.
- Before any action: re-price and re-validate, idempotency, secure new before releasing old, caps, kill switch.
- Tests: golden case per fixture PNR, plus the invariants.

## 5. Scale, cost & observability
- What breaks at large and growing volume, and the target architecture (incremental reshopping, prioritisation,
  caching, supplier rate limits, inventory contention).
- Cost model: a formula with stated inputs and 2–3 volume scenarios; the LLM runs only on the ambiguous subset.
- Observability: metrics (outcome mix, abstain rate, estimated vs. realised saving, fallback rate, cost per
  booking, latency), the audit trail, alerts, shadow mode, offline evals. How we'd know it isn't working.

## 6. Autonomy & human-in-the-loop
- Recommend vs. act today; what must be true before auto-executing a tier; rollback.

## 7. Assumptions & open questions
| # | Assumption / question | Our default | Impact if wrong | Business choice? | Ref |
|---|---|---|---|---|---|

## 8. What I deliberately did not do, and what's next
| Area | Built / Stubbed / Described | Note |
|---|---|---|
Next steps, in priority order, with what I'd do with more time.

## 9. AI usage note
Tools, and how they were driven (setup in `.claude/`, workflow phases). One suggestion I rejected or corrected, and why (from `docs/AI_USAGE_LOG.md`).

## 10. Architecture decision records
The architecture-significant decisions are in [`docs/adr/`](docs/adr/README.md). Each one has a **"Depends on (team & context)"**
section saying where a real team could reasonably decide differently.
| ADR | Decision | Depends on (one line) |
|---|---|---|
