"""
In-memory doubles for Session and the LLM client.

Every architecture is a control-flow policy over the same primitives, so it can
be driven to completion against a scripted model with no Docker daemon, no
provider and no API key. That makes each variant testable in milliseconds,
which is the only reason it is practical to have several of them.
"""

from langchain_core.messages import AIMessage

from environment.schemas import Action, LintError, LintResult, TestCase, TestResult


# ------------------------------------------------------------------
# Result builders
# ------------------------------------------------------------------

def passing_tests(n: int = 3) -> TestResult:
    cases = [TestCase(name=f"test_{i}", passed=True, duration_ms=1.0, error=None) for i in range(n)]
    return TestResult(passed=n, failed=0, errors=0, cases=cases, stdout="")


def failing_tests(n_pass: int = 1, n_fail: int = 2, error: str = "AssertionError: boom") -> TestResult:
    cases = [TestCase(name=f"test_pass_{i}", passed=True, duration_ms=1.0, error=None) for i in range(n_pass)]
    cases += [TestCase(name=f"test_fail_{i}", passed=False, duration_ms=1.0, error=error) for i in range(n_fail)]
    return TestResult(passed=n_pass, failed=n_fail, errors=0, cases=cases, stdout="")


def clean_lint() -> LintResult:
    return LintResult(errors=[], score=1.0)


def dirty_lint(n: int = 2) -> LintResult:
    errors = [
        LintError(path="src/solution.py", line=i + 1, col=1, code="F401", message="unused import")
        for i in range(n)
    ]
    return LintResult(errors=errors, score=max(0.0, 1.0 - 0.05 * n))


# ------------------------------------------------------------------
# Message builders
# ------------------------------------------------------------------

def ai(content: str = "", tool_calls: list | None = None) -> AIMessage:
    """An assistant message, optionally carrying tool calls."""
    return AIMessage(content=content, tool_calls=list(tool_calls or []))


def call(name: str, _id: str | None = None, **args) -> dict:
    """A single tool call, in the shape langchain hands to the agent loop."""
    return {"name": name, "args": args, "id": _id or f"call_{name}", "type": "tool_call"}


# ------------------------------------------------------------------
# Doubles
# ------------------------------------------------------------------

class FakeSession:
    """
    A Session with an in-memory filesystem and scripted test/lint outcomes.

    Records the same Action objects the real Session does, so assertions about
    trajectories exercise the real schema.
    """

    def __init__(self, files=None, test_results=None, lint_results=None, timeout_sec: float = 300.0):
        self.files = dict(files or {})
        self.timeout_sec = timeout_sec
        self.actions: list[Action] = []
        self._test_results = list(test_results or [passing_tests()])
        self._lint_results = list(lint_results or [clean_lint()])
        self._clock = 0.0

    # -- agent-facing API ------------------------------------------------

    def read_file(self, path: str) -> str:
        if path not in self.files:
            self._record("read_file", {"path": path}, None)
            raise FileNotFoundError(path)
        content = self.files[path]
        self._record("read_file", {"path": path}, content)
        return content

    def write_file(self, path: str, content: str) -> None:
        self.files[path] = content
        self._record("write_file", {"path": path, "content": content}, None)

    def list_files(self, path: str = "") -> list[str]:
        result = sorted(self.files)
        self._record("list_files", {"path": path}, result)
        return result

    def run_tests(self, suite: str = "public") -> TestResult:
        result = self._next(self._test_results)
        self._record("run_tests", {"suite": suite}, result)
        return result

    def run_lint(self) -> LintResult:
        result = self._next(self._lint_results)
        self._record("run_lint", {}, result)
        return result

    def remove_path(self, path: str) -> bool:
        victims = [p for p in self.files if p == path or p.startswith(path.rstrip("/") + "/")]
        for p in victims:
            del self.files[p]
        self._record("remove_path", {"path": path}, bool(victims))
        return bool(victims)

    def log_llm(self, messages: list, response, usage: dict | None = None) -> None:
        result = {"role": "ai", "content": getattr(response, "content", "")}
        if usage:
            result["usage"] = usage
        self._record("llm_invoke", {"messages": list(messages)}, result)

    def log_note(self, kind: str, text: str, **extra) -> None:
        self._record("agent_note", {"kind": kind, "text": text, **extra}, None)

    # -- introspection ---------------------------------------------------

    @property
    def trajectory(self) -> list[Action]:
        return list(self.actions)

    def tool_names(self) -> list[str]:
        return [a.tool for a in self.actions]

    def note_kinds(self) -> list[str]:
        return [a.args.get("kind") for a in self.actions if a.tool == "agent_note"]

    def written(self) -> list[str]:
        return [a.args["path"] for a in self.actions if a.tool == "write_file"]

    # -- internals -------------------------------------------------------

    @staticmethod
    def _next(queue: list):
        """Pop the next scripted result, repeating the last one forever."""
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def _record(self, tool: str, args: dict, result) -> None:
        self._clock += 0.1
        self.actions.append(Action(tool=tool, args=args, result=result, timestamp=self._clock))


class FakeLLM:
    """
    A scripted model. Hands back queued responses in order and fails loudly
    when a test under-scripts it, so a runaway loop shows up as a clear error
    rather than a hang.
    """

    def __init__(self, responses: list, name: str = "llm"):
        self.responses = list(responses)
        self.name = name
        self.calls: list[list] = []

    def invoke(self, messages: list):
        self.calls.append(list(messages))
        if not self.responses:
            raise AssertionError(
                f"FakeLLM({self.name!r}) exhausted after {len(self.calls)} calls — "
                "the agent asked for more turns than the test scripted."
            )
        return self.responses.pop(0)

    def bind_tools(self, schemas):
        return self

    @property
    def exhausted(self) -> bool:
        return not self.responses
