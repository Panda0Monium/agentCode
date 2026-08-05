"""
Deprecated compatibility shim.

The single hardcoded ReAct agent that used to live here has moved into the
``agents`` package, where it is one of several selectable architectures:

    from agents import build_agent
    agent = build_agent("react", task)

``coding_agent`` remains so that existing callers keep working, and is
equivalent to building the "react" architecture with a default token budget.
"""

import warnings
from collections.abc import Callable

from environment.session import Session


def coding_agent(instruction: str) -> Callable[[Session], None]:
    """Deprecated. Use ``agents.build_agent("react", task)`` instead."""
    warnings.warn(
        "agent.coding_agent is deprecated; use agents.build_agent(name, task)",
        DeprecationWarning,
        stacklevel=2,
    )
    from agents import build_agent_from_instruction

    return build_agent_from_instruction(instruction)
