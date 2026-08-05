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
from typing import Callable, Optional

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
    on_action: Optional[Callable] = None
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

    def log_llm(self, messages: list, response, usage: dict | None = None) -> None:
        """
        Record one LLM invoke (prompt + response) into the trajectory.

        ``usage`` carries per-call token counts when the provider reports them.
        It is folded into the serialized result rather than added as a field on
        Action, so every existing trajectory consumer keeps working unchanged.
        """
        result = _serialize_msg(response)
        if usage:
            result["usage"] = usage
        self._record(
            "llm_invoke",
            args={"messages": [_serialize_msg(m) for m in messages]},
            result=result,
        )

    def remove_path(self, path: str) -> bool:
        """
        Delete a path from the repo.

        Not exposed as an agent tool — it exists so an architecture can clean up
        scaffolding it created for its own use (see the test-driven variant,
        which must remove its scratch tests before grading).
        """
        self._check_timeout()
        removed = self.sandbox.remove_path(path)
        self._record("remove_path", {"path": path}, removed)
        return removed

    def log_note(self, kind: str, text: str, **extra) -> None:
        """
        Record a reasoning artefact — a plan, reflection, critique, skeleton.

        These are what distinguish one architecture from another, so they belong
        in the trajectory alongside tool calls. A single action type with a
        ``kind`` discriminator keeps every downstream consumer (reports, the web
        viewer, the live console) working as new architectures add new kinds.
        """
        self._record("agent_note", {"kind": kind, "text": text, **extra}, None)

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
    def from_task(
        cls,
        task: "Task",  # noqa: F821
        on_action: Optional[Callable] = None,
        timeout_sec: Optional[float] = None,
    ) -> "Session":
        """
        ``timeout_sec`` overrides the task's wall-clock budget. Multi-round
        architectures legitimately need longer than a single-pass one; without
        an override they would be recorded as timing out for reasons unrelated
        to how well they reason.
        """
        sandbox = Sandbox(task.repo_path, image=task.docker_image).start()
        # Public tests are visible to the agent; private tests are injected by the grader only.
        public_tests = task.tests_path / "public"
        if public_tests.exists():
            sandbox.inject_dir(public_tests, "tests/public")
        return cls(
            sandbox=sandbox,
            timeout_sec=timeout_sec if timeout_sec is not None else task.timeout_sec,
            on_action=on_action,
        )

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
        action = Action(
            tool=tool,
            args=args,
            result=result,
            timestamp=self.elapsed_sec,
        )
        self._log.append(action)
        if self.on_action is not None:
            try:
                self.on_action(action)
            except Exception:
                pass
