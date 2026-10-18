"""Reasoner slice: stub rationales, routing (D-21), the Claude agent loop and its validator (D-07, D-16, D-22, D-25).

The agent is exercised through the real loop with a scripted fake chat model (no network, no key). Each adversarial
case must end in the deterministic fallback with a recorded reason.
"""

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from pydantic import Field

from factories import booking, fixture_inputs, load, offer, usd
from rebooking_copilot.agent import DEFAULT_EFFORT, DEFAULT_MODEL, ClaudeReasoner
from rebooking_copilot.decision import Action, Confidence, evaluate
from rebooking_copilot.policy import PolicyConfig, Reason, SettlementPolicy
from rebooking_copilot.reasoning import PROMPT_VERSION, UnavailableReasoner, is_faithful, numbers_in

REPO = Path(__file__).resolve().parents[1]


# --- scripted fake chat model ---------------------------------------------------------------------------------------

class ScriptedChatModel(GenericFakeChatModel):
    """Replays scripted AIMessages and records what it was sent. bind_tools is a no-op (tools aren't needed offline)."""

    sent: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.sent.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


_ids = iter(range(10_000))


def tool_call(name: str, **args) -> dict:
    return {"name": name, "args": args, "id": f"toolu_{next(_ids)}", "type": "tool_call"}


def ai(*calls, text: str = "", stop: str = "tool_use") -> AIMessage:
    return AIMessage(content=text, tool_calls=list(calls), response_metadata={"stop_reason": stop})


def submit(offer_id, decision, rationale, ceiling="HIGH") -> AIMessage:
    return ai(tool_call("submit_recommendation", chosen_offer_id=offer_id, decision=decision, rationale=rationale, confidence_ceiling=ceiling))


def agent(*script, **kwargs) -> ClaudeReasoner:
    return ClaudeReasoner(llm=ScriptedChatModel(messages=iter(script)), **kwargs)


def by_pnr(recs):
    return {r.pnr: r for r in recs}


def zc(**edits) -> dict:
    return booking("ZC3N1D", **edits)  # 640 USD, refundable, fee 0, threshold 32


def zc_clean(**edits) -> dict:
    return offer("OF-4001", refundable=True, **edits)  # same flight and product → CLEAN


FAITHFUL_ZC = "AV24 is the same flight for 500.00 USD instead of 640.00 USD, a net saving of 140.00 USD, but the new fare is non-refundable."


# --- stub mode: rationales ----------------------------------------------------------------------------------------------

def test_every_stub_recommendation_has_a_faithful_rationale():
    for rec in evaluate(*fixture_inputs()):
        assert rec.rationale, rec.pnr
        assert rec.reasoner == "stub" and rec.fallback_reason is None
        assert is_faithful(rec.rationale, [rec.model_dump_json(exclude={"rationale"})]), (rec.pnr, rec.rationale)


def test_stub_rationales_say_why():
    recs = by_pnr(evaluate(*fixture_inputs()))
    assert "travel credit" in recs["QX7T2A"].rationale and "80.00 USD" in recs["QX7T2A"].rationale
    assert "252.04 EUR" in recs["RT5K8B"].rationale and "0.9276" in recs["RT5K8B"].rationale
    assert "refundab" in recs["ZC3N1D"].rationale
    assert "bag" in recs["LM9P4C"].rationale


# --- routing (D-21) ---------------------------------------------------------------------------------------------------

class RecordingReasoner:
    id = "recording"
    prompt_version = "test"

    def __init__(self):
        self.seen = []

    def run(self, case):
        self.seen.append(case.pnr.pnr)
        from rebooking_copilot.reasoning import AgentRun
        return AgentRun(answer=None, failure="recording only", trace=(), seen_text=())


def test_only_review_level_or_multi_offer_bookings_reach_the_agent():
    reasoner = RecordingReasoner()
    recs = by_pnr(evaluate(*fixture_inputs(), reasoner=reasoner))
    assert reasoner.seen == ["ZC3N1D"]  # the only fixture booking with a review-level eligible offer
    assert recs["ZC3N1D"].fallback_reason == "recording only"
    golden = by_pnr(evaluate(*fixture_inputs()))
    for locator in ["QX7T2A", "LM9P4C", "RT5K8B", "HB6W9E"]:
        assert recs[locator].model_dump(exclude={"rationale"}) == golden[locator].model_dump(exclude={"rationale"})


