---
name: slice
description: Phase 3. Builds one vertical slice test-first (acceptance criteria → failing tests → minimal code → green → targeted review). The default plan is three slices, risky core first - /slice core, /slice decision, /slice reasoner - but any name works.
argument-hint: "<slice-name> [notes]"
disable-model-invocation: true
---

# /slice $ARGUMENTS

Keep every slice thin, and spend the review effort where the risk is.

## Default plan (follow DESIGN.md if it differs)
| Slice | Contents | Tests by | Review |
|---|---|---|---|
| `core` | typed domain, fixture loading with validation (flag bad data, never coerce silently), the Money type with a currency guard | you: small unit tests | none (covered by `decision`) |
| `decision` | candidate matching, the equivalence / hard-constraint policy (versioned), net saving, thresholds, REBOOK / DO_NOT_REBOOK / NEEDS_REVIEW, confidence, rule trace | **`test-engineer` once**: a golden case per fixture PNR plus the invariants | **`money-safety-reviewer` once**, at the end |
| `reasoner` | the Reasoner interface: deterministic stub, optional Claude adapter (per LLM mode), prompt file, output schema, validation, faithfulness check, fallback; CLI output to the agreed format | you | deferred to `/review-submission` |

Observability: one structured log line per decision, plus counters, is enough. Describe the rest in DESIGN.md §5.

## 0. Scope check
- Read the CLAUDE.md quick reference, `docs/decisions.md`, and the relevant DESIGN.md section.
- State the slice's acceptance criteria in 3–6 bullets, each citing its D-xx.
- If a criterion depends on an undecided business or methodology choice, run `/decide` first. Don't guess.
- If the slice is growing beyond the risky core, ask (AskUserQuestion, header "Scope"):
  build it thinner · stub it and describe it in DESIGN.md · skip it.

## 1. Tests first
- For `decision`, delegate to `test-engineer` with the acceptance criteria and D-ids. Its tests come from the spec, not from code.
  Run it in the background, and sketch the module boundaries while it works.
- For other slices, write the tests yourself.
- Run them. They must fail for the expected reason. Anything reported as `needsDecision` goes through `/decide`.

## 2. Implement
Write the minimal code to pass. Follow the `money-safety` and `llm-boundary` rules. No speculative abstractions,
and no new dependency without a recorded decision (check the runtime-dependency decision).

## 3. Verify
Run the full test suite, then the program on the fixtures. Read the output for the affected PNRs the way a
travel agent would. Does each recommendation make sense on its own?

## 4. Review (only where the table says so)
Pass the reviewer the changed files and the acceptance criteria. Fix the confirmed issues. If a finding is
wrong, push back, say why, and log the rejection with `/ai-log`. Those rejections are good AI-usage-note material.

## 5. Close the loop
Update DESIGN.md §8 (the Built/Stubbed table) plus any v0 bullet whose behaviour changed. Record new decisions.
Offer a commit, `feat(<slice>): …`. The session hook counts these commits.
