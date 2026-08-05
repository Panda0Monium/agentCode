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
