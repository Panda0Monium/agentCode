"""
reflexion and tdd.

The behaviours worth pinning here are the ones that would silently corrupt the
benchmark if they regressed: reflexion trusting the model instead of the
harness, and tdd leaving lint-costing scratch files behind.
"""

import pytest

from agents import reflexion, tdd
from agents.base import AgentContext
from tests.fakes import (
    FakeLLM,
    FakeSession,
    ai,
    call,
    clean_lint,
    dirty_lint,
    failing_tests,
    passing_tests,
)
from tests.test_variants_wave1 import ScriptedConversation, _patch_conv


STUB = {"src/solution.py": "def solve():\n    ...\n"}


def _done(n=1):
    return [ai(content="done") for _ in range(n)]


# ------------------------------------------------------------------
# Reflexion
# ------------------------------------------------------------------

def test_reflexion_stops_as_soon_as_the_harness_says_it_is_solved(monkeypatch):
    session = FakeSession(files=dict(STUB), test_results=[passing_tests(3)], lint_results=[clean_lint()])
    ctx = AgentContext(instruction="Implement solve().")

    _patch_conv(monkeypatch, reflexion, session, tool_responses=_done(1), text_responses=[])
    reflexion.build(ctx)(session)

    kinds = session.note_kinds()
    assert kinds == ["attempt", "attempt"]          # started, then solved
    assert "reflection" not in kinds                 # nothing to reflect on


def test_reflexion_reflects_and_retries_after_a_failure(monkeypatch):
    session = FakeSession(
        files=dict(STUB),
        test_results=[failing_tests(1, 2), passing_tests(3)],
        lint_results=[clean_lint()],
    )
    ctx = AgentContext(instruction="Implement solve().")

    _patch_conv(
        monkeypatch, reflexion, session,
        tool_responses=_done(2),                     # two attempts
        text_responses=["solve() mishandles the empty case."],
    )
    reflexion.build(ctx)(session)

    kinds = session.note_kinds()
    assert kinds.count("reflection") == 1
    assert kinds.count("attempt") == 3               # attempt 1, attempt 2, solved
    reflection = next(a for a in session.trajectory
                      if a.tool == "agent_note" and a.args["kind"] == "reflection")
    assert "empty case" in reflection.args["text"]


def test_reflexion_uses_harness_ground_truth_not_the_models_claim(monkeypatch):
    # The model insists it is finished; the harness says two tests fail. The
    # architecture must believe the harness, or the loop is worthless.
    session = FakeSession(
        files=dict(STUB),
        test_results=[failing_tests(1, 2)],
        lint_results=[clean_lint()],
    )
    ctx = AgentContext(instruction="Implement solve().")

    _patch_conv(
        monkeypatch, reflexion, session,
        tool_responses=[ai(content="All tests pass, I am done.") for _ in range(3)],
        text_responses=["Still broken.", "Still broken again."],
    )
    reflexion.build(ctx)(session)

    assert session.note_kinds().count("attempt") == 3   # it kept trying
    assert session.note_kinds().count("reflection") == 2


def test_reflexion_treats_lint_errors_as_not_solved(monkeypatch):
    session = FakeSession(
        files=dict(STUB),
        test_results=[passing_tests(3)],
        lint_results=[dirty_lint(2), clean_lint()],
    )
    ctx = AgentContext(instruction="Implement solve().")

    _patch_conv(monkeypatch, reflexion, session,
                tool_responses=_done(2), text_responses=["Unused import."])
    reflexion.build(ctx)(session)

    assert "reflection" in session.note_kinds()


def test_reflexion_respects_its_attempt_cap(monkeypatch):
    session = FakeSession(files=dict(STUB), test_results=[failing_tests(0, 3)], lint_results=[clean_lint()])
    ctx = AgentContext(instruction="Implement solve().", options={"max_attempts": 2})

    _patch_conv(monkeypatch, reflexion, session,
                tool_responses=_done(2), text_responses=["nope"])
    reflexion.build(ctx)(session)

    assert session.note_kinds().count("attempt") == 2
    # No reflection after the final attempt — nothing would consume it.
    assert session.note_kinds().count("reflection") == 1


