"""
Coding agent backed by a privately-hosted OpenAI-compatible LLM.

Reads credentials from environment variables:
    AGENTCODE_API_KEY   - API key for the provider
    AGENTCODE_API_URL   - Base URL for the provider
    AGENTCODE_MODEL     - Model name (default: "default")

Usage:
    from tasks import Task
    from runner import run_episode
    from agent import coding_agent

    task = Task.load("tasks/lru-cache")
    result = run_episode(task, coding_agent(task.instruction))
    print(result.grade.summary())
"""

import os
from collections.abc import Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from environment.schemas import TestResult, LintResult
from environment.session import Session

# ------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format)
# ------------------------------------------------------------------

_TOOL_SCHEMAS = [
    {
        "name": "list_files",
        "description": "List all files currently in the repo.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": "Read the full contents of a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file, relative to the repo root.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write (or overwrite) a file with new content.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file, relative to the repo root.",
                },
                "content": {
                    "type": "string",
                    "description": "Full content to write to the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_tests",
        "description": (
            "Run the public test suite against the current state of the repo. "
            "Returns a pass/fail breakdown per test and a summary score."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "run_lint",
        "description": (
            "Run the linter (ruff) on the repo. "
            "Returns a list of errors with file, line, and message."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

_SYSTEM_PROMPT = """\
You are a software engineering agent. You will be given a coding task and a set \
of tools to read and modify files in a sandboxed repository.

Work iteratively:
1. Read the relevant files to understand the scaffold.
2. Implement the required code.
3. Run the tests to check your work.
4. Fix any failures, then run lint and fix any errors.
5. When the tests pass and lint is clean, stop — do not call any more tools.

Write correct, idiomatic Python. Do not add unnecessary comments or docstrings \
beyond what helps readability.\
"""


# ------------------------------------------------------------------
# Tool result formatting (what the LLM sees as tool output)
# ------------------------------------------------------------------

def _fmt_test_result(result: TestResult) -> str:
    lines = [f"Tests: {result.passed}/{result.total} passed"]
    for case in result.cases:
        status = "PASS" if case.passed else "FAIL"
        lines.append(f"  [{status}] {case.name}")
        if case.error:
            # include first 10 lines of the error to keep context manageable
            error_lines = case.error.strip().splitlines()[:10]
            lines.extend(f"         {l}" for l in error_lines)
    return "\n".join(lines)


def _fmt_lint_result(result: LintResult) -> str:
    if not result.errors:
        return "Lint: clean"
    lines = [f"Lint: {len(result.errors)} error(s)"]
    for e in result.errors:
        lines.append(f"  {e.path}:{e.line}:{e.col}  {e.code}  {e.message}")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Tool dispatch (maps LLM tool calls → session calls)
# ------------------------------------------------------------------

def _dispatch(name: str, args: dict, session: Session) -> str:
    if name == "list_files":
        files = session.list_files()
        return "\n".join(f.replace("\\", "/") for f in files) if files else "(no files)"
    if name == "read_file":
        return session.read_file(args["path"])
    if name == "write_file":
        session.write_file(args["path"], args["content"])
        return "Written successfully."
    if name == "run_tests":
        return _fmt_test_result(session.run_tests())
    if name == "run_lint":
        return _fmt_lint_result(session.run_lint())
    return f"Unknown tool: {name}"


# ------------------------------------------------------------------
# Agent factory
# ------------------------------------------------------------------

def coding_agent(instruction: str) -> Callable[[Session], None]:
    """
    Returns an agent function ready to pass to run_episode().

    The LLM client is initialised once per agent call so that
    multiple episodes can share a single process without re-reading env vars.
    """
    llm = ChatOpenAI(
        model=os.environ.get("AGENTCODE_MODEL", "default"),
        api_key=os.environ["AGENTCODE_API_KEY"],
        base_url=os.environ["AGENTCODE_API_URL"],
    ).bind_tools(_TOOL_SCHEMAS)

    MAX_TURNS = 25

    def _agent(session: Session) -> None:
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=instruction),
        ]

        _empty_turns = 0
        _turns = 0
        while _turns < MAX_TURNS:
            response: AIMessage = llm.invoke(messages)
            session.log_llm(messages, response)
            messages.append(response)
            _turns += 1

            if not response.tool_calls:
                if not (response.content or "").strip():
                    # Model returned a blank response — nudge it once, then give up
                    _empty_turns += 1
                    if _empty_turns < 3:
                        messages.append(HumanMessage(content="Continue. Use the write_file tool to implement the solution."))
                        continue
                break

            _empty_turns = 0
            for call in response.tool_calls:
                try:
                    result = _dispatch(call["name"], call["args"], session)
                except Exception as exc:
                    result = f"Error: {exc}"

                messages.append(
                    ToolMessage(content=result, tool_call_id=call["id"])
                )

    return _agent
