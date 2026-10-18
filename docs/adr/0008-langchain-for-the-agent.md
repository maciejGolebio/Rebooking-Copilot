# ADR-0008: LLM library: LangChain for the agent
- **Status:** Accepted · **Date:** 2026-10-18 · **Decided by:** user · **Log:** D-20

## Context
ADR-0003 deferred the choice between the direct SDK and LangChain. ADR-0007 needs a tool-calling agent loop. The
setup recommended the direct Anthropic SDK; the user chose **LangChain**.

## Decision
- Use `langchain` and `langchain-anthropic` (ChatAnthropic, a tool-calling agent) as the optional extra `llm`.
- Import them **lazily, only in Claude mode**. The stub path never imports them (ADR-0003, D-00d).
- In tests, LangChain's fake chat models script adversarial agent behaviour. No network, no key.
- In production, the approve → re-price → re-validate → execute flow is described on **LangGraph**, using `interrupt()` for
  human approval and checkpointed state. LangGraph already arrives as a dependency of `langchain`.
- Resolved on Python 3.14 (2026-10-18): `langchain 1.4.6`, `langchain-anthropic 1.7.6`, `langchain-core 1.6.12`, `langgraph 1.2.16`.

## Depends on (team & context)
- **Familiarity:** a team that knows LangChain moves faster with it; others pay a learning cost.
- **Provider strategy:** being provider-agnostic matters if the org wants to switch or mix LLM vendors.
- **Churn tolerance:** LangChain's API changes often, so long-lived code needs pinned versions and upgrade time.
- **Dependency and data policy:** a larger dependency tree to review. LangSmith tracing is a SaaS service and may not
  be allowed for PNR data; OTel is the fallback.

## Consequences
- More dependencies in the `llm` extra. `uv.lock` pins them. A stub-mode run installs and imports none of them.
- In `/slice reasoner`, verify how `langchain-anthropic` does structured output and tool choice with the chosen Claude
  model, and keep the model id and effort level in config.
- The prompt and the tool schemas stay readable artifacts in the repo, not hidden in framework defaults.

## Alternatives considered
- **The direct Anthropic SDK:** fewer dependencies and the most explicit boundary. It was the setup's recommendation, and its tool
  runner could drive the loop.
- **LangGraph in the prototype:** durable human-in-the-loop, but more to build. It's kept as the production story.

## Revisit when
LangChain churn costs more than it saves, or the agent shrinks to a single call (then the SDK is simpler).
