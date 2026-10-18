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
| D-09 | Autonomy | Recommend only; a human approves every rebook; DESIGN.md describes a future auto tier | user | accepted |
| D-10 | What counts as a saving | Configurable `settlementPolicy`; default `cash_only`; assumed refundable → cash, non-refundable → credit ([ADR-0006](adr/0006-money-model-settlement-fx-fees.md)) | user (default: user) | provisional (ask client Q1) |
| D-11 | Hard blocks | Only *fewer included bags* blocks outright; cabin downgrade, lost refundability, carrier change, added stop are review-level ([ADR-0005](adr/0005-eligibility-tiers-and-confidence-cap.md)) | user | accepted |
| D-12 | Currency mismatch | Stubbed `FxProvider`: timestamped static rates plus a spread margin; rate, source and as-of recorded ([ADR-0006](adr/0006-money-model-settlement-fx-fees.md)) | user | accepted (point of sale asked as client Q4) |
| D-13 | Threshold | Net ≥ max(25, 5% of total paid) in the ticket's currency; configurable | user | accepted |
| D-14 | Schedule window | Same flight is normal; another flight within ±60 min departure is review-level; beyond, or a next-day arrival, is ineligible | user | accepted |
| D-15 | Tie-break (stub and fallback) | Highest net saving → smallest schedule change → most seats left | user | accepted |
| D-16 | LLM approval on review-level differences | The LLM may recommend REBOOK; confidence capped at MEDIUM; trade-offs listed ([ADR-0005](adr/0005-eligibility-tiers-and-confidence-cap.md)) | user | accepted |
| D-17 | Confidence | LOW/MEDIUM/HIGH bands from code signals; HIGH = future auto-tier eligible; the LLM can only lower it | user | accepted |
| D-18 | Framing defaults | Fee = existing ticket's change fee × pax; as-of clock injected, default `capturedAt`; stub returns NEEDS_REVIEW for review-level differences; extra test cases under `tests/` | default | accepted (fee basis provisional: client Q3) |

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

### D-09: Autonomy (2026-10-18)
- **Context:** money moves on execution; the brief leaves "recommend vs act" open.
- **Options:** A) recommend only B) tiered auto-execute C) fully autonomous
- **Decision:** A. A human approves every rebook. DESIGN.md §6 describes what must be true before an auto tier for HIGH-confidence clean cases.
- **Decided by:** user · **Status:** accepted

### D-10: What counts as a saving (2026-10-18)
- **Context:** QX7T2A is non-refundable; in practice its 180 USD difference may come back as travel credit.
- **Options:** A) cash only B) credit at face value C) credit at a discount. The user asked for this to be **selectable**.
- **Decision:** a configurable `settlementPolicy` (`cash_only` | `credit_face_value` | `credit_discounted(f)`), default
  `cash_only`. The assumed settlement form is refundable → cash, non-refundable → credit; no fixture field says so.
- **Decided by:** user (both the configurability and the default) · **Status:** provisional, client Q1
- **Consequences / where it shows:** QX7T2A → NEEDS_REVIEW by default, with the residual reported as credit; [ADR-0006](adr/0006-money-model-settlement-fx-fees.md).

### D-11: Hard blocks (2026-10-18)
- **Context:** the fixtures contain every kind of difference: downgrade, bags, refundability, carrier and stops.
- **Options (multi-select):** cabin downgrade · lost refundability · fewer bags · carrier change/added stop. The setup recommended all four.
- **Decision:** only **fewer included bags** makes an offer ineligible. The others are review-level differences.
- **Decided by:** user · **Status:** accepted
- **Consequences / where it shows:** LM9P4C/OF-2001 and HB6W9E/OF-5002 are ineligible (bags 1 → 0). ZC3N1D/OF-4001 is review-level; [ADR-0005](adr/0005-eligibility-tiers-and-confidence-cap.md).

### D-12: Currency mismatch (2026-10-18)
- **Context:** RT5K8B was paid 2,200 EUR; the same flight and fare basis is offered at 2,100 USD.
- **Options:** A) re-shop in the ticket's currency, NEEDS_REVIEW (the setup's recommendation) B) a stubbed FX table C) not comparable
- **Decision:** B. An injected `FxProvider`, stubbed with timestamped static rates plus a spread margin; amounts are
  compared in the ticket's currency; the rate, source and as-of are recorded in the output. The rates are labelled illustrative.
- **Decided by:** user · **Status:** accepted. Whether the agency can exchange across points of sale is asked as client Q4.

### D-13: Threshold (2026-10-18)
- **Decision:** net ≥ max(25, 5% of total paid), in the ticket's currency, configurable and versioned with the policy.
  QX7T2A needs 25 (it has 80), ZC3N1D needs 32 (it has 140), RT5K8B needs 110 EUR.
- **Decided by:** user · **Status:** accepted

### D-14: Schedule window (2026-10-18)
- **Decision:** the same flight is normal. Another flight departing within ±60 min is a review-level difference.
  Beyond ±60 min, or arriving on a later day, makes it ineligible.
- **Decided by:** user · **Status:** accepted
- **Consequences:** LM9P4C/OF-2001 (−20 min) is review-level on schedule, but it is already ineligible on bags.
  HB6W9E/OF-5002 (+875 min, next-day arrival) is ineligible.

### D-15: Tie-break (2026-10-18)
- **Decision:** in stub mode, and as the fallback when Claude's answer is rejected: highest net saving → smallest
  schedule change → most seats left.
- **Decided by:** user · **Status:** accepted

### D-16: LLM approval on review-level differences (2026-10-18), refines D-07
- **Options:** A) yes, with confidence capped at MEDIUM B) always NEEDS_REVIEW, LLM advisory only C) yes, uncapped
- **Decision:** A. The LLM may recommend REBOOK for a review-level offer; confidence is capped at MEDIUM and the
  trade-offs are listed. Only clean offers can reach HIGH.
- **Decided by:** user · **Status:** accepted · [ADR-0005](adr/0005-eligibility-tiers-and-confidence-cap.md)

### D-17: Confidence (2026-10-18)
- **Decision:** LOW / MEDIUM / HIGH bands computed from code signals (data completeness, margin above threshold,
  snapshot age, FX use, review-level differences). HIGH = eligible for a future auto tier. The LLM can only lower confidence.
- **Decided by:** user · **Status:** accepted

### D-18: Framing defaults (2026-10-18)
- **Fee basis:** the existing ticket's `changeFeePerPassenger` × passengers; the offer's fee only matters for a later
  change. HB6W9E/OF-5002: −40 under this basis, +110 if the offer's fee were used. Provisional: client Q3.
- **Clock:** the as-of time is injected and defaults to `capturedAt` (2026-07-08). With the wall clock, every fixture
  flight has already departed.
- **Stub on review-level differences:** NEEDS_REVIEW (follows from D-00c). Only Claude mode may recommend REBOOK there (D-16).
- **Extra test cases** under `tests/`: several eligible offers for one booking, seat contention, FX edge cases, so the
  LLM's choice and the tie-break are actually exercised.
- **Decided by:** default (follows from earlier decisions; stated at `/frame`) · **Status:** accepted; fee basis provisional

<!--
Entry format:

### D-19: <topic> (YYYY-MM-DD)
- **Context:** 1–2 lines; cite PNRs or fixture facts where relevant.
- **Options:** A) …  B) …  C) …
- **Decision:** …
- **Decided by:** user | default | client | setup · **Status:** accepted | provisional
- **Why:** …
- **Consequences / where it shows:** DESIGN.md §…, ADR-NNNN, code/tests: …
-->
