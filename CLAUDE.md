# Rebooking Copilot — senior SWE take-home

An agent that reviews ticketed bookings (`fixtures/pnrs.json`) against a fare snapshot
(`fixtures/fares_feed.json`) and emits one structured recommendation per booking: rebook or not,
which fare, why, confidence, estimated net saving.

The brief (scope, deliverables, rubric) is the contract: @docs/ASSIGNMENT.md

## What gets scored
1. **DESIGN.md**: the primary deliverable. 2. **Prototype + README**: how to run it, plus a real example output.
3. **AI-usage note**: which tools, how they were driven, and one AI suggestion that was rejected or corrected, and why. 4. The `fixtures/` it ran against.

Rubric: framing & requirement-sensing · architecture & AI/deterministic boundary · correctness &
money safety · scale/cost/observability · prototype quality & pragmatism · communication &
decision-making. Depth and judgment on a few things beat shallow coverage.

## Delivery workflow
| Phase | Command | Produces |
|---|---|---|
| 0 Kickoff | `/kickoff` | stack/method decisions, skeleton |
| 1 Frame | `/frame [deep]` | `docs/framing.md`, product stances, open questions, email draft |
| 2 Design v0 | `/design-doc` | chosen architecture and agent shape, DESIGN.md skeleton |
| 3 Build | `/slice core` → `/slice decision` → `/slice reasoner` | tests → code → targeted review |
| 4 Design v1 | `/design-doc complete` | full DESIGN.md that matches the code |
| 5 Review + finalize | `/review-submission` → `/finalize` | verified fixes, README example output, AI note, checks |

Anytime: `/decide <topic>`, `/ai-log`. Phase commands are user-invoked: suggest them, don't
expect to run them yourself. Guide: `docs/AI_SETUP.md`.

## Rules (D-00b–e and D-07 in docs/decisions.md; architecture decisions in docs/adr/)
**Money & decisions**
- Every number, every hard constraint and the **eligible set** come from deterministic code, whatever the agent
  shape. Within that set the LLM may choose the offer and judge soft trade-offs, approving or rejecting (D-07,
  ADR-0004). Code re-validates its answer (the offer is eligible, the output is schema-valid, it adds no numbers)
  and otherwise falls back to the deterministic decision. The LLM never computes or invents a number.
- No binary floats for money: use Decimal or integer minor units, tagged with a currency. Never add or compare
  amounts across currencies without an explicit, timestamped FX rate. *What to do instead* is a `/frame` decision.
- When unsure, return `NEEDS_REVIEW` (abstain), never a guess. A wrong "rebook" costs more than a missed saving.
- Recommendations are reproducible: the same inputs and policy version give the same output, with a rule trace.

**Runtime**
- Runs offline: no API key, no network, no paid APIs. A real LLM is optional and must degrade cleanly to the deterministic stub.
- Secrets only via env vars. `.env*` files are gitignored, and Read is denied on `.env` and `.env.local`-style files.
  `guard.py` blocks key-like content in file writes and shell commands.
- `fixtures/` is read-only: file tools are denied, `guard.py` blocks obvious mutating shell commands, and
  `/finalize` verifies `.claude/fixtures.sha256`. Extra test data goes under `tests/`.

**Working agreement**
- Do not silently decide business or methodology questions (equivalence, acceptable inconvenience, autonomy,
  thresholds, FX, confidence semantics, stack/libraries). Use `/decide`, which asks the user and records the answer
  in `docs/decisions.md`. If the client should answer, add the question to `docs/open-questions.md` and proceed on
  a stated default. Subagents cannot ask the user: they return a `needsDecision` item instead.
- When the user rejects or corrects a suggestion, or you reject a reviewer finding, log it with `/ai-log` in
  `docs/AI_USAGE_LOG.md`. That file feeds the required AI-usage note.
- Keep scope tight: build the risky core; for anything else prefer "stub + describe in DESIGN.md" over building it.
  Say explicitly what was stubbed or cut.
- Keep DESIGN.md in sync when a decision changes behaviour. Every assumption cites its `D-xx`.
- Compute numbers with code (a script or a test), never mentally. Show inputs.
- Commit at phase or slice boundaries, and only after the user says OK.

## Project decisions (quick reference; rationale lives in docs/decisions.md)
<!-- kickoff:start -->
- **Stack:** Python 3.14 ([ADR-0001](docs/adr/0001-python-3-14.md)) · uv + `pyproject.toml` + committed `uv.lock` (D-06) · src layout, package `rebooking_copilot`
- **Commands:** install `uv sync` · test `uv run pytest` · run `uv run rebooking-copilot [--pnrs PATH] [--fares PATH]` ·
  offline check `env -u ANTHROPIC_API_KEY uv run rebooking-copilot`
- **LLM mode:** deterministic stub by default; optional Claude when `ANTHROPIC_API_KEY` is set *and* an explicit switch (defined in
  `/slice reasoner`) is on (D-02, ADR-0002). The LLM decides only inside the code-built eligible set (D-07, ADR-0004).
- **Dependencies:** pydantic at runtime · `anthropic` as the optional extra `llm` (`uv sync --extra llm`) · LangChain allowed,
  decided in `/slice reasoner` · dev: pytest, hypothesis (D-04, ADR-0003)
- **Method:** test-first: a golden case per fixture PNR plus invariant/property tests (D-03)
- **Output:** `recommendations.json` validated by a JSON Schema generated from the pydantic models, plus a stdout table (D-05)
- **Process:** commit at phase/slice boundaries after OK; review depth chosen at review time (D-08)
- **Session model:** Claude Opus 5.5 (`claude-opus-5-5`) in the Claude Code desktop app
<!-- kickoff:end -->

Decision log: @docs/decisions.md
