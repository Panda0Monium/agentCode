"""
plan_execute and skeleton, driven to completion against a scripted model.

Each test asserts the *control flow* — which phases ran, in what order, and
what reasoning artefacts they emitted — because that is the only thing that
distinguishes one architecture from another.
"""

import pytest

from agents import plan_execute, skeleton
from agents.base import AgentContext, Conversation
from tests.fakes import FakeLLM, FakeSession, ai, call


STUB = {"src/solution.py": "def solve():\n    ...\n"}


class ScriptedConversation(Conversation):
    """
    A Conversation with separate scripts for tool calls and tool-free asks.

    Splitting them keeps tests readable: the act loops consume tool responses,
    the planning/reflection steps consume plain text, and neither can silently
    eat the other's script.
    """

    def __init__(self, session, tool_responses, text_responses):
        super().__init__(
            session,
            budget=None,
            llm=FakeLLM(text_responses, name="text"),
            tool_llm=FakeLLM(tool_responses, name="tool"),
        )


def _patch_conv(monkeypatch, module, session, tool_responses, text_responses):
    conv = ScriptedConversation(session, tool_responses, text_responses)
    monkeypatch.setattr(module, "Conversation", lambda *a, **k: conv)
    return conv


def _done(n=1):
    return [ai(content="done") for _ in range(n)]


# ------------------------------------------------------------------
# Plan parsing
# ------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("1. Read the stub\n2. Implement solve\n3. Run tests",
     ["Read the stub", "Implement solve", "Run tests"]),
    ("1) First\n2) Second", ["First", "Second"]),
    ("Here is the plan:\n1. Alpha\nsome noise\n2. Beta", ["Alpha", "Beta"]),
])
def test_parse_plan_extracts_numbered_steps(text, expected):
    assert plan_execute.parse_plan(text) == expected


def test_parse_plan_falls_back_to_a_single_step():
    # An unparseable plan must not silently produce a no-op episode.
    assert plan_execute.parse_plan("Just implement the whole thing.") == \
        ["Just implement the whole thing."]


def test_parse_plan_is_capped():
    text = "\n".join(f"{i}. step {i}" for i in range(1, 20))
    assert len(plan_execute.parse_plan(text, max_steps=7)) == 7


def test_parse_plan_of_empty_text_is_empty():
    assert plan_execute.parse_plan("   ") == []


# ------------------------------------------------------------------
# plan_execute control flow
# ------------------------------------------------------------------

def test_plan_execute_runs_orient_plan_steps_then_verify(monkeypatch):
    session = FakeSession(files=dict(STUB))
    ctx = AgentContext(instruction="Implement solve().")

    tool_responses = (
        _done(1)                                              # orient
        + [ai(tool_calls=[call("write_file", _id="w1", path="src/solution.py",
                               content="def solve():\n    return 1\n")]), ai(content="step 1 done")]
        + [ai(tool_calls=[call("write_file", _id="w2", path="src/solution.py",
                               content="def solve():\n    return 42\n")]), ai(content="step 2 done")]
        + [ai(tool_calls=[call("run_tests", _id="t1")]), ai(content="all green")]
    )
    text_responses = ["1. Write a stub body\n2. Return the right value"]

    _patch_conv(monkeypatch, plan_execute, session, tool_responses, text_responses)
    plan_execute.build(ctx)(session)

    kinds = session.note_kinds()
    assert kinds == ["plan", "phase", "phase"]
    assert session.files["src/solution.py"] == "def solve():\n    return 42\n"
    assert "run_tests" in session.tool_names()  # verification always runs


def test_plan_execute_verifies_even_when_the_plan_is_empty(monkeypatch):
    # An empty plan must still end in verification rather than doing nothing.
    session = FakeSession(files=dict(STUB))
    ctx = AgentContext(instruction="Implement solve().")

    _patch_conv(monkeypatch, plan_execute, session,
                tool_responses=_done(1) + [ai(tool_calls=[call("run_tests")]), ai(content="ok")],
                text_responses=["   "])
    plan_execute.build(ctx)(session)

    assert session.note_kinds() == ["plan"]
    assert "run_tests" in session.tool_names()


def test_plan_execute_replans_once_when_the_executor_escapes(monkeypatch):
    session = FakeSession(files=dict(STUB))
    ctx = AgentContext(instruction="Implement solve().")

    tool_responses = (
        _done(1)                       # orient
        + [ai(content="REPLAN")]       # step 1 of the bad plan bails out
        + [ai(content="ok")]           # step 1 of the corrected plan
        + [ai(content="verified")]     # verify
    )
    text_responses = [
        "1. Edit the file that does not exist",   # original plan
        "1. Edit src/solution.py instead",        # corrected plan
    ]

    _patch_conv(monkeypatch, plan_execute, session, tool_responses, text_responses)
    plan_execute.build(ctx)(session)

    notes = [a for a in session.trajectory if a.tool == "agent_note"]
    plans = [n for n in notes if n.args["kind"] == "plan"]
    assert len(plans) == 2
    assert plans[1].args["replan"] is True


