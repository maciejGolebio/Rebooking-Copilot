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
| D-19 | Architecture | B: an LLM agent over deterministic tools; code builds the eligible set independently and re-validates ([ADR-0007](adr/0007-agent-over-deterministic-tools.md)); considered alternatives in DESIGN.md: A, the Hybrid, C as production design | user | accepted |
| D-20 | LLM library | LangChain (`langchain`, `langchain-anthropic`) as the `llm` extra, lazily imported; LangGraph described for production HITL ([ADR-0008](adr/0008-langchain-for-the-agent.md)) | user | accepted |
| D-21 | Agent routing | Claude mode: the agent runs only for review-level or ≥2 eligible offers; an empty set or a single clean offer is decided deterministically | user | accepted |
| D-22 | Agent veto | The agent declining a clean offer above the threshold → NEEDS_REVIEW `LLM_DISAGREES_WITH_POLICY` | user | accepted |
| D-23 | Reproducibility | Determinism is claimed for stub mode only; Claude mode records model, prompt version, tool trace and answer | user | accepted |
| D-24 | Prototype grafts from C | Build the fingerprint, a per-run seat ledger (greedy by net saving; losers `SEAT_CONTENTION`) and `asOf`/`expiresAt` (asOf + one reshop interval); the priority score is described only | user (ledger and expiry rules: default) | accepted |
| D-25 | Agent guardrail defaults | Tools take ids only and are read-only; submit tool has no numeric fields; budget 6 turns / 30 s → fallback; tool results are untrusted data; model id, effort and structured-output mechanism are chosen in `/slice reasoner` | default | accepted |
| D-26 | Input data contract | Reject each bad record on its own with `DATA_INVALID` / `DATA_INCONSISTENT` / `UNSUPPORTED_ITINERARY`; no coercion, no unknown fields, floats rejected for money, unknown ISO currencies rejected; multi-segment → unsupported | default | accepted |
| D-27 | FX provider | API-shaped `FxProvider.quote(from, to, as_of)`; `MockFxProvider` (`mock-fx-v1`) returns an executable rate with the spread included: USD→EUR 0.9276 (≈1.10 mid less ~2%); missing pair → NEEDS_REVIEW `CURRENCY_MISMATCH_NO_FX`; refines D-12 | user (shape) / default (mock values) | accepted |
| D-28 | Confidence rules | REBOOK starts HIGH, lowered one band each for FX use, net < 2× threshold, snapshot older than the reshop interval; review-level capped at MEDIUM; NEEDS_REVIEW = LOW; DO_NOT_REBOOK HIGH unless a candidate had a positive net blocked only by money rules or seat contention (then MEDIUM); refines D-17 | default | accepted |
| D-29 | Clean first | Stub mode picks the best *clean* offer before any review-level one; D-15 applies within each tier; other eligible offers are listed as alternatives | user | accepted |
| D-30 | Clarifications | Under `cash_only` a credit saving is *reported* (estimated saving + settlement CREDIT) but can never become REBOOK; "net saving" in D-15/D-24 means the *counted* net saving | default | accepted |
| D-31 | Seat-ledger rules | REBOOK-bound bookings are served before NEEDS_REVIEW-bound ones; within a group, by the counted saving of the offer the booking would pick (D-29), then input index; mixed currencies are ranked in the offer's currency via the inverse of each booking's own FX quote (ranking only) | user | accepted |
| D-32 | Fingerprint scope | Per booking: the booking, its candidate offers, policy, FX quotes, as_of, reasoner. Seat contention with other bookings can change the final recommendation under the same fingerprint (documented) | user | accepted |
| D-33 | Lead time | An offer is ineligible (DEPARTS_TOO_SOON) unless its earliest possible departure (local time read as UTC+14) is ≥ as_of + 24 h | user | accepted |
| D-34 | Price anomaly | An offer more than 60% cheaper than the paid fare per passenger (in the ticket currency) is review-level (PRICE_ANOMALY) | user | accepted; the Claude-mode MEDIUM cap superseded by D-40 |
| D-35 | Review hardening | Duplicate ids rejected; offer price > 0; FX quotes validated; per-booking isolation; rejected offers on the route → OFFER_DATA_REJECTED; freed seats re-offered; bounded amounts in a fixed Decimal context; fingerprint adds captured_at + engine | default | accepted |
| D-36 | Model and effort | `claude-sonnet-5-5` at effort `medium` (set explicitly); refusal fallback on by default ([ADR-0009](adr/0009-claude-mode-runtime.md)) | user (fallback: default) | accepted |
| D-37 | Claude-mode switch | `--reasoner claude` or `REBOOKING_REASONER=claude`; the flag wins; no credentials → per-booking fallback, announced | user | accepted; credential wording refined by D-41 |
| D-38 | Agent loop | Explicit loop on LangChain primitives (`ChatAnthropic.bind_tools`, tool_choice auto, strict tools), 6 turns / 30 s | user | accepted |
| D-39 | Validator details | Agent works on the post-ledger seat-feasible set; any failed check → full deterministic fallback; veto shows the best clean offer; agent REBOOK moves the seat | default | accepted; refined by D-40, D-41 |
| D-40 | Agent and PRICE_ANOMALY | The agent can never REBOOK an offer flagged PRICE_ANOMALY; such a submission falls back to the deterministic NEEDS_REVIEW | user | accepted |
| D-41 | Review hardening (round 2) | Typed rationale number check; strict offer-id pattern and escaped FACTS; agent outcomes keep credit savings visible and always carry a reason; an unpriced sibling offer lowers confidence; seats freed by the agent are re-offered; LangChain runtime fixes; fixed-point JSON amounts; prompt v2 | default | accepted |

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

