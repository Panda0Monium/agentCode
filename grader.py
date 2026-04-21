"""
Grader: scores the agent's final sandbox state.

Called after the agent is done (submitted or timed out).
Injects private tests, re-runs everything fresh, returns a GradeResult.

The agent never sees private test files — they're only added here,
after the agent's session is over.
"""

from dataclasses import dataclass

from environment import tools as _tools
from environment.schemas import LintResult, TestResult
from environment.session import Session
from tasks.task import GraderWeights, Task


@dataclass
class GradeResult:
    reward: float            # scalar ∈ [0, 1], suitable as RL reward
    public_score: float
    private_score: float
    lint_score: float
    public_result: TestResult
    private_result: TestResult
    lint_result: LintResult
    weights: GraderWeights

    def summary(self) -> str:
        w = self.weights
        lines = [
            f"reward:  {self.reward:.4f}",
            f"public:  {self.public_score:.4f}  (weight {w.public})"
            f"  [{self.public_result.passed}/{self.public_result.total} passed]",
            f"private: {self.private_score:.4f}  (weight {w.private})"
            f"  [{self.private_result.passed}/{self.private_result.total} passed]",
            f"lint:    {self.lint_score:.4f}  (weight {w.lint})"
            f"  [{len(self.lint_result.errors)} errors]",
        ]
        return "\n".join(lines)


class Grader:
    def grade(self, session: Session, task: Task) -> GradeResult:
        """
        Grade the agent's final state.
        Injects private tests, runs all suites fresh, computes weighted reward.
        """
        private_tests = task.tests_path / "private"
        if private_tests.exists():
            session.sandbox.inject_dir(private_tests, "tests/private")

        public_result = _tools.run_tests(session.sandbox, "public")
        private_result = _tools.run_tests(session.sandbox, "private")
        lint_result = _tools.run_lint(session.sandbox)

        w = task.weights
        reward = (
            w.public * public_result.score
            + w.private * private_result.score
            + w.lint * lint_result.score
        )

        return GradeResult(
            reward=round(reward, 6),
            public_score=public_result.score,
            private_score=private_result.score,
            lint_score=lint_result.score,
            public_result=public_result,
            private_result=private_result,
            lint_result=lint_result,
            weights=w,
        )
