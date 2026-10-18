# Framing: the fixtures, the traps, and what our decisions imply

Produced in `/frame` from a scripted fact table and an independent analysis (business ambiguity and production
reality). The decisions referenced here are in [`decisions.md`](decisions.md); the architecture-level ones are in [`adr/`](adr/README.md).

## 1. Fact table (naive: before policy)
Snapshot `capturedAt` 2026-07-08T09:00:00Z. Offers are matched to bookings on origin, destination and departure date.
Fees = the existing ticket's change fee × passengers (D-18). Computed with a script from the fixtures.

| PNR | Pax | Paid (per pax / total) | Candidate offer | Differences vs booked | Gross Δ | Fees | Naive net |
|---|---|---|---|---|---|---|---|
| QX7T2A | 1 | 480.00 USD / 480.00 USD | OF-1001 300.00 USD (seats 5) | none | 180.00 | 100.00 | 80.00 USD |
| LM9P4C | 2 | 350.00 USD / 700.00 USD | OF-2001 320.00 USD (seats 9) | flight UA642→UA640; dep 13:30→13:10; arr 19:45→19:25; cabin ECONOMY→BASIC_ECONOMY; bags 1→0; fareBasis KUA14→NUA00BsC | 60.00 | 150.00 | −90.00 USD |
| RT5K8B | 1 | 2200.00 EUR / 2200.00 EUR | OF-3001 2100.00 USD (seats 2) | none, except the currency | n/a | n/a | not comparable without FX (EUR vs USD) |
| ZC3N1D | 1 | 640.00 USD / 640.00 USD | OF-4001 500.00 USD (seats 4) | refundable true→false; fareBasis YAVREF→OAVNR | 140.00 | 0.00 | 140.00 USD |
| HB6W9E | 1 | 260.00 USD / 260.00 USD | OF-5001 200.00 USD (seats 7) | none | 60.00 | 150.00 | −90.00 USD |
| HB6W9E | 1 | 260.00 USD / 260.00 USD | OF-5002 150.00 USD (seats 1) | flight AS612→F9310; carrier AS→F9; dep 06:45→21:20 (+875 min); arr 08-30 10:05→08-31 03:55; stops 0→1; cabin ECONOMY→BASIC_ECONOMY; bags 1→0 | 110.00 | 150.00 | −40.00 USD |

For every PNR, `pricePerPassenger × passengers == totalPaid`.

## 2. Traps
1. **Wrong fee basis** (HB6W9E/OF-5002). Using the *offer's* fee (0.00) instead of the ticket's (150.00) turns −40.00 into +110.00.
2. **Passenger multiplier** (LM9P4C). Forgetting × 2 on the fee gives −15.00 instead of −90.00. The decision doesn't flip, but the explanation would be wrong.
3. **Currency mismatch** (RT5K8B). At any rate above 0.9545 USD/EUR, a naive conversion makes the USD offer look cheaper. The two zero fees are in different currencies and must not be added together.
4. **Lost refundability shows up as the biggest saving** (ZC3N1D). +140.00, paid for by giving up a fully refundable fare.
5. **Downgrade on another flight** (LM9P4C/OF-2001). BASIC_ECONOMY, 0 bags, 20 minutes earlier.
6. **The decoy cheapest fare** (HB6W9E/OF-5002). Another carrier, an extra stop, a red-eye arriving the next day, no bag, 1 seat left.
   A non-refundable ticket usually can't be exchanged onto another carrier at all.
7. **Same flight, same fare, cheaper, still a loss** (HB6W9E/OF-5001). The fee is 250% of the gross difference.
8. **An obvious yes that hides the settlement form** (QX7T2A). The ticket is non-refundable, so the 80.00 may come back as travel credit, not cash.
9. **The clock.** Every fixture flight departed before today's date (2026-10-18). Reading the wall clock marks everything as
   departed or stale. The as-of time must be injected (D-18).
10. **Matching on date.** Arrivals can fall on the next day, and times carry no timezone. Match on `route.departureDate` against
    the date part of the segment's departure. Never compute durations across airports.

**The effect on D-07.** With the fixtures alone, the eligible set never holds two offers for the same booking, so the
LLM never really chooses between offers. Extra test cases under `tests/` cover that (D-18).

## 3. What each PNR probably probes (inference)
- **QX7T2A:** the happy path: subtract the fee, apply the threshold, and ask whether the saving is cash or credit.
- **LM9P4C:** stacked problems (× 2 passengers, basic economy, no bag, another flight). Does every reason code get reported?
- **RT5K8B:** the currency and point-of-sale rule on its own. Everything else matches.
- **ZC3N1D:** a positive saving bought with lost refundability. Where is the line between soft and hard, and does the human-review route work?
- **HB6W9E:** several candidates for one booking. The fee wipes out the same-flight saving, and the decoy hides the wrong-fee mistake.

