---
name: frame
description: Phase 1. Builds a per-PNR fact table with a script, analyses business ambiguity and production gaps, asks the user to set the product stances, and drafts clarifying questions for the assessors. `/frame deep` runs the 4-lens workflow instead of the quick path.
argument-hint: "[deep]"
disable-model-invocation: true
---

# /frame $ARGUMENTS: problem framing and requirement-sensing

This phase serves the rubric's "problem framing & requirement-sensing" and "communication &
decision-making" dimensions. What it produces becomes DESIGN.md §1 and §7. Budget: about 20 minutes.

## 1. Analyse
**Quick (default), in parallel:**
- Launch one `fixture-analyst` agent **in the background**, with the lens "business ambiguity + production
  reality": undefined requirements, business choices, questions for the assessors, gaps the fixtures don't model.
  Ask it for a compact result: at most 10 traps, 8 questions and 6 choices.
- Meanwhile, build the per-PNR fact table yourself with a throwaway script in the scratchpad. Never do the numbers by hand.

**Deep (`/frame deep`, about 8 minutes):** run the saved workflow `frame-problem` with the Workflow tool:
`name: "frame-problem"`, args `{"brief": "docs/ASSIGNMENT.md", "fixtures": "fixtures", "decisions": "docs/decisions.md"}`.
If the Workflow tool isn't available, run 4 `fixture-analyst` lenses in ONE message instead (money ·
equivalence & traveler impact · business ambiguity · production & scale).

## 2. Write `docs/framing.md`
- **Per-PNR table:** PNR · pax · paid (per pax / total / currency) · candidate offer(s) · differences from what was
  booked (flight, time, stops, cabin, refundability, bags, carrier, seats) · gross Δ · fees · naive net · what makes
  it tricky. Label the numbers "naive: before policy".
- **Traps:** the ones in the fixtures, plus the production ones the fixtures don't model.
- **Assumptions:** for each, the assumption · why · alternative · impact if wrong.
- **Conflicts:** places where the analyses disagree. Don't paper over them.

## 3. Product stances: ask the user
Use AskUserQuestion, at most 4 questions per call, recommendation first. **Cite the PNR(s) that illustrate each
choice in the question text.** Skip what `docs/decisions.md` already settles, and adapt the options to what the
analysis found.

**Call 1: what a "saving" is and how much autonomy**
1. **Autonomy** (header "Autonomy")
   - Recommend only; a human approves every rebook; the design describes a future auto tier (Recommended).
   - Tiered: auto-execute only high-confidence, same-flight, same-product cases; everything else goes to a human.
   - Fully autonomous.
2. **What counts as a saving** (header "Saving")
   - Only cash back to the payer counts. Residual travel credit is reported separately and needs human review (Recommended).
   - Credit counts at face value.
   - Credit counts at a discount (the value is set in policy).
   - Also confirm whose saving it is (the traveler's or the agency's client's) if the analysis flags it.
3. **Hard blocks** (header "Hard blocks", multiSelect): which differences make an offer ineligible outright, rather than
   sending it to human review? Options: cabin/fare-product downgrade · lost refundability · fewer included bags ·
   added stop or a different flight beyond the schedule window. Recommend the first three.
4. **Currency mismatch** (header "FX")
   - Re-shop in the ticket's currency and point of sale; a foreign-currency offer goes to NEEDS_REVIEW; FX is used only for ranking (Recommended).
   - A stubbed FX provider with a timestamped static table, and a margin for spread.
   - Treat it as not comparable, so DO_NOT_REBOOK.

**Call 2: the numbers and tie-breaks**
1. **Threshold values** (header "Threshold"). Show the naive nets from the table so the user sees which PNRs flip.
   - Net saving ≥ max(USD 25, 5% of fare), configurable (Recommended).
   - Net saving ≥ max(USD 50, 10% of fare).
   - Any positive net saving.
2. **Schedule window** (header "Schedule")
   - Same flight only for auto; up to ±60 min departure goes to review; anything beyond is ineligible (Recommended).
   - Up to ±2 h is eligible.
   - Same flight only.
3. **Several eligible offers** (header "Tie-break")
   - Highest net saving, then least schedule change, then the most seats left (Recommended).
   - Least change first, then saving.
4. **Confidence semantics** (header "Confidence")
   - Bands from deterministic signals (data completeness, margin above threshold, snapshot age, trade-offs); HIGH = eligible for a future auto tier (Recommended).
   - A 0–1 score with documented components.

Record each answer in `docs/decisions.md`. Anything the user marks "ask the client" gets `Status: provisional`, with the stated default.

## 4. Questions for the assessors
- `docs/open-questions.md`: a ranked list. For each, the question · why it matters · our default if unanswered ·
  the D-xx it affects. Put the money-definition questions at the top: cash vs credit, whose saving, the cost of a human review.
- `docs/questions-email.md`: a short, senior-sounding email draft to the address in the brief, with 6 questions or
  fewer. Group them; make each answerable in one line; state our default so silence is fine. **Never send it.**
  Tell the user to send it now, and that work carries on with the defaults. Don't pause the timer while waiting.

## 5. Close
Summarise in five lines or fewer, append a `/checkpoint` row, and offer a commit (`docs: framing`). Next step: `/design-doc`.
