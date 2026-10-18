---
name: rebooking-domain
description: Travel reshopping domain knowledge for the Rebooking Copilot. Covers the fixture data contract, what "equivalent fare" can mean, fee and refund semantics, and a trap checklist for why a cheaper number is not always a saving. Load when analysing fixtures, matching offers to bookings, defining equivalence/eligibility policy, or writing DESIGN.md assumptions.
user-invocable: false
---

# Rebooking domain primer

The brief says airline trivia is not tested and everything needed is in the fixtures. Use this
file to *ask better questions* and to name real-world gaps in DESIGN.md. Don't build logic for
real-world rules the fixtures don't model unless a decision in `docs/decisions.md` says so.

## Glossary
- **PNR**: booking record (locator such as `QX7T2A`). It holds the itinerary (segments), passengers and the ticket.
- **Ticketed**: a ticket has been issued at a fare. Changing it is an *exchange/reissue*, or a *refund + new purchase*.
- **Fare basis**: code naming the fare product and its rules. The first letter is usually the booking class.
- **Cabin vs fare product**: `BASIC_ECONOMY` sits in the economy cabin but is a stripped product
  (typically no changes, no bag, no seat choice). Treat it as a different product from `ECONOMY`, not "the same seat cheaper".
- **Refundable**: the cancel value comes back as money. Non-refundable value is usually forfeited or kept as travel credit.
- **Change fee**: the penalty for changing *this* ticket. It is charged per passenger, on top of any fare difference.
- **Reshopping / price assurance**: re-pricing a ticketed booking to capture a later price drop.
- **TMC**: travel management company (corporate agency). It has travel policies, duty of care, and negotiated fares.

## Fixture data contract (verify against the files; don't trust this summary over them)
- `pnrs.json → pnrs[]`: `pnr`, `passengers`, `itinerary[]` (origin, destination, departure,
  arrival, carrier, flightNumber, stops, cabin, fareBasis), `ticket` (pricePerPassenger,
  totalPaid, cabin, refundable, changeFeePerPassenger, baggageIncludedPieces).
- `fares_feed.json`: `capturedAt` and `offers[]` (offerId, route{origin,destination,departureDate},
  carrier, flightNumber, departure, arrival, stops, cabin, fareBasis, price, refundable,
  changeFeePerPassenger, baggageIncludedPieces, seatsAvailable).
- File comments: offer prices are **per passenger**. PNR prices are per passenger "unless you
  decide otherwise (see totalPaid)". **Currency is not always USD.** Match offers by origin, destination and departure date.
- Times are local and carry no timezone offset. Comparing booked vs offered times at the *same* airport is safe;
  durations or cross-airport arithmetic need airport timezone data the fixtures don't provide.

## Equivalence: the dimensions (policy must decide each; record as D-xx)
| Dimension | Questions to settle |
|---|---|
| Route & date | Same O&D and same date only? Nearby airports? ± days? |
| Flight & schedule | Same flight only, or a window (± N min)? Earlier/later departure? Arrival next day / red-eye? |
| Stops | Is adding a stop ever acceptable? |
| Carrier | Same carrier only? See "exchange mechanics" below. |
| Cabin / fare product | Is a downgrade (e.g. ECONOMY → BASIC_ECONOMY) ever allowed? Upgrade at a lower price? |
| Refundability | Is losing refundability a hard block, or a priced trade-off that needs human approval? |
| Baggage | Is fewer included bags a hard block, or priced (bag fee × pax)? |
| Future flexibility | Does the new fare's change fee or rules matter for the traveler's *next* change? |
| Inventory | `seatsAvailable` ≥ passengers? Contention when several PNRs want the same offer? |

## Money semantics to make explicit
- Net saving = (paid per pax − new per pax) × pax − applicable fees. Decide **which** change fee
  applies (normally the *existing* ticket's fee to change it; the offer's fee only matters for later changes) and whether it is per pax.
- `pricePerPassenger × passengers` vs `totalPaid`: what if they disagree? Treat it as a data-quality flag, never silently pick one.
- Cross-currency comparison needs an FX source and timestamp. If none is available, the comparison is not computable, not zero.
- A currency mismatch usually means a different **point of sale**, not just a conversion. Exchanges and refunds are
  normally priced in the original ticket's currency and point of sale. A fare quoted in another currency may not be
  something this agency can sell or exchange into, and a converted "saving" ignores FX spread. Consider re-shopping
  in the ticket's currency and using FX only for prioritisation.
- Real world: for non-refundable tickets the fare difference is often returned as **credit, not
  cash**, or forfeited. Is a credit a "saving"? This is a business question, so surface it.
- Taxes and fees aren't in the fixtures, but real repricing includes them. Name the gap.

## Trap checklist (apply to every PNR, then cite the PNR ids)
1. Is a cheaper offer actually a **different product** (cabin, refundability, bags)?
2. Is it a **different flight** (number, time, stops, arrival day)?
3. Does the **change fee** wipe out the gross difference? Per pax × pax?
4. **Currency** mismatch between ticket and offer?
5. **Multi-passenger**: are seats enough, and is the fee multiplied?
6. **Same flight, same product, cheaper**: is it still worth it after fees and the threshold? Is the difference cash or credit?
7. **Staleness**: offers are a snapshot (`capturedAt`). Any action needs a re-price first.
8. **Several candidates for one PNR:** what's the tie-break rule, and are ineligible ones even considered?
9. Missing or contradictory data: abstain and say why.

## Production realities the fixtures don't model (DESIGN.md material, usually don't build)
- **Exchange mechanics:** a non-refundable ticket can generally only be exchanged with its own
  (validating) carrier. A cheaper fare on *another* carrier means cancel (forfeit or credit) and buy
  new. Refundable: buy the new ticket first, then refund the old one, so the traveler is never left without a seat.
- Fare rules in real feeds are long free text (penalties, combinability). That is a plausible LLM
  extraction job, but only with validation.
- Multi-segment and round trips (married segments, fare components), connections, schedule changes by the airline.
- Volume: reshopping a large book hits supplier rate limits and look-to-book ratios. Prioritise by departure date and saving potential.
- Fares move in minutes. Inventory can disappear between recommendation and action.
- Corporate policy, loyalty or status, and traveler preferences can make a "cheaper" fare unacceptable.