## 4. Expected outcomes under the current decisions
This is a projection for checking that the policy is coherent. The golden tests in `/slice decision` are the source of truth.

| PNR | Tier per offer (ADR-0005) | Stub mode | Claude mode | Driving decisions |
|---|---|---|---|---|
| QX7T2A | OF-1001 clean; net 80 ≥ 25 | NEEDS_REVIEW: under `cash_only`, the residual of a non-refundable ticket counts as credit | the same, because the settlement gate is in code | D-10, D-13 |
| LM9P4C | OF-2001 ineligible (bags 1→0), and net −90 | DO_NOT_REBOOK, with every reason code | the same | D-11, D-13 |
| RT5K8B | OF-3001 clean apart from FX; needs ≥ 110 EUR, i.e. a stub rate ≥ 1.0048 USD/EUR after spread | REBOOK if the stub rate clears it; confidence lowered for FX use | the same | D-12, D-13, D-17 |
| ZC3N1D | OF-4001 review-level (lost refundability); net 140 ≥ 32 | NEEDS_REVIEW | may recommend REBOOK at MEDIUM at most, with the trade-off listed | D-11, D-16, D-18 |
| HB6W9E | OF-5001 below threshold (−90); OF-5002 ineligible (bags, +875 min, next-day arrival) | DO_NOT_REBOOK | the same | D-11, D-13, D-14 |

## 5. Production gaps (for DESIGN.md §5–§7; not built)
- **Stale snapshot:** re-price and re-validate right before any action. Snapshot age lowers confidence, and recommendations expire.
- **Seat contention:** `seatsAvailable` is a snapshot (OF-5002 has 1). A batch run needs to allocate seats per offer, or hold them.
- **Exchange mechanics:** there's no validating carrier, ticket number or fare components in the data. Moving to another
  carrier means cancelling and buying new. A refundable ticket should be replaced by buying the new one first and refunding the old one second.
- **Point of sale and currency:** there's no point-of-sale field. RT5K8B leaves London but was ticketed in EUR, and converting ignores the spread.
- **Taxes:** it's unclear whether `amount` is the base fare or the total including tax. A real reissue recomputes taxes.
- **Multi-segment trips:** every PNR has one segment. Round trips, connections, partial exchanges and airline schedule changes aren't modelled.
- **Fare rules as free text:** an LLM could extract them, but only with validation, and it never supplies the numbers.
- **Supplier limits and volume:** shopping calls count against look-to-book ratios. Rank PNRs by how soon they depart and how much they could save, cache results, and call the LLM only for the ambiguous ones.
- **Autonomy risk:** use idempotency keys, caps, a kill switch and a shadow period. PNRs are personal data, so the LLM provider needs approval (ADR-0002).
- **Observability:** the eligible share, the REBOOK and review rates, estimated vs re-priced saving, how often humans overturn
  a recommendation, the LLM fallback rate, stub/LLM agreement, the spread of reason codes, cost per PNR.

## 6. Assumptions
| Assumption | Why | Alternative | Impact if wrong | Ref |
|---|---|---|---|---|
| A refundable ticket refunds cash; a non-refundable one issues credit | No fixture field says so; common practice | Ask per carrier or fare rule | QX7T2A's outcome flips | D-10 |
| The fee is the existing ticket's change fee × passengers | The primer says "what it costs to *change* an existing ticket" | The offer's fee | HB6W9E/OF-5002 −40 ↔ +110 (blocked anyway on bags) | D-18 |
| Prices are the full ticket amounts (no separate taxes) | No tax fields in the fixtures | Base fare plus taxes | Savings are overstated if taxes differ | — |
| Stub FX rates are illustrative | No FX source was supplied | A client-provided rate | RT5K8B's outcome depends on the rate | D-12 |
| The saving goes to the payer | The usual TMC framing | The traveler | Changes who is affected by trade-offs | client Q2 |

## 7. Conflicts and decisions that went against the recommendation
- **FX:** the setup recommended re-shopping in the ticket's currency (point of sale). The user chose a stubbed FX table, so the point-of-sale constraint goes to the assessors (Q4).
- **Hard blocks:** the setup recommended four. The user chose only "fewer bags", so downgrades, refundability and carrier changes are review-level, judged by the LLM with confidence capped at MEDIUM.
- **Saving definition:** the setup recommended a fixed cash-only rule. The user asked for it to be selectable (config), with cash-only as the default.
