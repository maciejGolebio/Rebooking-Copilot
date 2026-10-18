# Decision log

ADR-lite. One entry per decision; newest at the bottom. Written by `/kickoff`, `/frame`, `/design-doc`, `/decide`.
Architecture-significant decisions also get a full ADR in [`docs/adr/`](adr/README.md).

- **Decided by:** `user` (asked and answered) · `default` (assumed, so it must appear in DESIGN.md
  "Assumptions") · `client` (answered by the assessors) · `setup` (pre-set with the AI setup before the
  implementation work; the user confirms or revises these at `/kickoff`).
- **Status:** `accepted` · `provisional` (waiting for a client answer; also listed in
  `docs/open-questions.md`) · `superseded by D-xx`.

## Index
| ID | Topic | Decision | Decided by | Status |
|----|-------|----------|------------|--------|
| D-00a | Money gate | ~~The LLM can only make a decision more conservative~~ | setup | superseded by D-07 |
| D-00b | Money representation | Currency-tagged decimals; no cross-currency arithmetic without an explicit, timestamped rate | setup | accepted (kept at kickoff) |
| D-00c | Uncertainty | Unsure → `NEEDS_REVIEW` (abstain); never guess | setup | accepted (kept at kickoff) |
| D-00d | Runtime | Runs offline with no key and no network; a real LLM is optional with a deterministic fallback | setup | accepted (follows the brief) |
| D-00e | Fixtures | `fixtures/` is immutable; extra cases go under `tests/` | setup | accepted (follows the brief) |
| D-01 | Stack | Python 3.14 ([ADR-0001](adr/0001-python-3-14.md)) | user | accepted |
| D-02 | LLM mode | Deterministic stub by default; optional Claude behind an env var with fallback ([ADR-0002](adr/0002-llm-integration-stub-plus-claude.md)) | user | accepted |
| D-03 | Methodology | Test-first: golden case per fixture PNR plus invariant/property tests | user | accepted |
| D-04 | Runtime dependencies | Mainstream libraries allowed: pydantic, LLM SDK, LangChain or similar ([ADR-0003](adr/0003-runtime-dependencies.md)) | user | accepted |
| D-05 | Output format | `recommendations.json` validated by a JSON Schema, plus a stdout table | user | accepted |
| D-06 | Packaging | uv + `pyproject.toml` + committed `uv.lock` | user | accepted |
| D-07 | LLM decision authority | The LLM decides within code guardrails: it chooses among code-built eligible offers and judges soft trade-offs; code re-validates ([ADR-0004](adr/0004-llm-decision-authority.md)) | user | accepted |
| D-08 | Process defaults | Commit at phase/slice boundaries after OK; `/frame` drafts an assessor email; review depth chosen at review time | default | accepted |

## Entries

### D-00a…e: Pre-set engineering rules (2026-10-18)
- **Context:** The brief stresses money safety, an explicit AI/deterministic boundary, an offline run with no key,
  and submitting the fixtures that were used.
- **Decision:** as in the index rows D-00a to D-00e. What happens *instead* when a rule bites is not pre-set. For
  example, the currency-mismatch policy is decided in `/frame`.
- **Decided by:** setup · **Status:** b–e accepted at kickoff; a superseded by D-07.
- **Why:** these are the cheapest way to avoid the "wrong saving" failure, and they're needed in every phase from the start.
- **Consequences / where it shows:** the CLAUDE.md rules, the `money-safety` invariants, the reviewers' checklists, and DESIGN.md §3–§4.

### D-01: Stack (2026-10-18)
- **Context:** the prototype needs exact money maths, JSON validation and fast iteration.
- **Options:** A) Python B) TypeScript/Node C) Kotlin/JVM or Go
- **Decision:** Python 3.14.
- **Decided by:** user · **Status:** accepted
- **Why:** Decimal in the standard library, a mature validation ecosystem, first-class LLM SDKs.
  The choice depends on team experience and the existing platform; see ADR-0001, "Depends on".
- **Consequences / where it shows:** `requires-python >= 3.14`; [ADR-0001](adr/0001-python-3-14.md).

