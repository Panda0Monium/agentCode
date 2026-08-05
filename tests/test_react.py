"""
ReAct is the control the other architectures are measured against, so these
tests pin its observable behaviour: the loop shape, the turn cap, the blank
response handling, and the exact system prompt bytes.
"""

from langchain_core.messages import HumanMessage, SystemMessage

from agents import react
from agents.base import AgentContext, Conversation, run_tool_loop
from agents.prompts import CONTINUE_NUDGE, REACT_SYSTEM
from tests.fakes import FakeLLM, FakeSession, ai, call, failing_tests


def _run(responses, session=None, **ctx_kw):
    session = session or FakeSession(files={"src/solution.py": "def solve():\n    ...\n"})
    llm = FakeLLM(responses)
    ctx = AgentContext(instruction="Implement solve().", **ctx_kw)

    # Drive the loop directly with the fake client rather than going through
    # build(), which would construct a real provider client.
    conv = Conversation(session, budget=ctx.budget, llm=llm, tool_llm=llm)
    messages = [SystemMessage(content=REACT_SYSTEM), HumanMessage(content=ctx.instruction)]
    run_tool_loop(conv, messages, max_turns=ctx.opt("max_turns", react.MAX_TURNS))
    return session, llm, messages


def test_system_prompt_is_byte_identical_to_the_original():
    # Historical results in output/ were produced with these exact bytes.
    # If this test fails, every cross-architecture comparison against the
    # ReAct baseline is invalid — fix the prompt, do not update the test.
    expected = (
        "You are a software engineering agent. You will be given a coding task and a set "
        "of tools to read and modify files in a sandboxed repository.\n"
        "\n"
        "Work iteratively:\n"
        "1. Read the relevant files to understand the scaffold.\n"
        "2. Implement the required code.\n"
        "3. Run the tests to check your work.\n"
        "4. Fix any failures, then run lint and fix any errors.\n"
        "5. When the tests pass and lint is clean, stop — do not call any more tools.\n"
        "\n"
        "Write correct, idiomatic Python. Do not add unnecessary comments or docstrings "
        "beyond what helps readability."
    )
    assert REACT_SYSTEM == expected


def test_happy_path_reads_writes_tests_then_stops():
    session, llm, _ = _run([
        ai(tool_calls=[call("read_file", path="src/solution.py")]),
        ai(tool_calls=[call("write_file", path="src/solution.py", content="def solve():\n    return 42\n")]),
        ai(tool_calls=[call("run_tests")]),
        ai(tool_calls=[call("run_lint")]),
        ai(content="Tests pass and lint is clean. Done."),
    ])

    assert session.tool_names() == [
        "llm_invoke", "read_file",
        "llm_invoke", "write_file",
        "llm_invoke", "run_tests",
        "llm_invoke", "run_lint",
        "llm_invoke",
    ]
    assert session.files["src/solution.py"] == "def solve():\n    return 42\n"
    assert llm.exhausted


def test_stops_as_soon_as_the_model_stops_calling_tools():
    session, llm, _ = _run([ai(content="Nothing to do.")])
    assert session.tool_names() == ["llm_invoke"]
    assert llm.exhausted


def test_parallel_tool_calls_in_one_turn_all_dispatch():
    session, _, _ = _run([
        ai(tool_calls=[
            call("read_file", _id="a", path="src/solution.py"),
            call("list_files", _id="b"),
        ]),
        ai(content="done"),
    ])
    assert session.tool_names() == ["llm_invoke", "read_file", "list_files", "llm_invoke"]


def test_blank_response_is_nudged_twice_then_gives_up():
    session, llm, messages = _run([ai(content=""), ai(content=""), ai(content="")])

    nudges = [m for m in messages if isinstance(m, HumanMessage) and m.content == CONTINUE_NUDGE]
    assert len(nudges) == 2
    assert len(llm.calls) == 3
    assert llm.exhausted


def test_a_nudged_model_that_recovers_keeps_going():
    session, llm, _ = _run([
        ai(content=""),
        ai(tool_calls=[call("write_file", path="src/solution.py", content="x = 1\n")]),
        ai(content="done"),
    ])
    assert session.written() == ["src/solution.py"]
    assert llm.exhausted


def test_turn_cap_stops_a_model_that_never_finishes():
    responses = [ai(tool_calls=[call("run_tests", _id=f"c{i}")]) for i in range(10)]
    session, llm, _ = _run(responses, options={"max_turns": 4})

    assert len([t for t in session.tool_names() if t == "llm_invoke"]) == 4
    assert len(llm.responses) == 6  # loop stopped early rather than draining


def test_tool_errors_are_fed_back_instead_of_crashing():
    session, llm, messages = _run([
        ai(tool_calls=[call("read_file", path="does/not/exist.py")]),
        ai(content="I'll create it instead."),
    ])
    tool_msgs = [m for m in messages if getattr(m, "type", None) == "tool"]
    assert tool_msgs and tool_msgs[0].content.startswith("Error:")
    assert llm.exhausted


def test_failing_tests_are_rendered_for_the_model():
    session = FakeSession(
        files={"src/solution.py": "x = 1\n"},
        test_results=[failing_tests(n_pass=1, n_fail=2)],
    )
    _, _, messages = _run(
        [ai(tool_calls=[call("run_tests")]), ai(content="done")],
        session=session,
    )
    tool_msgs = [m for m in messages if getattr(m, "type", None) == "tool"]
    assert "Tests: 1/3 passed" in tool_msgs[0].content
    assert "[FAIL] test_fail_0" in tool_msgs[0].content


def test_usage_is_not_recorded_when_no_budget_is_attached():
    session, _, _ = _run([ai(content="done")])
    llm_actions = [a for a in session.trajectory if a.tool == "llm_invoke"]
    assert "usage" not in llm_actions[0].result