def test_two_clean_offers_reach_the_agent():
    reasoner = RecordingReasoner()
    evaluate(*load([zc()], [zc_clean(), zc_clean(offer_id="OF-4002", price="560.00")]), reasoner=reasoner)
    assert reasoner.seen == ["ZC3N1D"]


def test_a_single_clean_offer_stays_deterministic():
    reasoner = RecordingReasoner()
    (rec,) = evaluate(*load([zc()], [zc_clean()]), reasoner=reasoner)
    assert reasoner.seen == [] and rec.action is Action.REBOOK and rec.reasoner == "stub"


# --- the agent decides inside the eligible set -----------------------------------------------------------------------

def test_agent_can_approve_a_review_level_offer_capped_at_medium():
    script = (
        ai(tool_call("check_policy", pnr_id="ZC3N1D", offer_id="OF-4001")),
        ai(tool_call("compute_saving", pnr_id="ZC3N1D", offer_id="OF-4001")),
        submit("OF-4001", "REBOOK", FAITHFUL_ZC),
    )
    rec = by_pnr(evaluate(*fixture_inputs(), reasoner=agent(*script)))["ZC3N1D"]
    assert (rec.action, rec.chosen_offer_id, rec.estimated_net_saving) == (Action.REBOOK, "OF-4001", usd("140.00"))
    assert rec.confidence is Confidence.MEDIUM  # review-level cap (D-16), although 140 ≥ 64 would be HIGH
    assert Reason.REFUNDABILITY_LOST in rec.reasons
    assert rec.reasoner == f"claude:{DEFAULT_MODEL}" and rec.prompt_version == PROMPT_VERSION
    assert rec.rationale == FAITHFUL_ZC and rec.fallback_reason is None
    assert [t.split("(")[0] for t in rec.agent_trace] == ["check_policy", "compute_saving", "submit_recommendation"]


def test_agent_can_send_to_review():
    rec = by_pnr(evaluate(*fixture_inputs(), reasoner=agent(submit("OF-4001", "NEEDS_REVIEW", FAITHFUL_ZC))))["ZC3N1D"]
    assert (rec.action, rec.chosen_offer_id, rec.confidence) == (Action.NEEDS_REVIEW, "OF-4001", Confidence.LOW)


def test_agent_can_decline_when_only_review_level_offers_exist():
    rec = by_pnr(evaluate(*fixture_inputs(), reasoner=agent(submit(None, "DO_NOT_REBOOK", "Losing refundability is not worth it here."))))["ZC3N1D"]
    assert (rec.action, rec.chosen_offer_id, rec.estimated_net_saving) == (Action.DO_NOT_REBOOK, None, None)
    assert rec.confidence is Confidence.MEDIUM and Reason.REFUNDABILITY_LOST in rec.reasons


def test_confidence_ceiling_can_only_lower():
    offers = [zc_clean(), offer("OF-4001", offer_id="OF-4002", price="450.00")]  # clean 140 · review-level 190
    (rec,) = evaluate(*load([zc()], offers), reasoner=agent(submit("OF-4001", "REBOOK", "Same flight and product, 140.00 USD cheaper.", ceiling="LOW")))
    assert (rec.action, rec.chosen_offer_id, rec.confidence) == (Action.REBOOK, "OF-4001", Confidence.LOW)  # HIGH by code, LOW by ceiling
    (rec,) = evaluate(*load([zc()], [zc_clean(price="580.00"), offer("OF-4001", offer_id="OF-4002", price="450.00")]),
                      reasoner=agent(submit("OF-4001", "REBOOK", "Same flight, 60.00 USD cheaper.", ceiling="HIGH")))
    assert rec.confidence is Confidence.MEDIUM  # 60 < 64 → MEDIUM by code; a HIGH ceiling cannot raise it


def test_agent_may_prefer_a_review_level_offer_over_a_clean_one():
    offers = [zc_clean(price="600.00"), offer("OF-4001", offer_id="OF-4002", price="450.00")]  # clean 40 · review 190
    (rec,) = evaluate(*load([zc()], offers), reasoner=agent(submit("OF-4002", "REBOOK", "OF-4002 saves 190.00 USD; refundability is lost.")))
    assert (rec.action, rec.chosen_offer_id, rec.estimated_net_saving, rec.confidence) == (Action.REBOOK, "OF-4002", usd("190.00"), Confidence.MEDIUM)
    assert rec.alternatives == ("OF-4001",)


