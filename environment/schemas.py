from dataclasses import dataclass, field


@dataclass
class TestCase:
    name: str
    passed: bool
    duration_ms: float
    error: str | None  # longrepr if failed, else None


@dataclass
class TestResult:
    passed: int
    failed: int
    errors: int
    cases: list[TestCase]
    stdout: str

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors

    @property
    def score(self) -> float:
        """Fraction of tests passing. 0.0 if no tests collected."""
        if self.total == 0:
            return 0.0
        return self.passed / self.total


@dataclass
class LintError:
    path: str
    line: int
    col: int
    code: str
    message: str


@dataclass
class LintResult:
    errors: list[LintError]
    score: float  # 1.0 = clean, decays 5% per error, floor 0.0


@dataclass
class Action:
    tool: str
    args: dict
    result: object
    timestamp: float  # monotonic seconds since session start


class ToolError(Exception):
    """Raised when a tool call fails due to bad input (not a sandbox crash)."""
