"""
ReAct — the baseline architecture.

Think → act → observe in a single loop until the model stops calling tools.
This is the original agent, unchanged, and it is the control against which every
other architecture is measured. Changes here invalidate historical comparisons.
"""

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from environment.session import Session

from .base import AgentContext, Conversation, run_tool_loop
from .prompts import REACT_SYSTEM
from .registry import AgentSpec, register

MAX_TURNS = 25


def build(ctx: AgentContext) -> Callable[[Session], None]:
    def _agent(session: Session) -> None:
        conv = Conversation(session, budget=ctx.budget)
        messages = [
            SystemMessage(content=REACT_SYSTEM),
            HumanMessage(content=ctx.instruction),
        ]
        run_tool_loop(conv, messages, max_turns=ctx.opt("max_turns", MAX_TURNS))

    return _agent


register(
    AgentSpec(
        name="react",
        label="ReAct",
        description="Baseline. One think/act/observe loop until tests pass.",
        build=build,
        default_options={"max_turns": MAX_TURNS},
    )
)