def test_agent_declining_a_clean_rebook_escalates_to_review():
    # D-22: a clean offer above the threshold exists, the agent says no → NEEDS_REVIEW + LLM_DISAGREES_WITH_POLICY,
    # with the clean offer shown so the missed saving stays visible.
    offers = [zc_clean(), offer("OF-4001", offer_id="OF-4002", price="450.00")]
    (rec,) = evaluate(*load([zc()], offers), reasoner=agent(submit(None, "DO_NOT_REBOOK", "Not worth it.")))
    assert (rec.action, rec.chosen_offer_id, rec.estimated_net_saving, rec.confidence) == (Action.NEEDS_REVIEW, "OF-4001", usd("140.00"), Confidence.LOW)
    assert Reason.LLM_DISAGREES_WITH_POLICY in rec.reasons


# --- adversarial: every bad answer falls back to the deterministic decision ------------------------------------------

def _zc_fallback(*script, **kwargs):
    rec = by_pnr(evaluate(*fixture_inputs(), reasoner=agent(*script, **kwargs)))["ZC3N1D"]
    golden = by_pnr(evaluate(*fixture_inputs()))["ZC3N1D"]
    assert (rec.action, rec.chosen_offer_id, rec.estimated_net_saving, rec.confidence, rec.reasons) == (
        golden.action, golden.chosen_offer_id, golden.estimated_net_saving, golden.confidence, golden.reasons
    )
    assert rec.reasoner == "stub" and rec.fallback_reason
    return rec


@pytest.mark.parametrize(
    "script, expected_reason",
    [
        ((submit("OF-9999", "REBOOK", "OF-9999 is cheaper."),), "eligible"),
        ((submit("OF-5001", "REBOOK", "OF-5001 is cheaper."),), "eligible"),  # a real offer, but not this booking's
        ((submit("OF-4001", "REBOOK", "It saves 999.00 USD."),), "unfaithful"),
        ((ai(tool_call("submit_recommendation", chosen_offer_id="OF-4001", decision="MAYBE", rationale="x", confidence_ceiling="HIGH")),), "invalid"),
        ((ai(tool_call("submit_recommendation", decision="REBOOK")),), "invalid"),
        ((submit(None, "REBOOK", "Rebook."),), "eligible"),
        ((ai(text="I think you should rebook.", stop="end_turn"),), "no submission"),
        ((ai(stop="refusal"),), "refusal"),
        (tuple(ai(tool_call("check_policy", pnr_id="ZC3N1D", offer_id="OF-4001")) for _ in range(6)), "turn budget"),
    ],
    ids=["unknown-offer", "other-bookings-offer", "invented-number", "bad-enum", "missing-fields", "rebook-without-offer",
         "text-only", "refusal", "turn-budget"],
)
def test_bad_agent_answers_fall_back(script, expected_reason):
    rec = _zc_fallback(*script)
    assert expected_reason in rec.fallback_reason


def test_time_budget_falls_back():
    ticks = iter([0.0, 31.0, 62.0])
    rec = _zc_fallback(ai(tool_call("check_policy", pnr_id="ZC3N1D", offer_id="OF-4001")), submit("OF-4001", "REBOOK", FAITHFUL_ZC),
                       clock=lambda: next(ticks))
    assert "time budget" in rec.fallback_reason


class _Exploding(ScriptedChatModel):
    def _generate(self, *args, **kwargs):
        raise ConnectionError("network down")


def test_api_errors_fall_back():
    rec = by_pnr(evaluate(*fixture_inputs(), reasoner=ClaudeReasoner(llm=_Exploding(messages=iter([])))))["ZC3N1D"]
    assert rec.reasoner == "stub" and "network down" in rec.fallback_reason and rec.action is Action.NEEDS_REVIEW


def test_tool_argument_abuse_gets_an_error_not_data():
    script = (
        ai(tool_call("compute_saving", pnr_id="QX7T2A", offer_id="OF-1001"), tool_call("check_policy", pnr_id="ZC3N1D", offer_id="OF-1001")),
        submit("OF-4001", "NEEDS_REVIEW", FAITHFUL_ZC),
    )
    reasoner = agent(*script)
    rec = by_pnr(evaluate(*fixture_inputs(), reasoner=reasoner))["ZC3N1D"]
    assert rec.action is Action.NEEDS_REVIEW and rec.fallback_reason is None
    tool_results = [m.content for m in reasoner.llm.sent[1] if m.type == "tool"]
    assert len(tool_results) == 2 and all("error" in json.loads(r) for r in tool_results)
    assert "480" not in "".join(tool_results)  # another booking's data is never returned