def test_reflexion_carries_reflections_into_later_attempts(monkeypatch):
    session = FakeSession(files=dict(STUB), test_results=[failing_tests(0, 3)], lint_results=[clean_lint()])
    ctx = AgentContext(instruction="Implement solve().", options={"max_attempts": 3})

    conv = _patch_conv(monkeypatch, reflexion, session,
                       tool_responses=_done(3), text_responses=["First lesson.", "Second lesson."])
    reflexion.build(ctx)(session)

    # The third attempt's system messages must mention the earlier lessons.
    last_call = conv.tool_llm.calls[-1]
    system_text = " ".join(str(m.content) for m in last_call if getattr(m, "type", None) == "system")
    assert "First lesson." in system_text


# ------------------------------------------------------------------
# TDD
# ------------------------------------------------------------------

def _tdd_script(extra_impl=None):
    """Write a scratch test, then implement, then verify."""
    return (
        [ai(tool_calls=[call("write_file", _id="t1", path="tests/agent/test_extra.py",
                             content="def test_x():\n    assert True\n")]),
         ai(content="tests written")]
        + (extra_impl or [ai(tool_calls=[call("write_file", _id="i1", path="src/solution.py",
                                              content="def solve():\n    return 42\n")]),
                          ai(content="implemented")])
        + _done(1)
    )


def test_tdd_writes_tests_first_then_implements(monkeypatch):
    session = FakeSession(files=dict(STUB))
    ctx = AgentContext(instruction="Implement solve().")

    _patch_conv(monkeypatch, tdd, session, tool_responses=_tdd_script(), text_responses=[])
    tdd.build(ctx)(session)

    writes = [a.args["path"] for a in session.trajectory if a.tool == "write_file"]
    assert writes[0].startswith("tests/agent/")     # tests came first
    assert "src/solution.py" in writes


def test_tdd_removes_its_scratch_tests_before_grading(monkeypatch):
    # ruff runs at the repo root during grading, so leaving these behind costs
    # 5% of lint_score per violation — for work the agent was asked to do.
    session = FakeSession(files=dict(STUB))
    ctx = AgentContext(instruction="Implement solve().")

    _patch_conv(monkeypatch, tdd, session, tool_responses=_tdd_script(), text_responses=[])
    tdd.build(ctx)(session)

    assert not [p for p in session.files if p.startswith("tests/agent")]
    assert "cleanup" in session.note_kinds()
    assert "src/solution.py" in session.files       # real work untouched


def test_tdd_records_a_red_baseline_from_the_harness(monkeypatch):
    session = FakeSession(files=dict(STUB), test_results=[failing_tests(0, 3), passing_tests(3)])
    ctx = AgentContext(instruction="Implement solve().")

    _patch_conv(monkeypatch, tdd, session, tool_responses=_tdd_script(), text_responses=[])
    tdd.build(ctx)(session)

    phases = [a for a in session.trajectory
              if a.tool == "agent_note" and a.args["kind"] == "phase"]
    assert phases and "Baseline" in phases[0].args["text"]


def test_tdd_survives_writing_no_scratch_tests(monkeypatch):
    session = FakeSession(files=dict(STUB))
    ctx = AgentContext(instruction="Implement solve().")

    _patch_conv(monkeypatch, tdd, session,
                tool_responses=_done(1) + _done(1) + _done(1), text_responses=[])
    tdd.build(ctx)(session)

    note = next(a for a in session.trajectory
                if a.tool == "agent_note" and a.args["kind"] == "test_plan")
    assert note.args["files"] == 0
    assert "cleanup" not in session.note_kinds()    # nothing to clean


# ------------------------------------------------------------------
# Wall-clock
# ------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("react", 300.0),
    ("reflexion", 600.0),
    ("tdd", 600.0),
])
def test_time_multiplier_scales_the_session_timeout(name, expected):
    from types import SimpleNamespace

    from agents import build_agent

    task = SimpleNamespace(instruction="x", name="t", difficulty="medium",
                           language="python", timeout_sec=300.0)
    assert build_agent(name, task).suggested_timeout_sec == expected


def test_session_accepts_a_timeout_override():
    from types import SimpleNamespace

    from environment.session import Session

    # from_task needs Docker; construct directly to test the plumbing only.
    s = Session(sandbox=SimpleNamespace(), timeout_sec=600.0)
    assert s.timeout_sec == 600.0
    assert s.remaining_sec > 0
