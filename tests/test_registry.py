from types import SimpleNamespace

import pytest

import agents
from agents import build_agent, get_agent, list_agents
from agents.base import AgentContext


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


def test_baseline_architectures_are_registered():
    names = [s.name for s in list_agents()]
    assert "react" in names
    assert "noop" in names
    # The baseline is registered first so it leads --help and the web dropdown.
    assert names[0] == "react"


def test_spec_names_are_unique():
    names = [s.name for s in list_agents()]
    assert len(names) == len(set(names))


def test_every_registered_spec_builds_a_callable():
    for spec in list_agents():
        agent = build_agent(spec.name, _task())
        assert callable(agent)


def test_unknown_architecture_lists_the_known_ones():
    with pytest.raises(KeyError) as excinfo:
        get_agent("does-not-exist")
    assert "react" in str(excinfo.value)


def test_build_attaches_metadata_the_runner_reads_back():
    agent = build_agent("react", _task(timeout_sec=300.0))
    assert agent.agent_name == "react"
    assert hasattr(agent, "budget")
    assert agent.suggested_timeout_sec == 300.0


def test_time_multiplier_scales_the_suggested_timeout():
    spec = get_agent("react")
    object.__setattr__(spec, "time_multiplier", 2.0)
    try:
        agent = build_agent("react", _task(timeout_sec=300.0))
        assert agent.suggested_timeout_sec == 600.0
    finally:
        object.__setattr__(spec, "time_multiplier", 1.0)


def test_options_override_spec_defaults():
    captured = {}

    def fake_build(ctx: AgentContext):
        captured["max_turns"] = ctx.opt("max_turns")
        return lambda session: None

    spec = get_agent("react")
    real_build = spec.build
    object.__setattr__(spec, "build", fake_build)
    try:
        build_agent("react", _task(), options={"max_turns": 3})
        assert captured["max_turns"] == 3
    finally:
        object.__setattr__(spec, "build", real_build)


def test_deprecated_shim_still_builds_a_react_agent():
    import agent as legacy

    with pytest.deprecated_call():
        built = legacy.coding_agent("do a thing")
    assert callable(built)
    assert built.agent_name == "react"


def test_default_agent_is_react():
    assert agents.DEFAULT_AGENT == "react"


# ------------------------------------------------------------------
# Controlled constants across architectures
# ------------------------------------------------------------------

def test_every_terminal_prompt_uses_the_same_stop_mandate():
    """
    The architecture is the independent variable; the finish line is not.
    VERIFY_SYSTEM once said "Keep going until tests pass and lint is clean"
    while ReAct said "stop when" — so plan_execute/skeleton/tdd burned their
    whole verify budget on tasks where ReAct stopped early, and the difference
    looked like an architectural result.
    """
    from agents import prompts

    terminal = {
        "REACT_SYSTEM": prompts.REACT_SYSTEM,
        "VERIFY_SYSTEM": prompts.VERIFY_SYSTEM,
        "REFLEXION_SYSTEM": prompts.REFLEXION_SYSTEM,
    }
    for name, text in terminal.items():
        assert prompts.STOP_MANDATE in text, f"{name} does not carry the shared stop mandate"


def test_no_terminal_prompt_invents_its_own_finish_line():
    from agents import prompts

    for name in ("VERIFY_SYSTEM", "REFLEXION_SYSTEM"):
        text = getattr(prompts, name).lower()
        assert "keep going until" not in text, f"{name} reintroduced a divergent mandate"


def test_harness_success_predicate_is_shared():
    # The prompt-level mandate is only half of it; architectures that decide
    # for themselves when to stop must agree on the same condition.
    from agents.base import is_solved
    from tests.fakes import clean_lint, dirty_lint, failing_tests, passing_tests

    assert is_solved(passing_tests(3), clean_lint()) is True
    assert is_solved(failing_tests(1, 2), clean_lint()) is False
    assert is_solved(passing_tests(3), dirty_lint(1)) is False


def test_is_solved_rejects_an_empty_suite():
    # 0/0 passing is not success; it usually means collection failed.
    from environment.schemas import TestResult

    from agents.base import is_solved
    from tests.fakes import clean_lint

    empty = TestResult(passed=0, failed=0, errors=0, cases=[], stdout="")
    assert is_solved(empty, clean_lint()) is False
