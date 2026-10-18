---
name: money-safety
description: Engineering rules for code that computes money or decides whether to rebook. Covers the currency-safe Money type, fee math, FX policy, abstain semantics, invariants to test, audit trail, and execution safety. Load when writing or reviewing money, matching, eligibility, decision, confidence or output-contract code, or the DESIGN.md "Correctness & money safety" section.
user-invocable: false
---

# Money safety rules

Principle: **a wrong REBOOK is the expensive failure.** Every path that can produce REBOOK must be bounded by
deterministic checks: a code-built eligible set, code-computed numbers, re-validation (D-07), and a test. Uncertainty resolves to `NEEDS_REVIEW`.

## Representation
- Use Decimal (Python `decimal.Decimal`; TS: integer minor units in `bigint`/`number` ints, or a
  decimal lib), never binary floats. Parse JSON numbers as strings or Decimal at the boundary.
- `Money(amount, currency)` is an immutable value object. Arithmetic and comparison across currencies
  **raise**; they never coerce.
- Minor units come from ISO 4217 (USD/EUR 2, JPY 0). Don't assume 2 everywhere. Round only at
  presentation or settlement boundaries, with an explicit mode, and document it.
- Keep per-passenger and total amounts as distinct, named fields. If `price × pax ≠ totalPaid`, raise a data-quality flag.

## FX
- Convert only through an injected `FxProvider` that returns (rate, source, as-of). The prototype
  may stub it, but the stub's behaviour must be a recorded decision (e.g. "no rate → NEEDS_REVIEW").
- Never hard-code a rate inside decision logic. Never let an LLM supply one.
- A currency mismatch is often a point-of-sale problem, not a conversion problem (see rebooking-domain). The policy
  for it, whether abstain, not comparable, or re-shop in the ticket's currency, is a recorded decision. Don't assume one.

## Decision states
`REBOOK` · `DO_NOT_REBOOK` · `NEEDS_REVIEW`. Every result carries machine-readable reason codes
(e.g. `NET_SAVING_BELOW_THRESHOLD`, `CABIN_DOWNGRADE`, `REFUNDABILITY_LOST`, `CURRENCY_MISMATCH_NO_FX`,
`INSUFFICIENT_SEATS`, `DATA_INCONSISTENT`) plus a short human explanation.

## Invariants (turn each into a test: golden per fixture PNR, plus property tests where the stack has them)
1. `estimatedNetSaving` is recomputable from fields in the same output (gross, fees, pax).
2. REBOOK ⇒ the chosen offer is in the code-built eligible set: every hard constraint passes ∧ same currency (or a
   sourced FX rate) ∧ seats ≥ pax ∧ net saving ≥ threshold ∧ the input data is consistent.
3. Any failing hard constraint ⇒ never REBOOK.
4. Monotonicity: raising the offer price or a fee never moves a decision *toward* REBOOK (neither DO_NOT_REBOOK nor
   NEEDS_REVIEW may become REBOOK), and never increases the saving.
5. Determinism (stub mode, D-23): same input + policy version ⇒ identical output. Inject the clock and sort outputs and
   candidates stably. Claude mode is not asserted deterministic; it records the model, prompt version and tool trace.
6. Reasoner bounds (D-07): for *any* reasoner output, adversarial ones included, REBOOK happens only for an offer
   in the eligible set; output numbers equal the code-computed ones; invalid output, an ineligible offer id, invented
   numbers or a timeout lead to the deterministic fallback, with the reason recorded.
7. Exactly one recommendation per input PNR, including malformed ones (they get NEEDS_REVIEW, not a crash).

## Confidence
Derive it from deterministic signals first: data completeness, margin above threshold, number of
soft trade-offs, snapshot age, currency/FX certainty. An LLM's self-reported confidence can only lower it.
Document the scale and what each band means operationally (e.g. HIGH means eligible for future auto-execution).

## Audit trail (per recommendation)
Inputs (PNR id, offer id, captured-at), policy version, rule trace (each rule: pass/fail/value),
computed breakdown, reasoner id (stub|model id), prompt version, and the output schema version.

## Execution safety (usually *described*, not built, in the prototype)
Two-phase: recommend → (human or policy) approve → re-price and re-validate at execution time → execute.
Use idempotency keys per (PNR, offer, attempt), a secure-new-before-release-old ordering, per-run and
per-day caps, a kill switch, and shadow mode before any autonomy.
