# ADR-0006: Money model: settlement form, FX and fee basis
- **Status:** Accepted (parts provisional until the open questions are answered) · **Date:** 2026-10-18 · **Decided by:** user, plus defaults · **Log:** D-10, D-12, D-13, D-18

## Context
A cheaper fare is only a saving if the money actually comes back, in a currency that can be compared, after the right
fees. The fixtures don't say how a fare difference is returned. RT5K8B was paid in EUR but is offered in USD. The two
change fees per booking (the ticket's and the offer's) can flip a result: HB6W9E / OF-5002 is −40 with the ticket's
fee and +110 with the offer's.

## Decision
- **Fee basis** (D-18, default, provisional): net = (paid per passenger − offer per passenger) × passengers − *existing
  ticket's* `changeFeePerPassenger` × passengers. The offer's fee only matters for a later change.
- **Settlement form** (D-10, configurable): `settlementPolicy = cash_only | credit_face_value | credit_discounted(f)`.
  The default is `cash_only`. Assumption (provisional): a refundable ticket returns the residual as cash and a
  non-refundable one as travel credit. A saving that would come back as credit isn't counted under `cash_only`; it's
  reported separately, and the case goes to NEEDS_REVIEW.
- **FX** (D-12): an injected `FxProvider`, stubbed with a timestamped static rate table plus a spread margin. The rate,
  its source and its as-of time are recorded in the output. Amounts are compared in the ticket's currency, and code never mixes currencies.
  *Refined by D-27 and D-35:* the provider is API-shaped (`quote(from, to, as_of)`), and the mock returns one executable
  rate with the spread already included (USD→EUR 0.9276, `mock-fx-v1`), so there is no separate spread margin.
  Every quote is validated before use.
- **Threshold** (D-13): net ≥ max(25, 5% of total paid), in the ticket's currency, configurable and versioned with the policy.
- **Clock** (D-18): the as-of time is injected and defaults to the snapshot's `capturedAt`. It's never the wall clock.

## Depends on (team & context)
- **Ticketing and settlement practice:** whether the agency's GDS and airline contracts refund cash or issue credit,
  and whether the business values credit (expiry, use rates).
- **Point of sale:** an exchange is normally priced in the original ticket's currency and point of sale. Whether
  this agency can sell or exchange into a fare quoted in another currency (RT5K8B) is a business and contractual question.
- **Treasury policy:** which FX source and spread finance accepts.
- **Who gets the saving** (traveler or paying client), and what a human review costs, which sets the threshold.

## Consequences
- With the defaults, QX7T2A (non-refundable, net 80) becomes NEEDS_REVIEW, with the residual reported as credit.
  ZC3N1D's residual is cash.
- RT5K8B's outcome depends on the stub rate. It clears the 110 EUR threshold only at an executable rate (spread
  included, D-27) of at most 0.9952 EUR per 1 USD, i.e. at least 1.0048 USD per 1 EUR; break-even is 1.0476 EUR per
  1 USD (0.9545 USD per 1 EUR). The mock's 0.9276 EUR per 1 USD (≈ 1.078 USD per 1 EUR) clears it. The stub rates are
  labelled illustrative.
- Every number in the output can be recomputed from fields in the same output.

## Alternatives considered
- **Credit at face value, or at a discount:** available as config values.
- **Abstain, or re-shop in the ticket's currency, instead of converting:** the safer reading of point of sale.
  It stays the production recommendation in DESIGN.md if the assessors confirm the constraint.
- **The offer's fee as the fee basis:** rejected as a default, because it overstates savings.

## Revisit when
The assessors answer the settlement, fee-basis and point-of-sale questions, or a real FX source is wired in.

## Clarification (2026-10-18, D-30)
"Isn't counted" under `cash_only` means the credit saving is *reported* (estimated saving, settlement CREDIT, reason
SAVING_AS_CREDIT) but can never become REBOOK. The action is NEEDS_REVIEW. No decision changed.
