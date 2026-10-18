# ADR-0003: Runtime dependencies: mainstream libraries allowed
- **Status:** Accepted · **Date:** 2026-10-18 · **Decided by:** user · **Log:** D-04

## Context
The options were a standard-library-only runtime (zero install for the assessors) or using popular libraries where
they save effort and make intent clearer.

## Decision
Use mainstream libraries where they earn their place:
- **pydantic v2:** domain and output models, validation, and a JSON Schema for the output.
- **anthropic SDK:** only in LLM mode, as an optional extra.
- **LangChain or similar:** allowed. Whether to use it or the direct SDK is decided in `/slice reasoner`, or with the
  agent shape in `/design-doc`.
- **Dev only:** pytest and hypothesis.

Constraint from D-00d: *running* must never need network access or a key. LLM libraries are imported lazily, only in LLM
mode. `uv.lock` is committed, and the install step (`uv sync`) is in the README.

## Depends on (team & context)
- **Familiarity:** the team's existing experience with these libraries.
- **Dependency policy:** licensing, supply-chain review, version pinning and vulnerability scanning.
- **Expected lifetime:** fast-moving frameworks (LangChain especially) add upgrade churn to long-lived code. A
  thin direct-SDK adapter is cheaper to keep.

## Consequences
- The assessors run `uv sync` once, which needs network at install time only. Versions are pinned by `uv.lock`.
- Schemas and validation come from pydantic rather than hand-rolled checks.

## Alternatives considered
- **Standard library only:** no install, more hand-written validation.
- **No constraint:** fastest, but the dependency surface becomes harder to defend.

## Revisit when
Supply-chain policy restricts these dependencies, or a library's churn starts costing more than it saves.
