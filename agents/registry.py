"""
The architecture registry.

Adding a variant means writing a module that calls ``register()`` at import
time and listing it in ``agents/__init__.py``. Everything downstream — the
``--agent`` CLI choices, the web dropdown, the per-variant report grouping —
reads from here, so a new architecture shows up everywhere without touching
the CLI or any template.
"""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentSpec:
    name: str
    """Stable slug. Used as the CLI value, the DB value and the report key."""

    label: str
    """Human-readable name for the web dropdown."""

    description: str
    """One line, shown in --help and next to the dropdown."""

    build: Callable
    """(AgentContext) -> Callable[[Session], None]"""

    default_options: dict = field(default_factory=dict)
    """Per-variant knobs, overridable per run."""

    time_multiplier: float = 1.0
    """
    Multiplies the task's timeout_sec for this architecture. Multi-round
    variants legitimately need more wall-clock than a single ReAct pass; without
    this they would be recorded as timing out for reasons unrelated to
    reasoning quality.
    """


_SPECS: dict[str, AgentSpec] = {}


def register(spec: AgentSpec) -> AgentSpec:
    if spec.name in _SPECS:
        raise ValueError(f"Duplicate agent name: {spec.name!r}")
    _SPECS[spec.name] = spec
    return spec


def get_agent(name: str) -> AgentSpec:
    try:
        return _SPECS[name]
    except KeyError:
        known = ", ".join(sorted(_SPECS)) or "(none registered)"
        raise KeyError(f"Unknown agent architecture {name!r}. Available: {known}") from None


def list_agents() -> list[AgentSpec]:
    """Registration order, which is baseline-first."""
    return list(_SPECS.values())


def agent_names() -> list[str]:
    return list(_SPECS)
