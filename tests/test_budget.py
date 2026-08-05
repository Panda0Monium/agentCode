from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from agents import build_agent
from agents.base import AgentContext, Conversation, run_tool_loop
from agents.budget import (
    DEFAULT_TOKEN_BUDGET,
    DIFFICULTY_TOKEN_BUDGETS,
    Budget,
    BudgetExhausted,
    default_budget_for,
)
from tests.fakes import FakeLLM, FakeSession, ai, call


def _task(**kw):
    base = dict(
        instruction="Implement the thing.",
        name="demo-task",
        difficulty="medium",
        language="python",
        timeout_sec=300.0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _resp(content="ok", usage_metadata=None, response_metadata=None):
    msg = ai(content=content)
    if usage_metadata is not None:
        msg.usage_metadata = usage_metadata
    if response_metadata is not None:
        msg.response_metadata = response_metadata
    return msg


# ------------------------------------------------------------------
# The three usage sources
# ------------------------------------------------------------------

def test_charges_from_usage_metadata_when_available():
    b = Budget(max_tokens=1000)
    usage = b.charge(_resp(usage_metadata={"input_tokens": 30, "output_tokens": 12}))
    assert usage["source"] == "usage_metadata"
    assert (b.input_tokens, b.output_tokens, b.total_tokens) == (30, 12, 42)


def test_falls_back_to_response_metadata():
    b = Budget(max_tokens=1000)
    usage = b.charge(_resp(response_metadata={"token_usage": {"prompt_tokens": 7, "completion_tokens": 3}}))
    assert usage["source"] == "response_metadata"
    assert b.total_tokens == 10


def test_estimates_when_the_provider_reports_nothing():
    # A silent zero here would make budgets a no-op against providers with
    # patchy usage reporting — exactly where a runaway loop is most likely.
    b = Budget(max_tokens=1000)
    usage = b.charge(_resp(content="x" * 40), messages=[HumanMessage(content="y" * 80)])
    assert usage["source"] == "estimated"
    assert b.output_tokens == 10  # 40 chars / 4
    assert b.input_tokens == 20   # 80 chars / 4
    assert b.total_tokens > 0


def test_sources_are_tallied_so_zero_is_distinguishable_from_unreported():
    b = Budget(max_tokens=1000)
    b.charge(_resp(usage_metadata={"input_tokens": 1, "output_tokens": 1}))
    b.charge(_resp(content="abcd"))
    assert b.sources == {"usage_metadata": 1, "estimated": 1}


# ------------------------------------------------------------------
# Limits
# ------------------------------------------------------------------

def test_unlimited_budget_never_raises():
    b = Budget(max_tokens=None)
    b.charge(_resp(usage_metadata={"input_tokens": 10**9, "output_tokens": 0}))
    b.check()
    assert b.remaining == float("inf")


def test_check_raises_once_the_allowance_is_gone():
    b = Budget(max_tokens=50)
    b.check()  # fine at zero
    b.charge(_resp(usage_metadata={"input_tokens": 40, "output_tokens": 20}))
    with pytest.raises(BudgetExhausted):
        b.check()
    assert b.exhausted is True
    assert b.remaining == 0


def test_snapshot_is_serializable_and_complete():
    b = Budget(max_tokens=100)
    b.charge(_resp(usage_metadata={"input_tokens": 5, "output_tokens": 5}))
    snap = b.snapshot()
    assert snap["total_tokens"] == 10
    assert snap["max_tokens"] == 100
    assert snap["calls"] == 1
    assert snap["exhausted"] is False


# ------------------------------------------------------------------
# Defaults and precedence
# ------------------------------------------------------------------

@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
def test_difficulty_drives_the_default(difficulty):
    assert default_budget_for(_task(difficulty=difficulty)) == DIFFICULTY_TOKEN_BUDGETS[difficulty]


def test_unknown_difficulty_falls_back_to_the_global_default():
    assert default_budget_for(_task(difficulty="impossible")) == DEFAULT_TOKEN_BUDGET


def test_task_max_tokens_beats_the_difficulty_table():
    assert default_budget_for(_task(difficulty="easy", max_tokens=7777)) == 7777


def test_explicit_override_beats_everything():
    agent = build_agent("react", _task(difficulty="easy", max_tokens=7777), max_tokens=123)
    assert agent.budget.max_tokens == 123


def test_budget_is_attached_and_defaulted_from_the_task():
    agent = build_agent("react", _task(difficulty="hard"))
    assert agent.budget.max_tokens == DIFFICULTY_TOKEN_BUDGETS["hard"]


# ------------------------------------------------------------------
# Integration: exhaustion ends the episode cleanly
# ------------------------------------------------------------------

def test_conversation_charges_every_call_and_records_usage_in_the_trajectory():
    session = FakeSession()
    llm = FakeLLM([_resp(usage_metadata={"input_tokens": 10, "output_tokens": 5})])
    budget = Budget(max_tokens=1000)
    conv = Conversation(session, budget=budget, llm=llm, tool_llm=llm)

    conv.invoke([HumanMessage(content="hi")])

    assert budget.total_tokens == 15
    action = session.trajectory[0]
    assert action.result["usage"]["input_tokens"] == 10


def test_all_subloops_share_one_budget():
    # This is the whole point: a multi-round architecture must not get a fresh
    # allowance per sub-loop, or expensive variants become uncomparable.
    session = FakeSession()
    budget = Budget(max_tokens=1000)
    responses = [_resp(usage_metadata={"input_tokens": 10, "output_tokens": 0}) for _ in range(4)]
    llm = FakeLLM(responses)
    conv = Conversation(session, budget=budget, llm=llm, tool_llm=llm)

    for _ in range(2):  # two separate "phases" of some architecture
        conv.invoke([HumanMessage(content="a")])
        conv.invoke([HumanMessage(content="b")], tools=False)

    assert budget.calls == 4
    assert budget.total_tokens == 40


def test_exhaustion_stops_the_loop_before_spending_more():
    session = FakeSession()
    budget = Budget(max_tokens=20)
    responses = [
        ai(tool_calls=[call("run_tests", _id=f"c{i}")]) for i in range(5)
    ]
    for r in responses:
        r.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
    llm = FakeLLM(responses)
    conv = Conversation(session, budget=budget, llm=llm, tool_llm=llm)

    with pytest.raises(BudgetExhausted):
        run_tool_loop(conv, [HumanMessage(content="go")], max_turns=10)

    # Two calls fit (15 then 30 > 20 trips the check before the third).
    assert budget.calls == 2
    assert len(llm.responses) == 3


def test_wrapped_agent_swallows_exhaustion_so_the_episode_still_grades():
    # If BudgetExhausted escaped, run_episode would record it as agent_error
    # and the run would read as a crash rather than a completed-but-capped run.
    from agents import _wrap_graceful

    ctx = AgentContext(instruction="x", budget=Budget(max_tokens=10))

    def inner(session):
        raise BudgetExhausted("out of tokens")

    session = FakeSession()
    _wrap_graceful(inner, ctx)(session)  # must not raise

    assert ctx.budget.exhausted is True
    assert session.note_kinds() == ["budget_exhausted"]
