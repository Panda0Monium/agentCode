"""
Plan-and-execute.

Orient, commit to a numbered plan, then execute one step at a time — each step
in its own bounded tool loop with fresh context, rather than one long
improvised conversation.

The trade-off against ReAct is rigidity: a plan made before writing any code
can be wrong, and an agent that follows it faithfully will implement the wrong
thing very efficiently. Two things guard against that. The executor may emit
REPLAN once, which buys a corrected plan from a position of more knowledge; and
the verification phase always runs, whether or not the plan was completed, so
the episode never ends on an unchecked assumption.
"""

import re
from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from environment.session import Session

from .base import (
    AgentContext,
    Conversation,
    ask,
    files_written,
    read_current_state,
    run_tool_loop,
    text_of,
)
from .prompts import (
    EXECUTOR_SYSTEM,
    ORIENT_SYSTEM,
    PLANNER_PROMPT,
    REPLAN_PROMPT,
    VERIFY_SYSTEM,
)
from .registry import AgentSpec, register

ORIENT_TURNS = 4
STEP_TURNS = 6
VERIFY_TURNS = 8
MAX_STEPS = 7

_STEP_RE = re.compile(r"^\s*(\d+)[.)]\s+(.+)$")


def parse_plan(text: str, max_steps: int = MAX_STEPS) -> list[str]:
    """
    Pull numbered steps out of a plan.

    Deliberately forgiving: if the model ignores the format entirely, the whole
    response becomes a single step rather than the episode doing nothing. A
    plan DSL would be more precise and far more brittle.
    """
    steps = [m.group(2).strip() for m in (_STEP_RE.match(l) for l in text.splitlines()) if m]
    if not steps:
        collapsed = " ".join(text.split())
        return [collapsed] if collapsed else []
    return steps[:max_steps]


def build(ctx: AgentContext) -> Callable[[Session], None]:
    def _agent(session: Session) -> None:
        conv = Conversation(session, budget=ctx.budget)

        # 1. Orient — look around before committing to anything.
        run_tool_loop(
            conv,
            [SystemMessage(content=ORIENT_SYSTEM), HumanMessage(content=ctx.instruction)],
            max_turns=ctx.opt("orient_turns", ORIENT_TURNS),
        )

        # 2. Plan — tool-free, so the planner cannot start editing.
        plan_text = ask(conv, [HumanMessage(content=PLANNER_PROMPT.format(instruction=ctx.instruction))])
        steps = parse_plan(plan_text, ctx.opt("max_steps", MAX_STEPS))
        session.log_note("plan", plan_text, steps=len(steps))

        # 3. Execute, one step per bounded loop.
        replanned = False
        i = 0
        while i < len(steps):
            step = steps[i]
            session.log_note("phase", step, step=i + 1, of=len(steps))

            messages = [
                SystemMessage(content=EXECUTOR_SYSTEM.format(plan=plan_text)),
                HumanMessage(content=f"Current step {i + 1} of {len(steps)}: {step}"),
            ]
            run_tool_loop(conv, messages, max_turns=ctx.opt("step_turns", STEP_TURNS))

            if not replanned and _wants_replan(messages):
                plan_text = ask(conv, [HumanMessage(content=REPLAN_PROMPT.format(
                    step_no=i + 1,
                    plan=plan_text,
                    state=read_current_state(session, files_written(session)),
                    instruction=ctx.instruction,
                ))])
                steps = parse_plan(plan_text, ctx.opt("max_steps", MAX_STEPS))
                session.log_note("plan", plan_text, steps=len(steps), replan=True)
                replanned = True
                i = 0
                continue

            i += 1

        # 4. Verify — always, even if the plan was abandoned or ran short.
        run_tool_loop(
            conv,
            [SystemMessage(content=VERIFY_SYSTEM), HumanMessage(content=ctx.instruction)],
            max_turns=ctx.opt("verify_turns", VERIFY_TURNS),
        )

    return _agent


def _wants_replan(messages: list) -> bool:
    """True when the executor's last word was the REPLAN escape."""
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "ai":
            content = text_of(msg)
            return content.strip().upper() == "REPLAN"
    return False


register(
    AgentSpec(
        name="plan_execute",
        label="Plan and execute",
        description="Commits to a numbered plan first, then executes it step by step.",
        build=build,
        default_options={
            "orient_turns": ORIENT_TURNS,
            "step_turns": STEP_TURNS,
            "verify_turns": VERIFY_TURNS,
            "max_steps": MAX_STEPS,
        },
        time_multiplier=1.5,
    )
)
