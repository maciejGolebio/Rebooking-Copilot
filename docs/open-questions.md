# Open questions

Ranked. Each one has our default, so work continues without an answer. The ones marked ✉ are in
[`questions-email.md`](questions-email.md). When an answer arrives, record it as `Decided by: client` and supersede the entry it affects.

| # | Question | Why it matters | Our default if unanswered | Affects |
|---|---|---|---|---|
| 1 ✉ | When a non-refundable ticket is changed to a cheaper fare, is the difference refunded in cash, kept as travel credit, or forfeited? Does credit count as a saving? | Decides whether QX7T2A's 80 is real money | Refundable → cash, non-refundable → credit; only cash counts (`cash_only`); credit → NEEDS_REVIEW | D-10 |
| 2 ✉ | Whose saving is it: the traveler's or the paying client's? And roughly what does one human review plus exchange cost? | Sets the threshold and who carries the trade-offs | The payer; threshold max(25, 5% of total paid) | D-13 |
| 3 ✉ | Is the applicable fee the *existing* ticket's change fee, per passenger? | HB6W9E/OF-5002 is −40 under that basis, +110 under the offer's fee | Yes; the offer's fee only matters for a later change | D-18 |
| 4 ✉ | For RT5K8B (EUR ticket, USD fare): can the agency exchange into a fare sold in another currency or point of sale? Is there an FX source we should assume? | A converted "saving" may not be achievable | A stubbed, timestamped FX table with a spread margin | D-12 |
| 5 ✉ | Are a basic-economy downgrade, lost refundability, or a carrier change ever acceptable if a human approves, or should any of them be ruled out? | Defines the eligible set and how much the LLM decides | Only fewer bags is ruled out; the others go to review, with an LLM REBOOK capped at MEDIUM | D-11, D-16 |
| 6 ✉ | Roughly how many active bookings, and how often should they be re-shopped? | The scale and cost section | Scenarios of 10k / 1M / 50M bookings | DESIGN.md §5 |
| 7 | Should v1 ever execute automatically? | Confidence semantics and safety machinery | Recommend-only; a future auto tier for HIGH, clean cases after shadow mode | D-09, D-17 |
| 8 | Is the fare amount the full ticket price, including taxes? | Savings are overstated if taxes differ | Treat `amount` as the full comparable amount | framing §6 |
| 9 | What minimum net saving applies per currency (e.g. JPY, KWD)? | A bare 25 is a very different bar in each currency | 25 in the ticket's currency, a stated limit (the fixtures use it only in USD) | D-13, D-42 |