### D-02: LLM mode (2026-10-18)
- **Context:** the brief says the model is optional, there must be no keys in the repo, and the program must degrade cleanly.
- **Options:** A) stub plus optional Claude B) stub only C) real Claude as the main path
- **Decision:** A. A deterministic stub by default; Claude is enabled by `ANTHROPIC_API_KEY` plus an explicit switch.
- **Decided by:** user · **Status:** accepted
- **Why:** it runs offline and still ships a real, scored prompt.
- **Consequences / where it shows:** the Reasoner interface (`/slice reasoner`); [ADR-0002](adr/0002-llm-integration-stub-plus-claude.md).

### D-03: Methodology for the money core (2026-10-18)
- **Options:** A) test-first: golden cases plus invariants B) golden only C) spike first
- **Decision:** A. Golden cases per fixture PNR, and the `money-safety` invariants as property tests (hypothesis).
- **Decided by:** user · **Status:** accepted
- **Consequences / where it shows:** `test-engineer` writes the `decision` slice tests from the spec; DESIGN.md §4 "Tests".

### D-04: Runtime dependencies (2026-10-18)
- **Options:** A) standard library only B) a validated-model library C) anything popular
- **Decision:** C. pydantic, the anthropic SDK (optional extra), LangChain or similar where it helps. The direct SDK
  vs LangChain choice is made in `/slice reasoner`.
- **Decided by:** user (the setup had recommended A) · **Status:** accepted
- **Why:** less hand-rolled validation and schema code. Running still needs no network or key (D-00d).
- **Consequences / where it shows:** a README install step (`uv sync`); [ADR-0003](adr/0003-runtime-dependencies.md).

### D-05: Output format (2026-10-18)
- **Options:** A) a JSON file plus a table B) JSONL C) stdout JSON only
- **Decision:** A. `recommendations.json`, validated against a JSON Schema generated from the pydantic output
  model, plus a readable table on stdout.
- **Decided by:** user · **Status:** accepted
- **Consequences / where it shows:** the `cli` part of `/slice reasoner`; the README "Output" and "Example output" sections.

### D-06: Packaging (2026-10-18)
- **Options:** A) uv + pyproject B) pip + requirements.txt C) Poetry
- **Decision:** A. `pyproject.toml`, a committed `uv.lock`, and commands run via `uv run`.
- **Decided by:** user · **Status:** accepted

### D-07: LLM decision authority (2026-10-18), supersedes D-00a
- **Context:** D-00a made the LLM explain-only, which is safe but decorative. The brief asks for an AI agent.
- **Options:** A) the LLM decides within guardrails B) the LLM picks the offer only C) decide in `/design-doc` D) the LLM makes the full call
- **Decision:** A.
  - Code computes every number, applies the hard constraints and threshold, and builds the eligible set.
  - The LLM chooses among eligible offers, judges soft trade-offs, and returns the decision with a rationale.
  - Code re-validates (the offer is eligible, the output is schema-valid, there are no new numbers), and otherwise falls back to the deterministic decision.
- **Decided by:** user · **Status:** accepted
- **Why:** it gives the model a real decision role while money and hard constraints stay in code.
- **Consequences / where it shows:**
  - The invariant becomes "REBOOK ⇒ the offer is in the eligible set, whatever the reasoner returns".
  - Contract tests with adversarial fake-LLM outputs.
  - The `money-safety` and `llm-boundary` skills and the reviewer checklists were updated.
  - [ADR-0004](adr/0004-llm-decision-authority.md).

### D-08: Process defaults (2026-10-18)
- **Decision:** commit at phase/slice boundaries after the user's OK; `/frame` drafts an email to the assessors for
  the user to send; review depth is chosen in `/review-submission`.
- **Decided by:** default (stated at kickoff; the user didn't override them) · **Status:** accepted

<!--
Entry format:

### D-09: <topic> (YYYY-MM-DD)
- **Context:** 1–2 lines; cite PNRs or fixture facts where relevant.
- **Options:** A) …  B) …  C) …
- **Decision:** …
- **Decided by:** user | default | client | setup · **Status:** accepted | provisional
- **Why:** …
- **Consequences / where it shows:** DESIGN.md §…, ADR-NNNN, code/tests: …
-->
