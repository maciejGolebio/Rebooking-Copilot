# Architecture Decision Records

Architecture-significant decisions for the Rebooking Copilot: one file per decision, numbered, never
rewritten. A changed decision gets a new ADR that supersedes the old one. Smaller product and process
decisions live only in [`docs/decisions.md`](../decisions.md); every ADR links to its `D-xx` entry there.

**For reviewers (human or AI):** every ADR has a section **"Depends on (team & context)"**. It says where a real
team could reasonably decide differently, for example because of team experience, the existing platform, policy or risk appetite.

| ADR | Title | Status | Log |
|-----|-------|--------|-----|
| [0001](0001-python-3-14.md) | Use Python 3.14 for the prototype | Accepted | D-01 |
| [0002](0002-llm-integration-stub-plus-claude.md) | LLM integration: deterministic stub by default, optional Claude | Accepted | D-02 |
| [0003](0003-runtime-dependencies.md) | Runtime dependencies: mainstream libraries allowed | Accepted | D-04 |
| [0004](0004-llm-decision-authority.md) | LLM decision authority: the LLM decides within code guardrails | Accepted | D-07 (supersedes D-00a) |
| [0005](0005-eligibility-tiers-and-confidence-cap.md) | Eligibility tiers and a confidence cap for LLM approvals | Accepted (amends 0004) | D-11, D-14, D-16, D-17, D-18 |
| [0006](0006-money-model-settlement-fx-fees.md) | Money model: settlement form, FX and fee basis | Accepted (parts provisional) | D-10, D-12, D-13, D-18 |
| [0007](0007-agent-over-deterministic-tools.md) | Architecture: an LLM agent over deterministic tools | Accepted | D-19, D-21, D-22, D-24, D-25 |
| [0008](0008-langchain-for-the-agent.md) | LLM library: LangChain for the agent | Accepted | D-20 |
| [0009](0009-claude-mode-runtime.md) | Claude-mode runtime: Sonnet 5.5, explicit LangChain loop, validator | Accepted (refines 0007/0008) | D-36–D-39 |

## Template
```markdown
# ADR-NNNN: <title>
- **Status:** Proposed | Accepted | Superseded by ADR-NNNN · **Date:** YYYY-MM-DD · **Decided by:** user | default | client · **Log:** D-xx

## Context
## Decision
## Depends on (team & context)
## Consequences
## Alternatives considered
## Revisit when
```
