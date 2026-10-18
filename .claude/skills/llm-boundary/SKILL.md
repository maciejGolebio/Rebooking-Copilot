---
name: llm-boundary
description: Where the LLM belongs in the Rebooking Copilot and how to wire it safely. Covers the deterministic-vs-model decision matrix, the Reasoner interface (stub plus optional Claude), prompt and structured-output design, validation, faithfulness checks, fallback, prompt injection, and the cost model. Load when designing or reviewing the reasoning step, writing prompts or output schemas, or writing DESIGN.md "Where the LLM is and isn't" or the cost sections.
user-invocable: false
---

# LLM boundary

The brief scores **the structure and the prompt(s)**, not whether a live model ran. Make the boundary explicit and defensible.

## Decision matrix (a starting point; the final split is a D-xx decision)
| Step | Default owner | Why |
|---|---|---|
| Parse and validate fixtures | Code | Exact, testable, cheap |
| Match offers to PNRs | Code | Deterministic keys |
| Hard constraints / equivalence policy | Code (versioned policy) | Money safety, auditability |
| Money math, thresholds, final gate | Code | Never trust generated numbers |
| Explanation for a human agent | LLM (or template stub) | Language is the LLM's strength; low risk if faithful |
| Soft trade-offs (schedule inconvenience vs saving) | Code score, LLM advisory at most | Optional. It may escalate, never approve |
| Free-text fare rules → structured attributes (production) | LLM extraction + validation | A real use the fixtures don't need; describe it |

## Agent shapes (a D-xx decision in /design-doc; present the one you don't pick as the considered variant)
- **Pipeline + LLM explainer/escalator:** code runs every step. The LLM writes the rationale and may set `escalate`.
  The simplest to make safe, but it has to justify the word "agent".
- **LLM orchestrating deterministic tools:** the model calls tools such as `find_candidates`, `check_policy` and
  `compute_saving`, and composes the recommendation. The final gate re-runs in code over the tool results, and any
  number not produced by a tool is rejected. This is closer to the brief's "AI agent", and it costs more tokens and needs more tests.
- Either way: every number comes from code, the gate is code, and the model can only make things more conservative.

## Reasoner interface
- `Reasoner.explain(facts) -> ReasonerOutput` with identical schemas for `StubReasoner`
  (deterministic templates) and an optional `ClaudeReasoner`.
- Pick it by config or env. No key, a timeout, an error, or schema-invalid output: fall back to the stub and record `reasoner=stub(fallback:<reason>)`.
- Facts passed in are **already computed**: decision candidate, breakdown, rule trace, trade-offs.
  The model chooses words, and at most one escalation flag from an enum.

## Prompt design (prompts are a scored artifact, so make them readable)
- Keep them in a versioned file (e.g. `prompts/rebooking_explainer_v1.md`) and record `promptVersion` in the output.
- System part: role, audience (a travel agent), hard rules ("don't introduce numbers not in FACTS",
  "if facts are insufficient, say so and set escalate=true"), and the output schema.
- User part: a delimited JSON FACTS block. Treat any free-text fields as untrusted data, not instructions (prompt injection).
- Use structured output (tool/JSON schema). Validate with pydantic/zod. Reject unknown fields.
- Make sampling as deterministic as the API allows. Keep the model id in config, not code.
  For current model ids and SDK usage, load the `claude-api` skill if it's available.

## Guards on model output
- **Faithfulness check:** every number or currency amount in the explanation must equal a value in
  FACTS. Otherwise discard it and use the template.
- The decision field is never taken from the model. The escalate flag can only downgrade.
- Log the prompt version, model, latency, tokens and fallback reason for each call.

## Confidence
Don't use model self-reported confidence as the measure. See money-safety → Confidence.

## Cost and scale (back-of-envelope with stated inputs; ask the user for volumes via /decide or present scenarios)
`cost/day ≈ bookings × reshop frequency × fraction needing LLM × tokens per call × price per token`.
Levers: call the LLM only for the ambiguous subset after deterministic filtering; cache by
(PNR hash, offer hash, prompt version); use batch processing for non-urgent sweeps; prompt-cache the
static system prompt; use a small model for explanations; set a token cap per booking. Get current prices
from the `claude-api` skill or state them as assumptions.

## Evaluation
Use an offline eval set (the fixtures plus synthetic edge cases). Measure decision agreement with
golden cases (should be 100%, because decisions are code), faithfulness pass rate, fallback rate,
and the rate of escalations that humans overturn. Run shadow mode before any autonomy.
