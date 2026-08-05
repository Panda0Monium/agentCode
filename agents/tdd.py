"""
Test-driven agent.

Write tests first, watch them fail, then implement until they pass — the
inverse of the default flow, where tests are something the agent runs at the
end to check work it already believes is correct.

IMPORTANT — why the cleanup step exists. Tests the agent writes cannot affect
its test scores: run_tests is scoped to tests/{suite}, so only the public and
private suites are ever collected. Lint is not scoped. `run_lint` shells
`ruff check .` at the repo root (environment/tools.py), and the grader runs it
after the agent finishes, so every ruff violation in an agent-authored test
file costs 5% of lint_score — a component this architecture would lose purely
for having done its job. The scratch tests are therefore deleted before the
episode ends. Without this, TDD scores worse than ReAct for a reason that has
nothing to do with test-driven development, and the benchmark quietly lies.
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
