"""
The five tools exposed to the agent.

All functions take a Sandbox as their first argument and return
structured schema objects (not raw strings), so the grader and
trajectory logger can consume them directly.
"""

import json

from .sandbox import Sandbox
from .schemas import LintError, LintResult, TestCase, TestResult, ToolError


def read_file(sandbox: Sandbox, path: str) -> str:
    try:
        return sandbox.read_file(path)
    except FileNotFoundError:
        raise ToolError(f"File not found: {path}")
    except PermissionError as e:
        raise ToolError(str(e))


def write_file(sandbox: Sandbox, path: str, content: str) -> None:
    try:
        sandbox.write_file(path, content)
    except PermissionError as e:
        raise ToolError(str(e))


def list_files(sandbox: Sandbox, path: str = "") -> list[str]:
    return sandbox.list_files(path)


def run_tests(sandbox: Sandbox, suite: str = "public") -> TestResult:
    """
    Run pytest on tests/{suite}/ inside the sandbox.
    Returns structured per-test results — the primary source of dense reward signal.
    """
    test_dir = f"tests/{suite}"
    report_path = "/tmp/agentcode_report.json"

    _, stdout = sandbox.exec(
        f"python -m pytest {test_dir} "
        f"--json-report --json-report-file={report_path} "
        f"-q 2>&1 || true"
    )

    _, report_raw = sandbox.exec(f"cat {report_path} 2>/dev/null || echo '{{}}'")

    try:
        report = json.loads(report_raw)
    except json.JSONDecodeError:
        return TestResult(passed=0, failed=0, errors=1, cases=[], stdout=stdout)

    cases = []
    for t in report.get("tests", []):
        outcome = t.get("outcome", "error")
        error = None
        if outcome != "passed":
            error = (t.get("call") or t.get("setup") or {}).get("longrepr")
        cases.append(
            TestCase(
                name=t["nodeid"],
                passed=(outcome == "passed"),
                duration_ms=(t.get("duration", 0.0) * 1000),
                error=error,
            )
        )

    summary = report.get("summary", {})
    return TestResult(
        passed=summary.get("passed", 0),
        failed=summary.get("failed", 0),
        errors=summary.get("error", summary.get("errors", 0)),  # pytest-json-report uses "error" (singular)
        cases=cases,
        stdout=stdout,
    )


# ------------------------------------------------------------------
# Lint scope
# ------------------------------------------------------------------
# lint_score feeds the reward, so what counts as an error has to be a property
# of the benchmark rather than of the host or of whichever ruff happens to be
# installed.
#
# EXE002 ("file is executable but no shebang") measures the filesystem, not the
# code. Bind-mounting the repo from a host without POSIX permission bits —
# Windows — presents every file as 0777, so the rule fires once per .py file,
# including files the agent never touched and cannot chmod. On Linux it never
# fires at all, which would make scores from the two platforms incomparable.
#
# tests/ is excluded because the harness owns it: public tests are injected at
# session start, and private tests are injected by the grader *after* the agent
# has stopped. Linting them scores the agent on files it never sees, and makes
# lint_score depend on how many test files the task author happened to write.
LINT_IGNORE = ("EXE002",)
LINT_EXCLUDE = ("tests",)


def lint_command() -> str:
    """The exact ruff invocation used for scoring. Kept separate so it is testable."""
    return (
        "ruff check . --output-format json"
        f" --ignore {','.join(LINT_IGNORE)}"
        f" --exclude {','.join(LINT_EXCLUDE)}"
        " 2>/dev/null || true"
    )


def run_lint(sandbox: Sandbox) -> LintResult:
    """
    Run ruff on the agent-owned source. Returns structured errors and a score.
    Score = max(0, 1.0 - 0.05 * num_errors).
    """
    _, output = sandbox.exec(lint_command())

    try:
        items = json.loads(output) if output.strip() else []
    except json.JSONDecodeError:
        items = []

    errors = [
        LintError(
            path=item["filename"],
            line=item["location"]["row"],
            col=item["location"]["column"],
            code=item["code"],
            message=item["message"],
        )
        for item in items
        if isinstance(item, dict)
    ]

    score = max(0.0, 1.0 - len(errors) * 0.05)
    return LintResult(errors=errors, score=score)
