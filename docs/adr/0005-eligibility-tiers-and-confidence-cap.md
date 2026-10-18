# ADR-0005: Eligibility tiers and a confidence cap for LLM approvals
- **Status:** Accepted (amends ADR-0004) · **Date:** 2026-10-18 · **Decided by:** user · **Log:** D-11, D-14, D-16, D-17, D-18 (stub default)

## Context
ADR-0004 lets the LLM decide inside a code-built eligible set. Framing then had to define what "eligible" means
and how far the LLM's approval reaches. The fixtures contain every kind of difference: a cabin downgrade with no
bag (LM9P4C), lost refundability (ZC3N1D), a carrier change with an extra stop and a next-day arrival (HB6W9E /
OF-5002), and a 20-minute schedule shift (LM9P4C).

## Decision
Code sorts every candidate offer into one of three tiers:

| Tier | What puts an offer there | Possible outcome |
|---|---|---|
| **Ineligible** (hard block) | fewer included bags (D-11) · another flight departing more than ±60 min away, or arriving on a later day (D-14) · net saving below the threshold (D-13) · seats < passengers | never REBOOK |
| **Review-level** | cabin/product downgrade · lost refundability · carrier change · added stop · another flight within ±60 min (D-11, D-14) | **Claude mode:** the LLM may recommend REBOOK, with confidence capped at MEDIUM and the trade-offs listed (D-16). **Stub mode:** NEEDS_REVIEW (D-18, from D-00c) |
| **Review-level, never an LLM approval** | more than 60% cheaper than paid, a possible feed error (`PRICE_ANOMALY`; added by D-34, *refined by D-40*) | NEEDS_REVIEW in both modes: an agent REBOOK onto it falls back |
| **Clean** | the same flight and product with none of the above | REBOOK possible; only this tier can reach HIGH confidence |

Confidence is a LOW / MEDIUM / HIGH band computed from code signals: data completeness, margin above the threshold,
snapshot age, FX use, and the number of review-level differences. HIGH means "eligible for a future auto-execute tier".
The LLM can only lower confidence (D-17). Autonomy is recommend-only (D-09): a human approves every rebook.

## Depends on (team & context)
- **Client contracts and travel policy:** what counts as an acceptable downgrade differs by corporate client and
  traveler type. A real system needs per-client policy profiles, not one global list.
- **Risk appetite:** a team that has been burned by a bad exchange would make more differences hard blocks.
- **Operations capacity:** how many review cases human agents can handle sets how much may sit in the review tier.
- **Evidence:** the overturn rate on MEDIUM LLM approvals should drive whether the cap goes up or down.

## Consequences
- The LLM has a real job: weighing review-level trade-offs. Stub and Claude mode differ exactly there, which is easy
  to show and to measure.
- The fixtures rarely give the LLM two eligible offers to choose between. Extra cases go under `tests/` (D-18).
- Every outcome carries the tier, reason codes and the confidence drivers.

## Alternatives considered
- **All differences are hard blocks:** safest, but the LLM gets almost nothing to decide.
- **Review-level differences always go to NEEDS_REVIEW, LLM advisory only:** a smaller LLM role.
- **Uncapped LLM approval:** an LLM approval could reach HIGH and later the auto tier without enough evidence.

## Revisit when
Per-client policies arrive, or the overturn data for MEDIUM approvals comes in.