### D-19: Architecture (2026-10-18)
- **Context:** `/design-doc` compared A (a safety-first pipeline with one LLM decision), B (an agent over tools) and C (scale-first).
- **Options:** A + grafts (recommended) · B · the Hybrid · C
- **Decision:** B. The user also asked for all the other options to appear in DESIGN.md: A as the main considered
  alternative (the user ticked "B" on the variant list, which was written assuming A would win; with B chosen this was
  read as "present the rejected options"), the Hybrid, and C as the production design.
- **Decided by:** user · **Status:** accepted · [ADR-0007](adr/0007-agent-over-deterministic-tools.md)

### D-20: LLM library (2026-10-18)
- **Options:** the direct SDK (recommended) · LangChain · LangGraph in the prototype
- **Decision:** LangChain, lazily imported in Claude mode only. LangGraph, already a transitive dependency, is described
  for the production approval flow. It resolves on Python 3.14.
- **Decided by:** user · **Status:** accepted · [ADR-0008](adr/0008-langchain-for-the-agent.md)

### D-21: Agent routing (2026-10-18)
- **Decision:** in Claude mode the agent runs only when the eligible set has a review-level offer or two or more offers.
  An empty set or a single clean offer is decided deterministically. Stub mode is always deterministic.
- **Decided by:** user · **Status:** accepted
- **Consequences:** with the fixtures alone the agent runs only for ZC3N1D. The multi-offer test cases exercise it.

### D-22: Agent veto (2026-10-18)
- **Decision:** if the agent declines a clean offer that clears the threshold, the result is NEEDS_REVIEW with
  `LLM_DISAGREES_WITH_POLICY`, so a missed saving stays visible.
- **Decided by:** user · **Status:** accepted

### D-23: Reproducibility (2026-10-18)
- **Options:** a replay cache (recommended) · record only · claim it for the stub only
- **Decision:** claim determinism for **stub mode only**. Claude mode records the model, prompt version, tool trace and answer in the audit record.
- **Decided by:** user · **Status:** accepted
- **Consequences:** the CLAUDE.md reproducibility rule and money-safety invariant 5 now say "in stub mode".

### D-24: Prototype grafts from C (2026-10-18)
- **Decision:** build the fingerprint (inputs, eligible set, policy, prompt and model), a per-run seat ledger and
  `asOf`/`expiresAt`. The priority score is described only.
  - Defaults: the ledger allocates greedily by net saving, and losers get `SEAT_CONTENTION`.
  - `expiresAt = asOf + one reshop interval`, configurable.
