"""
Noop — does nothing, calls no LLM.

Exists to exercise the session/grader/report plumbing without a provider or an
API key, which makes it the cheapest possible smoke test of the harness.
"""

from collections.abc import Callable

from environment.session import Session

from .base import AgentContext
from .registry import AgentSpec, register


def build(ctx: AgentContext) -> Callable[[Session], None]:
    def _agent(session: Session) -> None:
        return None

    return _agent


register(
    AgentSpec(
        name="noop",
        label="No-op",
        description="Does nothing. Tests harness plumbing without an LLM.",
        build=build,
    )
)
