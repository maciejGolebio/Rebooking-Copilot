---
name: kickoff
description: Phase 0. Interviews the user about stack, runtime dependencies, LLM mode, methodology and output format, records the decisions, and scaffolds the repo. Run once at the start; safe to re-run, since it only asks what's still open.
disable-model-invocation: true
---

# /kickoff: intake interview and project setup

Goal: turn the open *delivery* choices into recorded decisions, so every later phase and every subagent
works from the same assumptions. Product and policy stances (equivalence, autonomy, FX, thresholds) are
asked in `/frame`, once the fixtures have been looked at.

**You ask; the user decides.** Put your recommendation first, labelled "(Recommended)", with a one-line
trade-off per option. If the user says "you pick", record it as `Decided by: default`.

## 0. Read context (no questions yet)
Read `docs/ASSIGNMENT.md`, `fixtures/*.json`, `docs/decisions.md` (including the pre-set `D-00` entries)
and the CLAUDE.md "Project decisions" block. If some decisions exist already, ask only for what's missing.

## 1. Round 1: technology and methodology (one AskUserQuestion call)
1. **Stack** (header "Stack")
   - Python 3.11+, with pytest (+ hypothesis) for tests (Recommended): Decimal and dataclasses built in, fast to model data.
   - TypeScript/Node, with vitest (+ fast-check): pick this if it's your daily stack.
   - Kotlin/JVM, or Go: strong typing, more scaffolding.
2. **LLM in the prototype** (header "LLM mode")
   - A deterministic stub by default; optional real Claude behind an env var, with fallback (Recommended). It runs offline and still shows a real prompt.
   - Stub only, with the prompt shipped as a reviewed artifact: least risk, less to demo.
   - Real Claude as the main path (it still must degrade cleanly with no key).
3. **Methodology for the money core** (header "Method")
   - Test-first: a golden case per fixture PNR plus invariant/property tests (Recommended).
   - Golden tests only: lighter, weaker against edge cases.
   - Spike first, tests after: quickest start, riskiest for money logic.
4. **Runtime dependencies** (header "Runtime deps")
   - Standard library only at runtime; test tools are dev-only; the LLM SDK is an optional import (Recommended).
     The assessors can run it with no install and no network.
   - A small validated-model library (pydantic / zod) with a lockfile: nicer schemas, but it needs an install step.
   - Whatever suits you, with install steps in the README.

## 2. Round 2: output (one AskUserQuestion call)
**Output format** (header "Output")
- `recommendations.json` validated by a JSON Schema, plus a readable table on stdout (Recommended).
- JSONL, one recommendation per line: streams well at scale.
- JSON to stdout only.

## 3. Defaults: state them, don't ask (the user can override any of them in one line)
- **Commits:** at each phase or slice boundary, after the user's OK.
- **Questions for the assessors:** `/frame` drafts an email. The user sends it early and work goes on with stated defaults meanwhile.
- **Review depth:** chosen in `/review-submission`.
- **Pre-set rules:** list the `D-00` entries from `docs/decisions.md` in one line each and ask "keep these?"
  in plain text. Change any the user wants to revise.

## 4. Record
- Append one `D-xx` entry per answer to `docs/decisions.md`, using the format in that file, and update its index table.
- Replace the block between `<!-- kickoff:start -->` and `<!-- kickoff:end -->` in CLAUDE.md with a short
  quick reference: stack and versions; the commands to install, test and run (exact); the LLM mode and env vars;
  runtime dependencies; the output format; and the Claude model used for this session (for the AI-usage note).
- Propose permission rules for `.claude/settings.local.json`: the exact test and run commands, plus
  `Bash(python3 -c *)` (or `Bash(node -e *)`), so analysts and reviewers can compute without a prompt per call.
  Show the diff and apply it only on a yes.
- Fill in the "Tools" line of `docs/AI_USAGE_LOG.md`.

## 5. Scaffold (ask "Scaffold the skeleton now?" first)
Build the minimal skeleton for the chosen stack, with **no domain logic**. Module layout is decided in `/design-doc`.
- A project file, the test runner config, and lint/format only if the stack's default needs no extra decisions.
- One smoke test that loads both fixtures and asserts they parse.
- An entrypoint that loads the fixtures and prints "not implemented yet".
- A README.md skeleton with the sections Run · Test · Output · What is stubbed · Design (link to DESIGN.md).
  Leave the example-output section for `/finalize` to add.
- Run the test command. It must pass before you finish.

## 6. Close
Summarise the decisions in five lines or fewer and offer a commit (`chore: kickoff`). Next step: `/frame`.
