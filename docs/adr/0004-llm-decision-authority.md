# ADR-0004: LLM decision authority: the LLM decides within code guardrails
- **Status:** Accepted · **Date:** 2026-10-18 · **Decided by:** user · **Log:** D-07 (supersedes D-00a)

## Context
The pre-set rule D-00a let the LLM only explain or escalate. That is safe, but it makes the model decorative, and
the brief asks for an *AI agent*. Money safety still requires that no number and no hard constraint ever comes from the model.

## Decision
| Owner | Responsibility |
|---|---|
| **Code** | parse and validate input · match candidate offers · compute every number (gross, fees, net, per passenger and total) · apply hard constraints and the threshold · build the **eligible set**, with code-computed facts for each offer |
| **LLM** (Claude mode) | choose among the eligible offers (or none) · judge the soft trade-offs the policy leaves open · return REBOOK / DO_NOT_REBOOK / NEEDS_REVIEW with a rationale |
| **Code, again** | re-validate the LLM's answer: schema-valid · the chosen offer is in the eligible set · the rationale contains no number missing from the facts. Anything else falls back to the deterministic decision, and the fallback reason is recorded |

In stub mode, a deterministic policy fills the LLM's role, using the tie-break and soft-trade-off rules decided in `/frame`.

**Invariant:** REBOOK ⇒ the chosen offer is in the code-built eligible set, whatever the reasoner returns.

## Depends on (team & context)
- **Risk appetite and accountability:** who answers for an LLM-approved change (compliance, the agency's client contracts).
- **Autonomy level** (`/frame`): with human approval, an LLM "REBOOK" stays a recommendation. Autonomous execution
  would need stronger evidence first.
- **Eval maturity:** an offline eval set and shadow mode before LLM approvals are trusted at volume.
- **Cost and latency budget**, since the model is now on the decision path for ambiguous cases.

## Consequences
- The model has a real decision role, so this is genuinely an agent. Money safety is enforced by the eligible set and re-validation.
- More tests: contract tests with adversarial fake-LLM outputs (an ineligible offer id, invented numbers, an invalid
  schema, a timeout) must all end in a valid deterministic fallback.
- Decisions can differ between stub and Claude mode. Output records the reasoner, the prompt version and any fallback.
  The metrics to watch are agreement with the stub and the rate at which humans overturn decisions.

## Alternatives considered
- **LLM picks the offer only:** code keeps the rebook / don't-rebook call. Safer, with a smaller role for the model.
- **Decide later in `/design-doc`:** defers the decision.
- **LLM makes the full call:** rejected. A hallucinated or unjustified approval could reach the output, and it's harder to test.

## Revisit when
Evals show the LLM's approvals are often overturned (tighten its role), or are reliably right (consider an auto-execute tier).