def test_plan_execute_replans_at_most_once(monkeypatch):
    # Otherwise a model that always says REPLAN loops until the budget dies.
    session = FakeSession(files=dict(STUB))
    ctx = AgentContext(instruction="Implement solve().")

    tool_responses = _done(1) + [ai(content="REPLAN")] + [ai(content="REPLAN")] + _done(1)
    text_responses = ["1. First plan", "1. Second plan"]

    _patch_conv(monkeypatch, plan_execute, session, tool_responses, text_responses)
    plan_execute.build(ctx)(session)

    plans = [n for n in session.trajectory if n.tool == "agent_note" and n.args["kind"] == "plan"]
    assert len(plans) == 2  # not three, four, ...


# ------------------------------------------------------------------
# Skeleton parsing
# ------------------------------------------------------------------

def test_parse_sections_finds_defs_and_classes():
    text = (
        "class LRUCache:\n"
        "    def __init__(self, capacity):\n"
        "        ...\n"
        "    def get(self, key):\n"
        "        ...\n"
        "    def put(self, key, value):\n"
        "        ...\n"
    )
    assert skeleton.parse_sections(text) == ["LRUCache", "get", "put"]


def test_parse_sections_skips_dunders():
    assert "__init__" not in skeleton.parse_sections("def __init__(self):\n    ...\ndef go(self):\n    ...")


def test_parse_sections_deduplicates_and_caps():
    text = "\n".join(f"def f{i}():\n    ..." for i in range(20))
    assert len(skeleton.parse_sections(text, max_sections=8)) == 8


# ------------------------------------------------------------------
# skeleton control flow
# ------------------------------------------------------------------

def test_skeleton_writes_an_outline_then_fills_each_section(monkeypatch):
    session = FakeSession(files=dict(STUB))
    ctx = AgentContext(instruction="Implement solve().")

    outline = "def solve():\n    ...\ndef helper():\n    ..."
    tool_responses = (
        _done(1)                                                     # orient
        + [ai(tool_calls=[call("write_file", _id="s", path="src/solution.py", content=outline)]),
           ai(content="skeleton written")]                           # write skeleton
        + [ai(tool_calls=[call("write_file", _id="f1", path="src/solution.py",
                               content="def solve():\n    return helper()\ndef helper():\n    ...")]),
           ai(content="solve done")]                                 # fill solve
        + [ai(tool_calls=[call("write_file", _id="f2", path="src/solution.py",
                               content="def solve():\n    return helper()\ndef helper():\n    return 42")]),
           ai(content="helper done")]                                # fill helper
        + [ai(tool_calls=[call("run_tests", _id="t")]), ai(content="green")]  # verify
    )

    _patch_conv(monkeypatch, skeleton, session, tool_responses, [outline])
    skeleton.build(ctx)(session)

    kinds = session.note_kinds()
    assert kinds[0] == "skeleton"
    assert kinds.count("phase") == 2
    # Both sections survived into the final file — nothing clobbered.
    assert "return helper()" in session.files["src/solution.py"]
    assert "return 42" in session.files["src/solution.py"]


def test_skeleton_rereads_the_file_before_each_fill(monkeypatch):
    # The fill prompt must be built from the file as it is *now*; working from
    # a stale copy is how earlier sections get silently discarded.
    session = FakeSession(files=dict(STUB))
    ctx = AgentContext(instruction="Implement solve().")

    outline = "def a():\n    ...\ndef b():\n    ..."
    tool_responses = (
        _done(1)
        + [ai(tool_calls=[call("write_file", _id="s", path="src/solution.py", content=outline)]),
           ai(content="ok")]
        + _done(1)   # fill a
        + _done(1)   # fill b
        + _done(1)   # verify
    )
    _patch_conv(monkeypatch, skeleton, session, tool_responses, [outline])
    skeleton.build(ctx)(session)

    # One harness-driven read per fill section.
    reads = [a for a in session.trajectory if a.tool == "read_file"]
    assert len(reads) >= 2


def test_skeleton_still_verifies_when_nothing_was_written(monkeypatch):
    session = FakeSession(files=dict(STUB))
    ctx = AgentContext(instruction="Implement solve().")

    _patch_conv(monkeypatch, skeleton, session,
                tool_responses=_done(1) + _done(1) + [ai(tool_calls=[call("run_tests")]), ai(content="ok")],
                text_responses=["def solve():\n    ..."])
    skeleton.build(ctx)(session)

    assert "run_tests" in session.tool_names()


# ------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------

@pytest.mark.parametrize("name", ["plan_execute", "skeleton"])
def test_variant_is_registered_with_extra_wall_clock(name):
    from agents import get_agent

    spec = get_agent(name)
    assert spec.build is not None
    # Multi-phase variants need more wall-clock than a single ReAct pass, or
    # they get recorded as timeouts for reasons unrelated to reasoning.
    assert spec.time_multiplier > 1.0
