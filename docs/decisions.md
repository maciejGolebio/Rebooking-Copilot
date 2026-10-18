# Decision log

ADR-lite. One entry per decision; newest at the bottom. Written by `/kickoff`, `/frame`, `/design-doc`, `/decide`.

- **Decided by:** `user` (asked and answered) · `default` (assumed, so it must appear in DESIGN.md
  "Assumptions") · `client` (answered by the assessors) · `setup` (pre-set with the AI setup before the timed
  work; the user confirms or revises these at `/kickoff`).
- **Status:** `accepted` · `provisional` (waiting for a client answer; also listed in
  `docs/open-questions.md`) · `superseded by D-xx`.

## Index
| ID | Topic | Decision | Decided by | Status |
|----|-------|----------|------------|--------|
| D-00a | Money gate | Money math, eligibility and the final rebook gate are deterministic code; the LLM can only make a decision more conservative | setup | accepted (confirm at kickoff) |
| D-00b | Money representation | Currency-tagged decimals; no cross-currency arithmetic without an explicit, timestamped rate | setup | accepted (confirm at kickoff) |
| D-00c | Uncertainty | Unsure → `NEEDS_REVIEW` (abstain); never guess | setup | accepted (confirm at kickoff) |
| D-00d | Runtime | Runs offline with no key and no network; a real LLM is optional with a deterministic fallback | setup | accepted (follows the brief) |
| D-00e | Fixtures | `fixtures/` is immutable; extra cases go under `tests/` | setup | accepted (follows the brief) |

## Entries

### D-00a…e: Pre-set engineering rules (2026-10-18)
- **Context:** The brief stresses money safety, an explicit AI/deterministic boundary, an offline run with no key,
  and submitting the fixtures that were used.
- **Decision:** as in the index rows D-00a to D-00e. What happens *instead* when a rule bites is not pre-set. For
  example, the currency-mismatch policy is decided in `/frame`.
- **Decided by:** setup · **Status:** accepted. Revise any of them at `/kickoff`, and supersede with a new D-xx entry.
- **Why:** these are the cheapest way to avoid the "wrong saving" failure, and they're needed in every phase from the start.
- **Consequences / where it shows:** the CLAUDE.md rules, the `money-safety` invariants, the reviewers' checklists, and DESIGN.md §3–§4.

<!--
Entry format:

### D-01: <topic> (YYYY-MM-DD)
- **Context:** 1–2 lines; cite PNRs or fixture facts where relevant.
- **Options:** A) …  B) …  C) …
- **Decision:** …
- **Decided by:** user | default | client | setup · **Status:** accepted | provisional
- **Why:** …
- **Consequences / where it shows:** DESIGN.md §…, code/tests: …
-->
