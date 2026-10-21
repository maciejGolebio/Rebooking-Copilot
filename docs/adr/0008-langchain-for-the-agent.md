# ADR-0008: LLM library: LangChain for the agent
- **Status:** Accepted · **Date:** 2026-10-18 · **Decided by:** user · **Log:** D-20

## Context
ADR-0003 deferred the choice between the direct SDK and LangChain. ADR-0007 needs a tool-calling agent loop. The
AI setup recommended the direct Anthropic SDK; I chose **LangChain**.

## Decision
- Use LangChain (`langchain-anthropic`'s ChatAnthropic, a tool-calling agent) as the optional extra `llm`.
- Import them **lazily, only in Claude mode**. The stub path never imports them (ADR-0003, D-00d).
- In tests, LangChain's fake chat models script adversarial agent behaviour. No network, no key.
- In production, the approve → re-price → re-validate → execute flow is described on **LangGraph**, using `interrupt()` for
  human approval and checkpointed state.
- *Refined by D-38 and [ADR-0009](0009-claude-mode-runtime.md):* the prototype uses an explicit loop on
  `ChatAnthropic.bind_tools`, so only `langchain-anthropic` and `langchain-core` are installed. The `langchain`
  meta-package and LangGraph are not; LangGraph remains the production story.

## Depends on (team & context)
- **Familiarity:** a team that knows LangChain moves faster with it; others pay a learning cost.
- **Provider strategy:** being provider-agnostic matters if the org wants to switch or mix LLM vendors.
- **Churn tolerance:** LangChain's API changes often, so long-lived code needs pinned versions and upgrade time.
- **Dependency and data policy:** a larger dependency tree to review. LangSmith tracing is a SaaS service and may not
  be allowed for PNR data; OTel is the fallback.

## Consequences
- More dependencies in the `llm` extra. `uv.lock` pins them. A stub-mode run installs and imports none of them.
- Before building the loop, verify how `langchain-anthropic` handles structured output and tool choice with the chosen
  Claude model, and keep the model id and effort level in config. (Done in ADR-0009: forced tool choice is rejected, so
  the loop uses `tool_choice="auto"` with strict tools.)
- The prompt and the tool schemas stay readable artifacts in the repo, not hidden in framework defaults.

## Alternatives considered
- **The direct Anthropic SDK:** fewer dependencies and the most explicit boundary. It was the setup's recommendation, and its tool
  runner could drive the loop.
- **LangGraph in the prototype:** durable human-in-the-loop, but more to build. It's kept as the production story.

## Revisit when
LangChain churn costs more than it saves, or the agent shrinks to a single call (then the SDK is simpler).
