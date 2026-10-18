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
decision-making. **Timebox ~2–3 h.** Depth and judgment on a few things beat shallow coverage.

## Delivery workflow (default budget for 180 min)
| Phase | Command | Min | Produces |
|---|---|---|---|
| 0 Kickoff | `/kickoff [min]` | 10 | timer, stack/method decisions, skeleton |
| 1 Frame | `/frame [deep]` | 20 | `docs/framing.md`, product stances, open questions, email draft |
| 2 Design v0 | `/design-doc` | 20 | chosen architecture and agent shape, DESIGN.md skeleton |
| 3 Build | `/slice core` → `/slice decision` → `/slice reasoner` | 75 | tests → code → targeted review |
| 4 Design v1 | `/design-doc complete` | 25 | full DESIGN.md that matches the code |
| 5 Review + finalize | `/review-submission` → `/finalize` | 30 | verified fixes, README example output, AI note, checks |

Anytime: `/decide <topic>`, `/checkpoint`, `/ai-log`. Phase commands are user-invoked: suggest them, don't
expect to run them yourself. Guide: `docs/AI_SETUP.md`.

## Rules (pre-set as D-00a–e in docs/decisions.md; the user may revise them at /kickoff)
**Money & decisions**
- Every number and the final rebook gate come from deterministic code, whatever the agent shape: a pipeline
  with an LLM explainer, or an LLM orchestrating deterministic tools. The LLM never computes or invents a
  number; any number it emits is ignored or re-verified. It may make a recommendation *more* conservative
  (escalate to review), never approve one.
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
- Respect the timebox. For anything outside the risky core, prefer "stub + describe in DESIGN.md" over building it.
  Say explicitly what was cut.
- Keep DESIGN.md in sync when a decision changes behaviour. Every assumption cites its `D-xx`.
- Compute numbers with code (a script or a test), never mentally. Show inputs.
- Commit at phase or slice boundaries, and only after the user says OK.

## Project decisions (quick reference; rationale lives in docs/decisions.md)
<!-- kickoff:start -->
Not set yet. Run `/kickoff`.
<!-- kickoff:end -->

Decision log: @docs/decisions.md
