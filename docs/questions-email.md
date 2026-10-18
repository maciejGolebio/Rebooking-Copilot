# Draft: clarifying questions for the assessors

> **Draft only: Claude never sends this.** Send it yourself to the address in the brief (przemyslaw@oversee.biz).
> When answers arrive, record them in `docs/decisions.md` as `Decided by: client`.

**Subject:** Rebooking Copilot: six quick clarifying questions

Hi Przemysław,

I'm working on the Rebooking Copilot exercise and have a few questions. Each one has the default I'm proceeding with,
so there's no need to reply if the defaults are fine. A one-line answer is plenty where they aren't.

**What counts as a saving**
1. When a non-refundable ticket is changed to a cheaper fare, does the difference come back as cash, as travel credit,
   or is it forfeited, and should credit count as a saving?
   *Default: refundable → cash, non-refundable → credit; only cash counts, and credit goes to human review.*
2. Whose saving is it, the traveler's or the paying client's? And roughly what does one agent review plus exchange cost?
   *Default: the payer's; a minimum net saving of max(25, 5% of the fare).*
3. Is the applicable fee the existing ticket's change fee, per passenger?
   *Default: yes; the new fare's fee only matters for a later change.*

**What counts as an acceptable rebooking**
4. For a ticket paid in one currency with a cheaper fare quoted in another (EUR vs USD in the fixtures), can the agency
   actually exchange across currencies or points of sale, and is there an FX source you'd like me to assume?
   *Default: a stubbed, timestamped rate table with a spread margin, and the rate recorded in the output.*
5. Are a basic-economy downgrade, lost refundability, or a carrier change ever acceptable if a human approves?
   *Default: fewer included bags is ruled out; the others go to human review.*

**Scale**
6. Roughly how many active bookings would this run against, and how often should they be re-shopped?
   *Default: I'll size the design for 10k, 1M and 50M bookings.*

Other assumptions I'm working with: v1 is recommend-only (a human approves every rebook), and the fare snapshot is
re-priced before any action.

Thanks,
Maciej
