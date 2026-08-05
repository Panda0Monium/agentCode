"""
Critic-actor.

An implementer writes code; a reviewer reads it and demands changes; repeat
until the reviewer approves or the round budget runs out. Both roles share one
sandbox and one token budget.

Two failure modes shape the design.

Sycophancy. Models approve broken code readily, so an APPROVE verdict is not
taken at face value: if the public tests are failing, the harness overrides the
approval and the loop continues. Correctness is directly observable, so there
is no reason to accept an opinion about it — the critic's judgement is advisory
on style and structure only. Without this gate the architecture reduces to "one
ReAct pass plus a compliment".

Token cost. Sending whole files to a reviewer every round is the single largest
token sink in the whole feature. Only files touched in the current round are
included, each truncated, and the shared Budget bounds the rest.
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
    read_current_state,
    run_tool_loop,
)
from .prompts import ACTOR_REVISION, ACTOR_SYSTEM, CRITIC_PROMPT
from .registry import AgentSpec, register
from .toolkit import fmt_lint_result, fmt_test_result

MAX_ROUNDS = 3
ACTOR_TURNS = 10
FILE_CHARS = 4000


def parse_verdict(critique: str) -> str:
    """
    APPROVE or REVISE. Anything unparseable is REVISE — the safe default is to
    keep working, not to stop on an ambiguous signal.
    """
    for line in reversed(critique.splitlines()):
        stripped = line.strip().upper()
        if stripped.startswith("VERDICT:"):
            return "APPROVE" if "APPROVE" in stripped else "REVISE"
    return "REVISE"


def build(ctx: AgentContext) -> Callable[[Session], None]:
    max_rounds = ctx.opt("max_rounds", MAX_ROUNDS)
    actor_turns = ctx.opt("actor_turns", ACTOR_TURNS)

    def _agent(session: Session) -> None:
        conv = Conversation(session, budget=ctx.budget)
        critique = None
        last_tests = None
        seen_before_round: list[str] = []

        for round_no in range(1, max_rounds + 1):
            session.log_note("phase", f"Round {round_no} of {max_rounds}", round=round_no)

            # --- actor ---
            messages = [SystemMessage(content=ACTOR_SYSTEM), HumanMessage(content=ctx.instruction)]
            if critique:
                messages.append(HumanMessage(content=ACTOR_REVISION.format(
                    round=round_no - 1,
                    critique=critique,
                    tests=fmt_test_result(last_tests) if last_tests else "(not yet run)",
                )))
            run_tool_loop(conv, messages, max_turns=actor_turns)

            # --- ground truth, run rather than reported ---
            last_tests, lint = ground_truth(session)
            tests_pass = last_tests.total > 0 and last_tests.passed == last_tests.total

            # --- critic, tool-free so it cannot edit what it reviews ---
            written = files_written(session)
            this_round = [p for p in written if p not in seen_before_round] or written
            seen_before_round = list(written)

            critique = ask(conv, [HumanMessage(content=CRITIC_PROMPT.format(
                instruction=ctx.instruction,
                state=read_current_state(session, this_round, limit=FILE_CHARS),
                tests=fmt_test_result(last_tests),
                lint=fmt_lint_result(lint),
            ))])
            verdict = parse_verdict(critique)
            session.log_note("critique", critique, verdict=verdict, round=round_no)

            if verdict == "APPROVE":
                if tests_pass:
                    return
                # Approval of failing code is not evidence of anything.
                session.log_note(
                    "approval_overridden",
                    f"Critic approved, but {last_tests.total - last_tests.passed} of "
                    f"{last_tests.total} public tests fail. Continuing.",
                    round=round_no,
                )
                critique = (
                    "Your reviewer approved, but the tests still fail:\n"
                    + fmt_test_result(last_tests)
                    + "\nFix the failures."
                )

    return _agent


register(
    AgentSpec(
        name="critic_actor",
        label="Critic-actor",
        description="An implementer and a reviewer iterate until the reviewer approves.",
        build=build,
        default_options={"max_rounds": MAX_ROUNDS, "actor_turns": ACTOR_TURNS},
        time_multiplier=3.0,
    )
)
