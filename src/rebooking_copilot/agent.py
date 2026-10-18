"""Claude mode: an explicit tool-calling loop on LangChain primitives (D-19, D-20, D-38, ADR-0009).

`ChatAnthropic` (langchain-anthropic, which calls the official Anthropic SDK) with `bind_tools(tool_choice="auto",
strict=True)`. Forced tool choice is rejected by Claude Sonnet 5.5, so the instruction to submit lives in the
prompt and a missing submission is a fallback. The loop is append-only (thinking blocks are passed back as
returned), bounded by a turn and time budget, and never raises: every failure is an `AgentRun.failure`.
LangChain is imported lazily, so stub mode never loads it (ADR-0003).
"""

import json
import time
from collections.abc import Callable

from pydantic import BaseModel, Field

from rebooking_copilot.outcome import Confidence
from rebooking_copilot.reasoning import (
    PROMPT_PATH, PROMPT_VERSION, AgentCase, AgentDecision, AgentRun, UnavailableReasoner, call_tool, parse_answer,
    render_user_message,
)

DEFAULT_MODEL = "claude-sonnet-5-5"  # D-36
DEFAULT_EFFORT = "medium"  # D-36; Sonnet 5.5's own default is high, so it is set explicitly
MAX_TURNS = 6  # D-25
TIME_BUDGET_S = 30.0  # D-25
REQUEST_TIMEOUT_S = 20.0
REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"


# Tool schemas. The class names are the tool names; arguments are ids only (D-25).
class find_candidates(BaseModel):  # noqa: N801
    """List this booking's eligible offers (offer id and tier)."""

    pnr_id: str = Field(description="The booking's PNR locator, exactly as in FACTS.")


class check_policy(BaseModel):  # noqa: N801
    """Return an offer's tier, reasons and full rule trace for this booking."""

    pnr_id: str = Field(description="The booking's PNR locator.")
    offer_id: str = Field(description="An offer id from FACTS.")


class compute_saving(BaseModel):  # noqa: N801
    """Return the money breakdown for an offer: prices, change fees, net and counted saving, threshold, FX quote."""

    pnr_id: str = Field(description="The booking's PNR locator.")
    offer_id: str = Field(description="An offer id from FACTS.")


class get_fx_rate(BaseModel):  # noqa: N801
    """Return the FX quote that was used for this booking, if any."""

    from_currency: str = Field(description="ISO 4217 code, e.g. USD.")
    to_currency: str = Field(description="ISO 4217 code, e.g. EUR.")


class submit_recommendation(BaseModel):  # noqa: N801
    """Submit the final recommendation. Call exactly once, at the end."""

    chosen_offer_id: str | None = Field(description="An offer id from FACTS, or null for none.")
    decision: AgentDecision = Field(description="REBOOK, DO_NOT_REBOOK or NEEDS_REVIEW.")
    rationale: str = Field(description="Two to four sentences for the human agent. Only numbers that appear in FACTS or tool results.")
    confidence_ceiling: Confidence = Field(description="LOW, MEDIUM or HIGH; can only lower the system's confidence.")


TOOLS = [find_candidates, check_policy, compute_saving, get_fx_rate, submit_recommendation]


def chat_anthropic(model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT):
    """The production chat model. Credentials resolve the SDK's normal way (ANTHROPIC_API_KEY, `ant auth login`, ...)."""
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model,
        max_tokens=16_000,
        output_config={"effort": effort},
        default_request_timeout=REQUEST_TIMEOUT_S,
        max_retries=1,
        # Refusal fallback: if Sonnet 5.5 declines on safety grounds, the API re-runs the request on a fallback model.
        betas=[REFUSAL_FALLBACK_BETA],
        model_kwargs={"fallbacks": "default"},
    )


class ClaudeReasoner:
    def __init__(
        self,
        llm=None,
        *,
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
        max_turns: int = MAX_TURNS,
        time_budget_s: float = TIME_BUDGET_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.llm = llm if llm is not None else chat_anthropic(model, effort)
        self.id = f"claude:{model}"
        self.prompt_version = PROMPT_VERSION
        self.max_turns, self.time_budget_s, self.clock = max_turns, time_budget_s, clock

    def run(self, case: AgentCase) -> AgentRun:
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

        user = render_user_message(case)
        seen, trace = [user], []

        def fail(reason: str) -> AgentRun:
            return AgentRun(failure=reason, trace=tuple(trace), seen_text=tuple(seen))

        bound = self.llm.bind_tools(TOOLS, tool_choice="auto", strict=True)  # never forced: a 400 on Sonnet 5.5
        messages = [SystemMessage(PROMPT_PATH.read_text()), HumanMessage(user)]
        start = self.clock()
        for _ in range(self.max_turns):
            if self.clock() - start > self.time_budget_s:
                return fail(f"time budget exhausted ({self.time_budget_s:.0f} s)")
            try:
                reply = bound.invoke(messages)
            except Exception as exc:  # network, auth, rate limit, ...: none may crash the run
                return fail(f"api error: {type(exc).__name__}: {exc}")
            messages.append(reply)
            if reply.response_metadata.get("stop_reason") == "refusal":
                return fail("refusal: the model declined this request")
            if not reply.tool_calls:
                return fail("no submission: the model answered without calling submit_recommendation")
            results, submission = [], None
            for call in reply.tool_calls:
                trace.append(f"{call['name']}({json.dumps(call['args'], sort_keys=True)})")
                if call["name"] == "submit_recommendation":
                    submission = call["args"]
                    content = json.dumps({"status": "received"})
                else:
                    content = call_tool(case, call["name"], call["args"])
                    seen.append(content)
                results.append(ToolMessage(content=content, tool_call_id=call["id"]))
            if submission is not None:
                answer = parse_answer(submission)
                return fail(answer) if isinstance(answer, str) else AgentRun(answer=answer, trace=tuple(trace), seen_text=tuple(seen))
            messages.extend(results)
        return fail(f"turn budget exhausted ({self.max_turns} turns without a submission)")


def make_claude_reasoner() -> ClaudeReasoner | UnavailableReasoner:
    """Build the production reasoner, or explain why it can't run (missing extra, bad config, ...)."""
    try:
        return ClaudeReasoner()
    except Exception as exc:
        return UnavailableReasoner(f"{type(exc).__name__}: {exc}")
