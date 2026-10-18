# ADR-0007: Architecture: an LLM agent over deterministic tools
- **Status:** Accepted · **Date:** 2026-10-18 · **Decided by:** user · **Log:** D-19, D-21, D-22, D-24, D-25

## Context
I compared three options:
- **A:** a deterministic pipeline with one structured LLM decision inside the eligible set.
- **B:** an LLM agent that investigates cases through read-only deterministic tools.
- **C:** a scale-first incremental pipeline.

The AI setup recommended A; I chose **B**, which matches the brief's "AI agent" wording and gives the model a real
investigative role. ADR-0004 and ADR-0005 still bind it: every number, hard constraint and the eligible set come from code.

## Decision
1. **Core, as pure functions named as tools:** `find_candidates(pnr)`, `check_policy(pnr, offer)` (tier and rule
   trace), `compute_saving(pnr, offer)` (breakdown: fee basis, settlement form, FX), `get_fx_rate(from, to)`.
   Code uses them to build the eligible set E, a **fingerprint**, and a per-run **seat ledger** (D-24).
2. **Router** (D-21): stub mode always goes the deterministic way. In Claude mode, an empty E or a single clean offer
   also goes the deterministic way; review-level offers or two or more eligible offers go to the agent.
3. **Agent** (LangChain tool-calling, ADR-0008). Tools take **ids only**, never amounts, fees, passenger counts or rates, and
   are read-only. The agent submits through `submit_recommendation(chosenOfferId | null, decision, rationale)`, which
   has **no numeric fields**. Its budget is 6 turns and 30 s, then the fallback (D-25).
4. **Validator:** rebuilds E from the source data, not from the agent's transcript, then checks:
   - the schema;
   - that the chosen offer is in E;
   - the tier cap (a review-level REBOOK is capped at MEDIUM);
   - the settlement and threshold gates;
   - faithfulness: every number in the rationale must exist in the code breakdown;
   - the veto rule (D-22: declining a clean offer above the threshold → NEEDS_REVIEW `LLM_DISAGREES_WITH_POLICY`).

   Any failure falls back to the deterministic decision, and the reason is recorded.
5. **Output:** confidence computed by code (D-17), `asOf` / `expiresAt`, and an audit record that includes the tool trace.

## Depends on (team & context)
- **Agent and LLM-ops experience:** debugging tool loops, tracing and evals take practice. A team new to agents
  would reasonably start with A and add the agent once it has evals.
- **Risk appetite and accountability:** the model chooses what to look at. Compliance may want the simpler A boundary for money-moving decisions.
- **Cost budget:** this design uses roughly 2.5× A's tokens per agent-decided case and batches badly. The inputs are in DESIGN.md §5.
- **Data protection:** tool results put PNR data into model context, so the provider and region need approval (ADR-0002).
- **Observability tooling:** agent runs need traces (OTel or a vendor). Vendor SaaS tracing may not be allowed for PNR data.

## Consequences
- The model's role is real but bounded. With the fixtures alone the agent runs for **one** booking (ZC3N1D, review-level),
  so extra multi-offer cases under `tests/` exercise it (D-18).
- There are two decision paths: the deterministic one (stub, and Claude-mode clean cases) and the agent. The validator
  and the invariants apply to both.
- Determinism is claimed for stub mode only (D-23). Claude mode records the model, prompt version, tool trace and answer.
- The test surface is larger: scripted fake-LLM agents must cover an ineligible id, invented numbers, invalid output, an
  exhausted budget, a timeout and tool-argument abuse.

## Alternatives considered
- **A, a safety-first pipeline with one LLM call:** the simplest boundary, fully testable, cheapest. I rejected it in
  favour of a real agent role. It is DESIGN.md's main considered alternative.
- **A Hybrid of A and B:** A for every case, and the agent only for hard ones. Close to what the D-21 router does, but without
  the agent's investigation step on simple cases.
- **C, scale-first:** adopted as the *production* shape in DESIGN.md §5. The prototype builds the fingerprint, seat ledger and expiry from it.

## Revisit when
Evals show the agent adds no value over A's single call, or free-text fare rules and multi-segment exchanges give it more to investigate.
