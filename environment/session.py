"""
Session: one agent episode against one task.

Wraps the Sandbox + tools with:
  - timeout enforcement
  - action trajectory logging (for RL rollouts)
  - clean context-manager interface

Usage:
    task = Task(...)
    with Session.from_task(task) as session:
        content = session.read_file("src/solution.py")
        session.write_file("src/solution.py", content + "\\n# fix")
        result = session.run_tests()
        print(result.score)
    # sandbox is torn down automatically
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

from . import tools as _tools
from .sandbox import Sandbox
from .schemas import Action, LintResult, TestResult


def _serialize_msg(msg) -> dict:
    d = {"role": msg.type, "content": msg.content}
    if getattr(msg, "tool_calls", None):
        d["tool_calls"] = msg.tool_calls
    if getattr(msg, "tool_call_id", None):
        d["tool_call_id"] = msg.tool_call_id
    return d


@dataclass
class Session:
    sandbox: Sandbox
    timeout_sec: float
    _start: float = field(default_factory=time.monotonic, init=False)
    _log: list[Action] = field(default_factory=list, init=False)

    # ------------------------------------------------------------------
    # Agent-facing tools
    # ------------------------------------------------------------------

    def read_file(self, path: str) -> str:
        self._check_timeout()
        result = _tools.read_file(self.sandbox, path)
        self._record("read_file", {"path": path}, result)
        return result

    def write_file(self, path: str, content: str) -> None:
        self._check_timeout()
        _tools.write_file(self.sandbox, path, content)
        self._record("write_file", {"path": path, "content": content}, None)

    def list_files(self, path: str = "") -> list[str]:
        self._check_timeout()
        result = _tools.list_files(self.sandbox, path)
        self._record("list_files", {"path": path}, result)
        return result

    def run_tests(self, suite: str = "public") -> TestResult:
        self._check_timeout()
        result = _tools.run_tests(self.sandbox, suite)
        self._record("run_tests", {"suite": suite}, result)
        return result

    def run_lint(self) -> LintResult:
        self._check_timeout()
        result = _tools.run_lint(self.sandbox)
        self._record("run_lint", {}, result)
        return result

    def log_llm(self, messages: list, response) -> None:
        """Record one LLM invoke (prompt + response) into the trajectory."""
        self._record(
            "llm_invoke",
            args={"messages": [_serialize_msg(m) for m in messages]},
            result=_serialize_msg(response),
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def trajectory(self) -> list[Action]:
        """Full action log — consumed by grader and RL trainer."""
        return list(self._log)

    @property
    def elapsed_sec(self) -> float:
        return time.monotonic() - self._start

    @property
    def remaining_sec(self) -> float:
        return max(0.0, self.timeout_sec - self.elapsed_sec)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def from_task(cls, task: "Task") -> "Session":  # noqa: F821
        sandbox = Sandbox(task.repo_path, image=task.docker_image).start()
        # Public tests are visible to the agent; private tests are injected by the grader only.
        public_tests = task.tests_path / "public"
        if public_tests.exists():
            sandbox.inject_dir(public_tests, "tests/public")
        return cls(sandbox=sandbox, timeout_sec=task.timeout_sec)

    def close(self) -> None:
        self.sandbox.stop()

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _check_timeout(self) -> None:
        if self.elapsed_sec > self.timeout_sec:
            raise TimeoutError(
                f"Session budget of {self.timeout_sec}s exceeded "
                f"({self.elapsed_sec:.1f}s elapsed)"
            )

    def _record(self, tool: str, args: dict, result: object) -> None:
        self._log.append(
            Action(
                tool=tool,
                args=args,
                result=result,
                timestamp=self.elapsed_sec,
            )
        )