- **Decided by:** user (what to build) and default (ledger and expiry rules) · **Status:** accepted

### D-25: Agent guardrail defaults (2026-10-18)
- **Decision:**
  - Tools take ids only (never amounts, fees, passenger counts or rates) and are read-only.
  - `submit_recommendation` has no numeric fields.
  - Loop budget: 6 turns and 30 s, then the deterministic fallback.
  - Tool results are treated as untrusted data in the prompt.
  - The model id, effort and structured-output mechanism are chosen in `/slice reasoner` against the current API reference.
- **Decided by:** default (from the architect's proposal) · **Status:** accepted

### D-26: Input data contract (2026-10-18)
- **Context:** `/slice core`. D-00b and D-00c require exact money and abstaining on doubt, and invariant 7 requires one result per input booking.
- **Decision:**
  - Every record is validated on its own. A bad one is rejected with a reason code and later reported as NEEDS_REVIEW;
    the rest of the file still loads.
  - `DATA_INVALID`: wrong type, a missing or unknown field, a value out of range, a float in a money amount, an unknown ISO 4217 code.
  - `DATA_INCONSISTENT`: totalPaid ≠ price × passengers, mixed currencies within a ticket or offer, segment cabin ≠ ticket
    cabin, offer route date ≠ departure date.
  - `UNSUPPORTED_ITINERARY`: more than one segment (v1 is single-segment only).
  - No check that departure comes before arrival, because local times without an offset can legitimately look reversed.
  - Presentation rounding is ROUND_HALF_EVEN to ISO minor units.
  - Only a file that is unusable as a whole stops the run: unreadable JSON, missing top-level lists, or a capture time without a timezone.
- **Decided by:** default (follows from D-00b and D-00c; stated at `/slice core`) · **Status:** accepted
- **Consequences / where it shows:** `loader.py`, `models.py`, `money.py`; `tests/test_loader.py`, `tests/test_money.py`.

### D-27: FX provider (2026-10-18), refines D-12
- **Context:** the user asked for currency conversion to be "a method (it should be API, but just mock it for now)".
- **Decision:**
  - `FxProvider.quote(from_currency, to_currency, as_of) → FxQuote(rate, source, as_of)` is the seam for a real FX or treasury API.
  - `MockFxProvider` (`source = "mock-fx-v1"`) returns an *executable* rate with the spread already included, as a real
    API quote would, so the spread is not a policy setting.
  - The mock table is USD→EUR 0.9276, illustrative: about 1.10 USD/EUR mid less roughly 2%. Same currency → rate 1.
  - A missing pair raises `FxUnavailableError`, which leads to NEEDS_REVIEW `CURRENCY_MISMATCH_NO_FX`.
  - Offers are converted into the ticket's currency.
- **Decided by:** user (an API-shaped method, mocked) and default (the mock values; spread inside the quote) · **Status:** accepted
- **Consequences:** RT5K8B: 2,100 USD × 0.9276 = 1,947.96 EUR, net 252.04 EUR ≥ 110 → REBOOK, lowered to MEDIUM for FX use.

### D-28: Confidence rules (2026-10-18), refines D-17
- **REBOOK:** starts at HIGH and drops one band for each of: FX used; counted net < 2× the threshold; snapshot older than the reshop interval.
- **Review-level offers** are capped at MEDIUM (Claude mode).
- **NEEDS_REVIEW** is LOW.
- **DO_NOT_REBOOK** is HIGH when every candidate has a net ≤ 0 or fails a non-money hard block (bags, schedule, later-day arrival,
  seats). It is MEDIUM when some candidate had a positive net and failed only on the threshold or seat contention.
- **Decided by:** default · **Status:** accepted · the multiple (2) is configurable in `PolicyConfig`.

### D-29: Clean first (2026-10-18), refines D-15
- **Context:** in stub mode a review-level winner becomes NEEDS_REVIEW even when a clean REBOOK exists.
- **Decision:** pick the best clean offer first, and use review-level offers only if no clean one exists. D-15 (net
  saving → smallest schedule shift → most seats; then offer id for determinism) applies within each tier. Other eligible offers are listed as alternatives.
- **Decided by:** user · **Status:** accepted

### D-30: Clarifications from the test-first pass (2026-10-18)
- **Under `cash_only`:** a saving that would come back as credit is *reported* (estimated net saving, breakdown
  settlement CREDIT, reason SAVING_AS_CREDIT) and the action is NEEDS_REVIEW. It can never become REBOOK. This is what
  ADR-0006's "isn't counted" means.
- **"Net saving"** in D-15 and D-24 means the *counted* net saving. The two differ only under `credit_discounted`.
- **Decided by:** default (resolving wording found by the test-engineer) · **Status:** accepted

### D-31: Seat-ledger rules (2026-10-18), refines D-24
- **Context:** the test-engineer found three gaps in "greedy by net saving".
- **Decision:**
  - Bookings whose preferred offer would end in REBOOK are served before those that would end in NEEDS_REVIEW.
  - Within each group, bookings are ranked by the counted net saving of the offer they would actually pick (clean
    first, D-29), then by input index.
  - Mixed ticket currencies are ranked in the offer's currency, using the inverse of the FX quote in each booking's own
    breakdown. This is for ranking only; amounts stay in each ticket's currency.
  - A booking that loses an offer to contention gets SEAT_CONTENTION on it and falls through to its next eligible offer.
- **Decided by:** user (REBOOK first, preferred-offer ranking, FX ranking) and default (the inverse-quote mechanics) · **Status:** accepted

### D-32: Fingerprint scope (2026-10-18), refines D-24
- **Options:** include the ledger context · per booking only
- **Decision:** the fingerprint covers the booking's own inputs only: the booking, its candidate offers, the policy,
  the FX quotes, as_of and the reasoner. Seat contention with other bookings in the same run can change the final
  recommendation under the same fingerprint, and this is documented. The whole run stays deterministic in stub mode (D-23).
- **Decided by:** user · **Status:** accepted

### D-33: Lead time (2026-10-18)
- **Context:** the money-safety review found that a run with today's date REBOOKs onto flights that have already left.
- **Options:** 24 h · 3 h · not departed only
- **Decision:** 24 h. Times carry no timezone, so the check assumes the earliest possible zone: earliest departure = local
  time read as UTC − 14 h, and it must be ≥ as_of + 24 h. Otherwise the offer is INELIGIBLE with DEPARTS_TOO_SOON, a
  non-money block, so DO_NOT_REBOOK stays HIGH. With airport timezones (production) the check becomes exact.
- **Decided by:** user · **Status:** accepted · configurable (`min_lead_time`, `max_utc_offset`)

### D-34: Price anomaly (2026-10-18)
- **Context:** a zero price is now invalid data. A wildly cheap offer could still be a feed error.
- **Options:** more than 60% off → review · more than 80% off → review · no guard
- **Decision:** an offer whose price in the ticket currency is below paid × (1 − 0.60) is review-level (PRICE_ANOMALY).
  It is never approved by the stub, and is capped at MEDIUM in Claude mode (*superseded by D-40: the agent can't approve
  it at all*). The fixtures' biggest discount is 42% (HB6W9E/OF-5002).
- **Consequence:** money-safety invariant 4 has one deliberate exception. A price rising *out of* the anomaly band can
  make an offer eligible. The property test asserts the invariant only for offers outside the band.
- **Decided by:** user · **Status:** accepted · configurable (`max_plausible_discount`)

### D-35: Hardening from the money-safety review (2026-10-18)
- **Context:** `money-safety-reviewer` reported 10 findings, all reproduced. All were accepted; regression tests are in `tests/test_review_regressions.py`.
- **Decision (defaults):**
  1. A repeated offerId or PNR locator rejects every copy as DATA_INCONSISTENT. This prevents overselling and double rebooking.
  2. FX quotes are checked before use: the pair must match the request, the rate must be > 0, and the quote must be within
     one reshop interval of as_of. Any provider error means no usable quote (CURRENCY_MISMATCH_NO_FX; the trace records why).
  3. Each booking is evaluated in isolation. An unexpected error gives that booking NEEDS_REVIEW with EVALUATION_ERROR, and the run continues.
  4. as_of must be timezone-aware and not earlier than captured_at.
  5. The seat ledger re-offers seats freed by a displacement.
  6. An offer price ≤ 0 is DATA_INVALID.
  7. An offer on the booking's route that the loader rejected → OFFER_DATA_REJECTED: a REBOOK drops one band, and anything else becomes NEEDS_REVIEW.
  8. Amounts must satisfy |amount| ≤ 10¹², passengers ≤ 99, counts ≤ 9,999. All money arithmetic runs in a fixed local Decimal context.
  9. The fingerprint adds captured_at, rejected offers on the route, and the engine version.
  10. Invariant 4 holds per booking. Across bookings, the D-31 ranking can reorder the ledger (documented and tested).
- **Known limitation (not fixed):** there is no plausibility check of an FX rate against a reference. A plausible-looking
  misquote (e.g. 0.5 instead of 0.9276) would still produce a REBOOK. In production, cross-check two sources.
- **Decided by:** default · **Status:** accepted

### D-36: Model and effort (2026-10-18)
- **Context:** checked against the current Claude API reference. Sonnet 5.5 rejects forced tool choice and non-default
  sampling; thinking can't be off; effort defaults to `high`.
- **Options:** Opus 5.5 (the API reference's default; recommended) · Sonnet 5.5 · Haiku 5.5; effort low · medium · high
- **Decision:** `claude-sonnet-5-5` at `output_config.effort = "medium"`. The server-side refusal fallback
  (`fallbacks: "default"`) is on by default, per the API guidance. If the whole chain refuses, the validator falls back.
- **Decided by:** user (model, effort) and default (refusal fallback) · **Status:** accepted · [ADR-0009](adr/0009-claude-mode-runtime.md)

### D-37: Claude-mode switch (2026-10-18)
- **Options:** a `--reasoner` flag · the `REBOOKING_REASONER` env var · both
- **Decision:** both; the flag overrides the env var. Credentials resolve the SDK's normal way. Without them, or without
  the `llm` extra, the CLI says so, and every routed booking falls back with the reason recorded.
- **Decided by:** user · **Status:** accepted. *Refined by D-41:* LangChain passes the API key explicitly, so "the SDK's
  normal way" means `ANTHROPIC_API_KEY` only; `ant auth` profiles aren't read.

### D-38: Agent loop (2026-10-18), refines D-20
- **Options:** an explicit loop on LangChain primitives (recommended) · LangChain `create_agent` · the Anthropic SDK Tool Runner
- **Decision:**
  - an explicit, append-only loop: `ChatAnthropic.bind_tools(tool_choice="auto", strict=True)`;
  - four read-only, id-only tools plus `submit_recommendation`;
  - a budget of 6 turns and 30 s;
  - only `langchain-anthropic` and `langchain-core`.
- **Decided by:** user · **Status:** accepted

### D-39: Validator details (2026-10-18)
- The agent sees the booking's eligible offers that are still seat-feasible after the ledger.
- Bookings are processed in input order. A REBOOK onto a different offer moves the seat, so later bookings see what is left.
- Checks, in order:
  1. the offer is in the set;
  2. REBOOK names an offer;
  3. REBOOK passes the settlement gate;
  4. the rationale is faithful.

  Any failure means a full deterministic fallback, with the reason recorded.
- The D-22 veto shows the best clean offer and its saving, and the rationale prefixes the template to the agent's view.
- **Decided by:** default · **Status:** accepted

### D-40: The agent can't approve a price anomaly (2026-10-18), supersedes part of D-34
- **Context:** the LLM-boundary review showed that under D-34 an agent REBOOK onto a PRICE_ANOMALY offer was accepted at
  MEDIUM. An implausibly low price is a possible feed error: there's no trade-off for the model to weigh, and a wrong
  rebook onto a phantom fare costs more than a missed saving.
- **Options:** never let the agent approve it (review only) · keep the D-34 MEDIUM cap · cap it at LOW
- **Decision:** review only. In `_apply_agent`, after the settlement gate, an agent REBOOK onto an offer with
  PRICE_ANOMALY is a full fallback ("policy forbids REBOOK … (D-40)"), so the booking stays NEEDS_REVIEW. Prompt v2 says so too.
- **Decided by:** user · **Status:** accepted
- **Consequences / where it shows:** DESIGN.md §3 (validator step 4), §4 policy table, §7 row 8;
  `tests/test_review2_regressions.py::test_a_price_anomaly_is_never_approved_by_the_agent`.

### D-41: Hardening from the second review round (2026-10-18)
- **Context:** three independent reviewers (money safety, the LLM boundary, an assessor's read) checked the finished
  prototype. Every serious finding was reproduced before fixing. Regression tests are in `tests/test_review2_regressions.py`.
- **Decision (defaults):**
  1. **Number check:** the rationale is checked against typed (amount, currency) pairs from this booking's facts, not
     against any number seen. Ids, flight numbers, ISO dates and times and the FX source are stripped first; `%` and number
     words are rejected. Known limit: a real amount attributed to the wrong thing passes (a test documents it). The
     code's summary comes first in the rationale, so the human reads the right numbers before "Agent's view: …".
  2. **Injection:** tool error messages no longer echo the agent's arguments. Offer ids must match
     `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$` (else DATA_INVALID). The JSON in FACTS and tool results escapes `<` and `>`.
  3. **Agent-path visibility:** if the agent declines a credit saving under `cash_only`, the result is NEEDS_REVIEW with
     SAVING_AS_CREDIT and the saving shown (D-30). Every non-REBOOK agent outcome carries a reason, and a review-level
     REBOOK states its trade-off.
  4. **Incomplete picture:** a chosen offer whose sibling on the route couldn't be priced (no FX) gets
     CANDIDATE_NOT_EVALUATED, and a REBOOK drops one confidence band (at most two drops with OFFER_DATA_REJECTED).
  5. **Seats after the agent:** a seat the agent frees by choosing another offer is re-offered, by ledger priority, to
     bookings the agent didn't decide. Those get a fresh deterministic recommendation.
  6. **LangChain runtime:**
     - the refusal-fallback block is resent with the key `from`, because LangChain stores it as `from_`;
     - the serving model is recorded (`claude:<model>`), along with a per-call log line;
     - a text-only reply gets one reminder;
     - `max_tokens` and a refusal (with its category) are fallbacks;
     - a call starts only if its 10 s timeout fits in the 30 s budget;
     - `max_retries=0`;
     - prompt caching is requested (top-level `cache_control`);
     - Claude mode needs `ANTHROPIC_API_KEY`, because ChatAnthropic passes `api_key=""` otherwise and `ant auth`
       profiles aren't read (refines D-37);
     - the fingerprint covers the model, the effort and the prompt hash.
  7. **Output:** JSON amounts are written in fixed point, never `1E+3`. Rationale templates show exact amounts, and
     "counted as X" when the settlement policy discounts credit.
  8. **Prompt v2** (`rebooking_agent_v2.md`; v1 kept): whose saving it is, an injection rule, a reason-code glossary,
     what `chosen_offer_id` means for each decision, a strict number rule, and submit exactly once.
- **Decided by:** default (fix choices confirmed by the user) · **Status:** accepted
- **Consequences / where it shows:** DESIGN.md §3, §4, §5, §8; ADR-0009; `reasoning.py`, `agent.py`, `decision.py`, `rationale.py`.

<!--
Entry format:

### D-NN: <topic> (YYYY-MM-DD)
- **Context:** 1–2 lines; cite PNRs or fixture facts where relevant.
- **Options:** A) …  B) …  C) …
- **Decision:** …
- **Decided by:** user | default | client | setup · **Status:** accepted | provisional
- **Why:** …
- **Consequences / where it shows:** DESIGN.md §…, ADR-NNNN, code/tests: …
-->
