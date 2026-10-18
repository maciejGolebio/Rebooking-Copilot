---
name: review-submission
description: Phase 5a. Runs an independent review of the whole submission against the brief and rubric at a depth the user picks. Quick is assessor + money-safety; deep adds the LLM-boundary and fresh-run reviewers. Serious findings are adversarially verified. Then the user picks which fixes to make.
disable-model-invocation: true
---

# /review-submission

## 1. Pre-flight
The tests are green and the program runs on the fixtures. If not, fix that first; a review of broken code is wasted.

## 2. Choose the depth (AskUserQuestion, header "Review")
- **Quick** (2–6 agents): `assessor` + `money-safety-reviewer`; skeptics check critical findings only (Recommended).
- **Deep** (up to 10 agents): adds `llm-boundary-reviewer` and a fresh-clone run; skeptics check critical and high findings.
- **Self-review** (no agents): you walk the `/finalize` checklist plus the rubric yourself.

## 3. Run it
- **Quick or deep:** use the Workflow tool, `name: "review-panel"`, args `{"depth": "quick"|"deep"}`.
  If the Workflow tool isn't available, launch the same reviewers in ONE message. For deep, do the fresh-run check
  yourself: in a fresh shell, `env -u ANTHROPIC_API_KEY` plus the README commands, exactly as written.
- **Self-review:** skip to step 4 with your own findings.

## 4. Present
- The scorecard: 6 rubric dimensions, 1–5 each, with one line of evidence.
- Confirmed findings by severity, each with its failure scenario. Then list the unverified ones separately.
- A fix list sorted by impact relative to effort.

## 5. Decide and apply
- AskUserQuestion (header "Fixes", multiSelect): which fixes to do now. The unselected ones go into DESIGN.md §8
  as "known limitations / next".
- Fix, rerun the tests, rerun the program, and update DESIGN.md where needed.
- Log each reviewer finding you rejected with `/ai-log`.
- Offer a commit, `fix: review findings`. Next step: `/finalize`.
