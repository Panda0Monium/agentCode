"""
The shared tool layer every agent architecture builds on.

Moved verbatim out of the original monolithic ``agent.py`` so that all variants
see exactly the same tools, the same schemas and the same tool-result rendering.
If a variant needs different tools, it should say so explicitly rather than
quietly diverging here — the whole point of the benchmark is that architecture
is the only thing that varies.
"""

from environment.schemas import LintResult, TestResult
from environment.session import Session

# ------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format)
# ------------------------------------------------------------------

TOOL_SCHEMAS = [
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


# ------------------------------------------------------------------
# Tool result formatting (what the LLM sees as tool output)
# ------------------------------------------------------------------

def fmt_test_result(result: TestResult) -> str:
    lines = [f"Tests: {result.passed}/{result.total} passed"]
    for case in result.cases:
        status = "PASS" if case.passed else "FAIL"
        lines.append(f"  [{status}] {case.name}")
        if case.error:
            # include first 10 lines of the error to keep context manageable
            error_lines = case.error.strip().splitlines()[:10]
            lines.extend(f"         {l}" for l in error_lines)
    return "\n".join(lines)


def fmt_lint_result(result: LintResult) -> str:
    if not result.errors:
        return "Lint: clean"
    lines = [f"Lint: {len(result.errors)} error(s)"]
    for e in result.errors:
        lines.append(f"  {e.path}:{e.line}:{e.col}  {e.code}  {e.message}")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Tool dispatch (maps LLM tool calls → session calls)
# ------------------------------------------------------------------

def dispatch(name: str, args: dict, session: Session) -> str:
    if name == "list_files":
        files = session.list_files()
        return "\n".join(f.replace("\\", "/") for f in files) if files else "(no files)"
    if name == "read_file":
        return session.read_file(args["path"])
    if name == "write_file":
        session.write_file(args["path"], args["content"])
        return "Written successfully."
    if name == "run_tests":
        return fmt_test_result(session.run_tests())
    if name == "run_lint":
        return fmt_lint_result(session.run_lint())
    return f"Unknown tool: {name}"
