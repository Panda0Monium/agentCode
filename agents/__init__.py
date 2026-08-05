"""
Pluggable agent architectures.

AgentCode is a benchmark, so the agent architecture is the independent variable
worth measuring. This package makes it selectable and recorded: pick one by
name from the CLI (``--agent``) or the web UI, and the choice is carried through
into the reports so runs are comparable across architectures.

    from agents import build_agent
    agent = build_agent("react", task)
    result = run_episode(task, agent)

The runtime protocol is unchanged from the original single-architecture agent —
an agent is just ``Callable[[Session], None]``. Only construction goes through
here. Metadata the runner needs afterwards (which architecture ran, what it
spent) is attached to the returned callable, so run_episode's signature never
had to change and a plain ``def my_agent(session)`` still works.
"""

from collections.abc import Callable
from types import SimpleNamespace
from typing import TYPE_CHECKING, Optional

from environment.session import Session

from .base import AgentContext
from .budget import Budget, BudgetExhausted, default_budget_for
from .registry import AgentSpec, agent_names, get_agent, list_agents, register

# Importing a variant module registers it. Order here is the order they appear
# in --help and in the web dropdown, so keep the baseline first.
from . import react  # noqa: F401,E402
from . import plan_execute  # noqa: F401,E402
from . import skeleton  # noqa: F401,E402
from . import reflexion  # noqa: F401,E402
from . import tdd  # noqa: F401,E402
from . import critic_actor  # noqa: F401,E402
from . import noop  # noqa: F401,E402

if TYPE_CHECKING:  # pragma: no cover
    from tasks import Task

__all__ = [
    "AgentContext",
    "AgentSpec",
    "Budget",
    "BudgetExhausted",
    "agent_names",
    "build_agent",
    "build_agent_from_instruction",
    "default_budget_for",
    "get_agent",
    "list_agents",
    "register",
]

DEFAULT_AGENT = "react"


def _wrap_graceful(inner: Callable[[Session], None], ctx: AgentContext):
    """
    Turn budget exhaustion into a clean end-of-episode.

    Running out of tokens is a normal outcome, not a failure: the repo still
    holds whatever the agent managed to write, and that work should be scored.
    If BudgetExhausted escaped to run_episode it would be caught as a generic
    exception and recorded as agent_error, which reads as a crash and would
    distort every comparison involving the expensive architectures.
    """

    def _agent(session: Session) -> None:
        try:
            inner(session)
        except BudgetExhausted as exc:
            if ctx.budget is not None:
                ctx.budget.exhausted = True
            try:
                session.log_note("budget_exhausted", str(exc))
            except Exception:
                pass

    return _agent


def build_agent(
    name: str,
    task: "Task",
    *,
    max_tokens: Optional[int] = None,
    options: Optional[dict] = None,
) -> Callable[[Session], None]:
    """
    Build the named architecture for a task.

    ``max_tokens`` overrides the token budget for this run; when omitted the
    default is derived from the task (see agents.budget).
    """
    spec = get_agent(name)

    resolved_tokens = max_tokens if max_tokens is not None else default_budget_for(task)

    ctx = AgentContext(
        instruction=task.instruction,
        task_name=getattr(task, "name", ""),
        difficulty=getattr(task, "difficulty", ""),
        language=getattr(task, "language", "python"),
        budget=Budget(max_tokens=resolved_tokens),
        options={**spec.default_options, **(options or {})},
    )

    agent = _wrap_graceful(spec.build(ctx), ctx)

    # Metadata the runner reads back off the callable after the episode.
    timeout_sec = getattr(task, "timeout_sec", None)
    agent.agent_name = spec.name
    agent.budget = ctx.budget
    agent.suggested_timeout_sec = (
        timeout_sec * spec.time_multiplier if timeout_sec is not None else None
    )
    return agent


def build_agent_from_instruction(
    instruction: str,
    name: str = DEFAULT_AGENT,
    **kwargs,
) -> Callable[[Session], None]:
    """
    Build an architecture from a bare instruction, with no Task in hand.

    Only for callers that genuinely have nothing else — the task carries the
    difficulty that the token budget defaults from, so prefer build_agent().
    """
    return build_agent(name, SimpleNamespace(instruction=instruction), **kwargs)
