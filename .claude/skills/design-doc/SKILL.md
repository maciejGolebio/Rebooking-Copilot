---
name: design-doc
description: Phases 2 and 4 for DESIGN.md, the primary deliverable. With no DESIGN.md yet, it generates architecture options, asks the user to choose, and writes a v0 skeleton. After the build, `complete` writes the full v1. Also takes `<section>` to work on one section, `review` for an assessor critique, and `options deep` for the 3-architect workflow.
argument-hint: "[options [deep] | <section> | complete | review]"
disable-model-invocation: true
---

# /design-doc $ARGUMENTS

DESIGN.md is what gets scored most. Write it for a senior teammate deciding whether to trust this in
production: decisions first, then reasons, then trade-offs. Use tables over prose.

There are two passes. **v0 (about 20 minutes, before the build):** bullets only, enough to build against. **v1
(about 25 minutes, after the build):** full prose that matches the code, 1,500–2,500 words.

## Mode: `options` (default when DESIGN.md doesn't exist yet)
1. Generate options.
   - **Quick (default):** spawn one `solution-architect` agent and ask it for 2–3 *contrasting* architectures in one
     answer (e.g. safety-first · judgement-where-it-pays · scale-first). For each: the flow, the LLM vs code
     split, money safety, the scale story, what's buildable in the remaining minutes, and its `needsDecision` items.
   - **Deep (`options deep`, about 10–15 minutes):** use the Workflow tool, `name: "design-options"`, args
     `{"decisions": "docs/decisions.md", "framing": "docs/framing.md", "remainingMinutes": <from timebox status>}`.
     If the tool isn't available, launch 3 `solution-architect` agents in ONE message, one per angle.
2. Show a compact comparison table: option · idea · LLM role · money-safety story · scale story · buildable now · score.
3. Ask the user (AskUserQuestion, at most 4 questions per call; split into more calls if needed):
   - **Approach** (header "Approach"): the recommended option first.
   - **Agent shape** (header "Agent shape"), unless it's already decided:
     a deterministic pipeline with an LLM explainer/escalator ·
     an LLM agent that orchestrates deterministic tools (find candidates, check policy, compute saving), with the final gate in code ·
     a hybrid.
     Recommend the one that fits the chosen LLM mode, and present the other as the considered variant.
     The brief asks for an "AI agent", so an explainer-only design has to justify itself.
   - **Variant to present** (header "Variant", multiSelect): which rejected options to keep in DESIGN.md as
     "considered alternatives". The rubric rewards a considered variant.
   - The merged and deduped `needsDecision` / `questionsForUser` items that change the design.
4. Record the choices as D-xx entries. Create DESIGN.md from [template.md](template.md) and fill in the **v0**:
   TL;DR, §2 flow, §3 table, §4 policy table, §6 autonomy, and the §7 assumptions, all as bullets.

## Mode: `<section>`
- Write or revise only that section. Each assumption cites its `D-xx`; each open question links to `docs/open-questions.md`.
- §3 (LLM boundary) needs the step-by-step table and the actual prompt location and version.
- §5 (scale/cost) needs back-of-envelope numbers with **stated inputs**. If volume or frequency is undecided,
  run `/decide` or show 2–3 scenarios (e.g. 10k / 1M / 50M bookings). Compute the numbers with a script.
- §8 needs an accurate Built / Stubbed / Described-only table. Check it against the code, not against intentions.
- If a section reveals a business choice nobody has made yet, stop and run `/decide`.

## Mode: `complete` (the v1 pass, after the build)
Go in rubric order: §4 money safety → §3 LLM boundary → §1 framing → §5 scale/cost/obs → §7 → §8 → TL;DR.
Rewrite the bullets into tight prose and tables that match the code and the real output. Leave §9 for `/finalize`.

## Mode: `review`
Spawn the `assessor` agent on DESIGN.md (and the code if it exists). Show its scorecard and top 5 fixes, ranked
by value per minute. Ask which to apply (AskUserQuestion, multiSelect). Log any rejected suggestion with `/ai-log`.

## Always
Keep DESIGN.md consistent with `docs/decisions.md` and with the code. After each slice, update §8.
Offer a commit after a substantive revision (`docs: design <pass or section>`).
