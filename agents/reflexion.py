"""
Reflexion.

Attempt the task, check the result, and if it fell short, write down *why*
before trying again — carrying that diagnosis, not the whole transcript, into
the next attempt.

Two design choices matter:

Ground truth comes from the harness, not the model. After each attempt the
tests and lint are run directly and the reflection is written against those
results. Asking a model whether it succeeded is asking it to do the one thing
it is least reliable at, and a reflexion loop built on self-report converges on
confident nonsense.

History resets between attempts, reflections do not. A fresh transcript keeps
the failed approach from dominating the context, while the accumulated
reflections keep what was learned. The sandbox is not rolled back — there are
no snapshots — so each attempt continues from the current repo state, which is
what "retry with a reflection" honestly means here.
"""

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from environment.session import Session

from .base import (
    AgentContext,
    Conversation,
    ask,
    files_written,
    ground_truth,
    is_solved,
    run_tool_loop,
)
from .prompts import (
    REFLECT_PROMPT,
    REFLEXION_CARRY_OVER,
    REFLEXION_SYSTEM,
)
from .registry import AgentSpec, register
from .toolkit import fmt_lint_result, fmt_test_result

MAX_ATTEMPTS = 3
ATTEMPT_TURNS = 12


def build(ctx: AgentContext) -> Callable[[Session], None]:
    max_attempts = ctx.opt("max_attempts", MAX_ATTEMPTS)
    attempt_turns = ctx.opt("attempt_turns", ATTEMPT_TURNS)

    def _agent(session: Session) -> None:
        conv = Conversation(session, budget=ctx.budget)
        reflections: list[str] = []

        for attempt in range(1, max_attempts + 1):
            session.log_note("attempt", f"Attempt {attempt} of {max_attempts}", attempt=attempt)

            # Carried-forward reflections are folded into the single system
            # message rather than appended as a second one. Providers behind
            # litellm reject "System message must be at the beginning" when two
            # system messages appear in a row, which silently broke every
            # attempt after the first — the whole point of this architecture.
            system = REFLEXION_SYSTEM
            if reflections:
                system += "\n\n" + REFLEXION_CARRY_OVER.format(
                    attempt=attempt,
                    reflections="\n".join(f"- {r}" for r in reflections),
                    files=", ".join(files_written(session)) or "(none)",
                )
            messages = [
                SystemMessage(content=system),
                HumanMessage(content=ctx.instruction),
            ]

            run_tool_loop(conv, messages, max_turns=attempt_turns)

            # Ground truth, straight from the harness.
            tests, lint = ground_truth(session)
            if is_solved(tests, lint):
                session.log_note(
                    "attempt",
                    f"Solved on attempt {attempt}: {tests.passed}/{tests.total} tests, lint clean.",
                    attempt=attempt, solved=True,
                )
                return

            if attempt == max_attempts:
                break  # no point reflecting on the last attempt

            reflection = ask(conv, [HumanMessage(content=REFLECT_PROMPT.format(
                tests=fmt_test_result(tests),
                lint=fmt_lint_result(lint),
                files=", ".join(files_written(session)) or "(none)",
            ))])
            if reflection:
                reflections.append(reflection)
                session.log_note("reflection", reflection, attempt=attempt)

    return _agent


register(
    AgentSpec(
        name="reflexion",
        label="Reflexion",
        description="Retries after failure, carrying a written diagnosis into the next attempt.",
        build=build,
        default_options={"max_attempts": MAX_ATTEMPTS, "attempt_turns": ATTEMPT_TURNS},
        time_multiplier=2.0,
    )
)
