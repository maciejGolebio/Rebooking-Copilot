"""Claude mode: an explicit tool-calling loop on LangChain primitives (D-19, D-20, D-38, ADR-0009).

`ChatAnthropic` (langchain-anthropic, which calls the official Anthropic SDK) with `bind_tools(tool_choice="auto",
strict=True)`. Forced tool choice is rejected by Claude Sonnet 5.5, so the instruction to submit lives in the
prompt, a text-only reply gets one reminder, and a missing submission is a fallback. The loop is append-only
(thinking blocks are passed back as returned), bounded by a turn and time budget, and never raises: every failure
is an `AgentRun.failure`. LangChain is imported lazily, so stub mode never loads it (ADR-0003).
"""

import hashlib
import json
import os
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
TIME_BUDGET_S = 30.0  # D-25: a call starts only if a full request timeout still fits, so the total stays within it
REQUEST_TIMEOUT_S = 10.0
MAX_TOKENS = 16_000
REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"
REMINDER = "Call submit_recommendation now with your decision. Do not answer in plain text."


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

    chosen_offer_id: str | None = Field(description="REBOOK: the offer to book. NEEDS_REVIEW: the offer a human should look at, or null. DO_NOT_REBOOK: null.")
    decision: AgentDecision = Field(description="REBOOK, DO_NOT_REBOOK or NEEDS_REVIEW.")
    rationale: str = Field(description="Two to four sentences for the human agent. Amounts only as copied from FACTS, with their currency.")
    confidence_ceiling: Confidence = Field(description="LOW, MEDIUM or HIGH; can only lower the system's confidence.")


TOOLS = [find_candidates, check_policy, compute_saving, get_fx_rate, submit_recommendation]


def chat_anthropic(model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT):
    """The production chat model. Needs ANTHROPIC_API_KEY: ChatAnthropic passes the key explicitly, so `ant auth`
    profiles aren't used (D-41)."""
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model,
        max_tokens=MAX_TOKENS,
        output_config={"effort": effort},
        default_request_timeout=REQUEST_TIMEOUT_S,
        max_retries=0,  # the loop's budget and the deterministic fallback replace retries
        # Refusal fallback: if Sonnet 5.5 declines on safety grounds, the API re-runs the request on a fallback model.
        # Top-level cache_control caches the stable system prompt + tools across turns and bookings.
        betas=[REFUSAL_FALLBACK_BETA],
        model_kwargs={"fallbacks": "default", "cache_control": {"type": "ephemeral"}},
    )


def _resendable(reply):
    """LangChain stores the SDK's fallback block with the Python field name `from_`; the API expects `from` (D-41)."""
    if not isinstance(reply.content, list):
        return reply
    fixed = [
        {("from" if k == "from_" else k): v for k, v in block.items()} if isinstance(block, dict) and "from_" in block else block
        for block in reply.content
    ]
    return reply.model_copy(update={"content": fixed}) if fixed != reply.content else reply


class ClaudeReasoner:
    def __init__(
        self,
        llm=None,
        *,
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
        max_turns: int = MAX_TURNS,
        time_budget_s: float = TIME_BUDGET_S,
        request_timeout_s: float = REQUEST_TIMEOUT_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.llm = llm if llm is not None else chat_anthropic(model, effort)
        self.id = f"claude:{model}"
        self.prompt_version = PROMPT_VERSION
        prompt = PROMPT_PATH.read_text()
        self.config = {"model": model, "effort": effort, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
        self.max_turns, self.time_budget_s, self.request_timeout_s, self.clock = max_turns, time_budget_s, request_timeout_s, clock

    def run(self, case: AgentCase) -> AgentRun:
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

        trace, calls, served = [], [], None
        reminded = False

        def fail(reason: str) -> AgentRun:
            return AgentRun(failure=reason, trace=tuple(trace), calls=tuple(calls), served_model=served)

        bound = self.llm.bind_tools(TOOLS, tool_choice="auto", strict=True)  # never forced: a 400 on Sonnet 5.5
        messages = [SystemMessage(PROMPT_PATH.read_text()), HumanMessage(render_user_message(case))]
        start = self.clock()
        for _ in range(self.max_turns):
            if self.time_budget_s - (self.clock() - start) < self.request_timeout_s:
                return fail(f"time budget exhausted ({self.time_budget_s:.0f} s)")
            t0 = time.monotonic()
            try:
                reply = bound.invoke(messages)
            except Exception as exc:  # network, auth, rate limit, ...: none may crash the run
                return fail(f"api error: {type(exc).__name__}: {exc}")
            meta = reply.response_metadata or {}
            stop = meta.get("stop_reason")
            served = meta.get("model") or served
            usage = meta.get("usage") or {}
            calls.append(f"model={served} stop={stop} in={usage.get('input_tokens')} out={usage.get('output_tokens')} ms={int((time.monotonic() - t0) * 1000)}")
            messages.append(_resendable(reply))
            if stop == "refusal":
                category = (meta.get("stop_details") or {}).get("category")
                return fail(f"refusal: the model declined this request (category: {category})")
            if stop == "max_tokens":
                return fail("max_tokens: the reply was cut off before a complete submission")
            if not reply.tool_calls:
                if reminded:
                    return fail("no submission: the model answered in text twice without calling submit_recommendation")
                reminded = True
                messages.append(HumanMessage(REMINDER))
                continue
            results, submission = [], None
            for call in reply.tool_calls:
                trace.append(f"{call['name']}({json.dumps(call['args'], sort_keys=True)})")
                if call["name"] == "submit_recommendation":
                    submission = call["args"]
                    content, is_error = json.dumps({"status": "received"}), False
                else:
                    content, is_error = call_tool(case, call["name"], call["args"])
                results.append(ToolMessage(content=content, tool_call_id=call["id"], status="error" if is_error else "success"))
            if submission is not None:
                answer = parse_answer(submission)
                if isinstance(answer, str):
                    return fail(answer)
                return AgentRun(answer=answer, trace=tuple(trace), calls=tuple(calls), served_model=served)
            messages.extend(results)
        return fail(f"turn budget exhausted ({self.max_turns} turns without a submission)")


def make_claude_reasoner() -> ClaudeReasoner | UnavailableReasoner:
    """Build the production reasoner, or explain why it can't run (missing key, missing extra, bad config, ...)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return UnavailableReasoner("ANTHROPIC_API_KEY is not set (LangChain's ChatAnthropic doesn't read `ant auth` profiles)")
    try:
        return ClaudeReasoner()
    except Exception as exc:
        return UnavailableReasoner(f"{type(exc).__name__}: {exc}")
