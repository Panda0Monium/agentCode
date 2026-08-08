"""
Test-driven agent.

Write tests first, watch them fail, then implement until they pass — the
inverse of the default flow, where tests are something the agent runs at the
end to check work it already believes is correct.

The cleanup step removes the scratch tests before the episode ends, so the
graded deliverable is just the source the task asked for.

This used to matter for scoring: lint ran `ruff check .` at the repo root, so
every violation in an agent-authored test file cost 5% of lint_score — this
architecture was penalised for doing its job. Lint now excludes tests/
entirely (environment/tools.py), because that directory belongs to the harness.
The cleanup is kept for tidiness rather than points; leaving scratch tests in
code.zip alongside the solution invites them to be mistaken for graded suites.
"""

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from environment.session import Session

from .base import AgentContext, Conversation, ground_truth, read_current_state, run_tool_loop
from .prompts import TDD_IMPLEMENT_SYSTEM, TDD_TESTS_SYSTEM, VERIFY_SYSTEM
from .registry import AgentSpec, register
from .toolkit import fmt_test_result

TEST_DIR = "tests/agent"
TEST_TURNS = 8
IMPLEMENT_TURNS = 14
VERIFY_TURNS = 6


def _agent_test_files(session: Session) -> list[str]:
    """Scratch test files this architecture created, normalised to forward slashes."""
    written = (
        a.args["path"].replace("\\", "/")
        for a in session.trajectory
        if a.tool == "write_file" and "path" in a.args
    )
    return list(dict.fromkeys(p for p in written if p.startswith(TEST_DIR)))


def build(ctx: AgentContext) -> Callable[[Session], None]:
    def _agent(session: Session) -> None:
        conv = Conversation(session, budget=ctx.budget)

        # 1. Write tests first. Nothing is implemented yet, so these describe
        #    intent rather than reflecting whatever the code happens to do.
        run_tool_loop(
            conv,
            [SystemMessage(content=TDD_TESTS_SYSTEM), HumanMessage(content=ctx.instruction)],
            max_turns=ctx.opt("test_turns", TEST_TURNS),
        )

        test_files = _agent_test_files(session)
        session.log_note(
            "test_plan",
            "\n".join(test_files) if test_files else "(no scratch tests written)",
            files=len(test_files),
        )

        # 2. Confirm red, from the harness rather than the model's say-so.
        tests, _ = ground_truth(session)
        session.log_note(
            "phase",
            f"Baseline before implementing: {fmt_test_result(tests)}",
            passed=tests.passed, total=tests.total,
        )

        # 3. Implement until green.
        own_tests = read_current_state(session, test_files) if test_files else "(none)"
        run_tool_loop(
            conv,
            [
                SystemMessage(content=TDD_IMPLEMENT_SYSTEM.format(tests=own_tests)),
                HumanMessage(content=ctx.instruction),
            ],
            max_turns=ctx.opt("implement_turns", IMPLEMENT_TURNS),
        )

        # 4. Clean up before grading. See the module docstring: leaving these
        #    behind costs lint_score for no benefit.
        removed = [p for p in _agent_test_files(session) if session.remove_path(p)]
        if session.remove_path(TEST_DIR):
            removed.append(TEST_DIR)
        if removed:
            session.log_note(
                "cleanup",
                "Removed scratch tests so they are not linted during grading:\n"
                + "\n".join(removed),
                files=len(removed),
            )

        # 5. Verify against the graded suites only.
        run_tool_loop(
            conv,
            [SystemMessage(content=VERIFY_SYSTEM), HumanMessage(content=ctx.instruction)],
            max_turns=ctx.opt("verify_turns", VERIFY_TURNS),
        )

    return _agent


register(
    AgentSpec(
        name="tdd",
        label="Test-driven",
        description="Writes its own tests first, then implements until they pass.",
        build=build,
        default_options={
            "test_turns": TEST_TURNS,
            "implement_turns": IMPLEMENT_TURNS,
            "verify_turns": VERIFY_TURNS,
        },
        time_multiplier=2.0,
    )
)