def test_credit_under_cash_only_can_never_be_approved():
    # QX7T2A with two clean offers routes to the agent; non-refundable → credit → cash_only forbids REBOOK.
    offers = [offer("OF-1001"), offer("OF-1001", offer_id="OF-1002", price="320.00")]
    (rec,) = evaluate(*load([booking("QX7T2A")], offers), reasoner=agent(submit("OF-1001", "REBOOK", "Same flight, 80.00 USD net.")))
    assert rec.action is Action.NEEDS_REVIEW and Reason.SAVING_AS_CREDIT in rec.reasons
    assert "policy" in rec.fallback_reason


def test_agent_cannot_take_a_seat_another_booking_holds():
    # Both bookings hold the clean OF-4001 (5 seats) after the ledger. OF-4002 (review-level, 450, 1 seat) is free.
    # ZC2T7H's agent (index 0) takes OF-4002 (700 − 450 = 250). ZC3N1D's agent then also asks for OF-4002, but the
    # seat is gone → fallback "no seats left"; it is still routed because OF-4003 (review-level, 480) is offered.
    bookings = [zc(pnr="ZC2T7H", price="700.00"), zc()]
    offers = [zc_clean(seats=5), offer("OF-4001", offer_id="OF-4002", price="450.00", seats=1), offer("OF-4001", offer_id="OF-4003", price="480.00")]
    script = (submit("OF-4002", "REBOOK", "OF-4002 saves 250.00 USD."), submit("OF-4002", "REBOOK", "OF-4002 saves 190.00 USD."))
    other, z = evaluate(*load(bookings, offers), reasoner=agent(*script))
    assert (other.action, other.chosen_offer_id, other.estimated_net_saving) == (Action.REBOOK, "OF-4002", usd("250.00"))
    assert z.chosen_offer_id == "OF-4001" and z.reasoner == "stub" and "seat" in z.fallback_reason
    assert [r.chosen_offer_id for r in (other, z) if r.action is Action.REBOOK].count("OF-4002") == 1


def test_unavailable_claude_falls_back_for_routed_bookings_only():
    recs = by_pnr(evaluate(*fixture_inputs(), reasoner=UnavailableReasoner("no credentials")))
    assert recs["ZC3N1D"].fallback_reason == "claude unavailable: no credentials"
    assert all(recs[p].fallback_reason is None for p in ["QX7T2A", "LM9P4C", "RT5K8B", "HB6W9E"])


# --- what the model is sent ---------------------------------------------------------------------------------------------

def test_the_agent_sees_delimited_facts_and_the_versioned_prompt():
    reasoner = agent(submit("OF-4001", "NEEDS_REVIEW", FAITHFUL_ZC))
    evaluate(*fixture_inputs(), reasoner=reasoner)
    system, user = reasoner.llm.sent[0][0], reasoner.llm.sent[0][1]
    prompt = (REPO / "src/rebooking_copilot/prompts" / f"{PROMPT_VERSION}.md").read_text()
    assert system.content == prompt
    assert "<facts>" in user.content and "</facts>" in user.content
    facts = json.loads(user.content.split("<facts>")[1].split("</facts>")[0])
    assert facts["booking"]["pnr"] == "ZC3N1D"
    assert [o["offer_id"] for o in facts["eligible_offers"]] == ["OF-4001"]


def test_claude_defaults_match_the_recorded_decision():
    assert (DEFAULT_MODEL, DEFAULT_EFFORT) == ("claude-sonnet-5-5", "medium")


# --- faithfulness checker --------------------------------------------------------------------------------------------

def test_numbers_are_normalised():
    assert numbers_in("140.00 USD, 1,947.96 EUR and 22:05") == {Decimal("140"), Decimal("1947.96"), Decimal("22"), Decimal("5")}


def test_faithfulness():
    assert is_faithful("Saves 140 USD.", ['{"net": "140.00 USD"}'])
    assert not is_faithful("Saves 141 USD.", ['{"net": "140.00 USD"}'])
    assert is_faithful("No numbers at all.", [])


# --- stub mode never imports LangChain (D-00d, ADR-0003) -----------------------------------------------------------

def test_stub_mode_does_not_import_langchain(tmp_path):
    code = (
        "import sys; from rebooking_copilot.cli import main; "
        f"rc = main(['--out', {str(tmp_path / 'r.json')!r}]); "
        "assert rc == 0; assert not [m for m in sys.modules if m.startswith(('langchain', 'anthropic'))], 'LLM libs imported'"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
