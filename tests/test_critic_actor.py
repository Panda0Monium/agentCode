"""
critic_actor.

The load-bearing behaviour is the anti-sycophancy gate: an APPROVE verdict on
failing code must not end the episode.
"""

import pytest

from agents import critic_actor
from agents.base import AgentContext
from tests.fakes import FakeSession, ai, call, clean_lint, failing_tests, passing_tests
from tests.test_variants_wave1 import _patch_conv


STUB = {"src/solution.py": "def solve():\n    ...\n"}


def _done(n=1):
    return [ai(content="done") for _ in range(n)]


def _write(content="def solve():\n    return 42\n", _id="w"):
    return [ai(tool_calls=[call("write_file", _id=_id, path="src/solution.py", content=content)]),
            ai(content="written")]


# ------------------------------------------------------------------
# Verdict parsing
# ------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Looks good.\nVERDICT: APPROVE", "APPROVE"),
    ("Problems below.\nVERDICT: REVISE\n1. Fix the empty case", "REVISE"),
    ("verdict: approve", "APPROVE"),
    ("  VERDICT:   APPROVE  ", "APPROVE"),
])
def test_parse_verdict(text, expected):
    assert critic_actor.parse_verdict(text) == expected


def test_unparseable_verdict_defaults_to_revise():
    # Stopping on an ambiguous signal is the costly mistake; continuing is not.
    assert critic_actor.parse_verdict("I have some thoughts.") == "REVISE"
    assert critic_actor.parse_verdict("") == "REVISE"


# ------------------------------------------------------------------
# Control flow
# ------------------------------------------------------------------

def test_approval_on_passing_tests_ends_the_episode(monkeypatch):
    session = FakeSession(files=dict(STUB), test_results=[passing_tests(3)], lint_results=[clean_lint()])
    ctx = AgentContext(instruction="Implement solve().")

    _patch_conv(monkeypatch, critic_actor, session,
                tool_responses=_write(),
                text_responses=["Clean.\nVERDICT: APPROVE"])
    critic_actor.build(ctx)(session)

    kinds = session.note_kinds()
    assert kinds == ["phase", "critique"]           # exactly one round
    assert "approval_overridden" not in kinds


def test_approval_on_failing_tests_is_overridden(monkeypatch):
    # Without this gate the architecture is one ReAct pass plus a compliment.
    session = FakeSession(
        files=dict(STUB),
        test_results=[failing_tests(1, 2), passing_tests(3)],
        lint_results=[clean_lint()],
    )
    ctx = AgentContext(instruction="Implement solve().")

    _patch_conv(monkeypatch, critic_actor, session,
                tool_responses=_write(_id="a") + _write(_id="b"),
                text_responses=["Ship it.\nVERDICT: APPROVE",
                                "Now correct.\nVERDICT: APPROVE"])
    critic_actor.build(ctx)(session)

    kinds = session.note_kinds()
    assert "approval_overridden" in kinds
    assert kinds.count("phase") == 2                # it kept going


def test_revise_verdict_feeds_the_critique_into_the_next_round(monkeypatch):
    session = FakeSession(files=dict(STUB), test_results=[failing_tests(1, 2)], lint_results=[clean_lint()])
    ctx = AgentContext(instruction="Implement solve().", options={"max_rounds": 2})

    conv = _patch_conv(monkeypatch, critic_actor, session,
                       tool_responses=_write(_id="a") + _write(_id="b"),
                       text_responses=["VERDICT: REVISE\n1. Handle the empty list",
                                       "VERDICT: REVISE\n2. Still wrong"])
    critic_actor.build(ctx)(session)

    # The actor's second round must have been told what to change.
    prompts = " ".join(
        str(m.content) for call_msgs in conv.tool_llm.calls for m in call_msgs
    )
    assert "Handle the empty list" in prompts


def test_round_cap_is_respected(monkeypatch):
    session = FakeSession(files=dict(STUB), test_results=[failing_tests(0, 3)], lint_results=[clean_lint()])
    ctx = AgentContext(instruction="Implement solve().", options={"max_rounds": 2})

    _patch_conv(monkeypatch, critic_actor, session,
                tool_responses=_write(_id="a") + _write(_id="b"),
                text_responses=["VERDICT: REVISE", "VERDICT: REVISE"])
    critic_actor.build(ctx)(session)

    assert session.note_kinds().count("phase") == 2
    assert session.note_kinds().count("critique") == 2


def test_critic_never_gets_tools(monkeypatch):
    # A reviewer that can edit the code is not a reviewer.
    session = FakeSession(files=dict(STUB), test_results=[passing_tests(3)], lint_results=[clean_lint()])
    ctx = AgentContext(instruction="Implement solve().")

    conv = _patch_conv(monkeypatch, critic_actor, session,
                       tool_responses=_write(),
                       text_responses=["VERDICT: APPROVE"])
    critic_actor.build(ctx)(session)

    # The critique came from the tool-free client.
    assert len(conv.llm.calls) == 1
    assert conv.llm.exhausted


def test_registered_with_the_largest_time_multiplier():
    from agents import get_agent

    spec = get_agent("critic_actor")
    assert spec.time_multiplier >= 3.0
