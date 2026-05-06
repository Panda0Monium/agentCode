"""
Write structured JSON reports for each episode run.

Each run gets its own folder inside output/:

    output/episodes/<task>_<timestamp>/
        summary.json     ← always written; references siblings
        tests.json       ← test case arrays + lint errors
        trajectory.json  ← tool actions + LLM turns interleaved
        code.zip         ← final file states (whenever any file is written)
        diffs.zip        ← one unified diff per write_file action
"""

import difflib
import io
import json
import os
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from runner import EpisodeResult
from tasks.task import Task


def write_report(task: Task, result: EpisodeResult) -> Path:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    ts_display = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    run_dir = Path("output") / "episodes" / f"{task.name}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    g = result.grade
    w = g.weights
    trajectory = result.trajectory

    # ------------------------------------------------------------------
    # Derive summary fields from trajectory
    # ------------------------------------------------------------------
    tool_counts: Counter = Counter(a.tool for a in trajectory)
    llm_turns = tool_counts.get("llm_invoke", 0)

    files_read = list(dict.fromkeys(
        a.args["path"] for a in trajectory
        if a.tool == "read_file" and "path" in a.args
    ))
    files_written = list(dict.fromkeys(
        a.args["path"] for a in trajectory
        if a.tool == "write_file" and "path" in a.args
    ))

    # agent_output: null / zip-ref
    agent_output = None
    code_zip = False
    if files_written:
        code_zip = True
        agent_output = {"zip": "code.zip", "files": files_written}

    model = os.environ.get("AGENTCODE_MODEL") or None

    # ------------------------------------------------------------------
    # errors/ — one .txt file per failed test
    # ------------------------------------------------------------------
    def _error_filename(test_name: str) -> str:
        safe = test_name.replace("::", "__").replace("/", "__").replace("\\", "__")
        return f"{safe}.txt"

    all_cases = [
        (tc, "public") for tc in g.public_result.cases
    ] + [
        (tc, "private") for tc in g.private_result.cases
    ]
    errors_written = False
    errors_dir = run_dir / "errors"
    for tc, suite in all_cases:
        if tc.error:
            if not errors_written:
                errors_dir.mkdir(exist_ok=True)
                errors_written = True
            filename = _error_filename(tc.name)
            (errors_dir / filename).write_text(tc.error, encoding="utf-8")

    # ------------------------------------------------------------------
    # tests.json
    # ------------------------------------------------------------------
    tests_doc = {
        "task": task.name,
        "timestamp": ts_display,
        "public_tests": [
            {
                "name": tc.name,
                "passed": tc.passed,
                "duration_ms": tc.duration_ms,
            }
            for tc in g.public_result.cases
        ],
        "private_tests": [
            {
                "name": tc.name,
                "passed": tc.passed,
                "duration_ms": tc.duration_ms,
            }
            for tc in g.private_result.cases
        ],
        "lint_errors": [
            {
                "path": e.path,
                "line": e.line,
                "col": e.col,
                "code": e.code,
                "message": e.message,
            }
            for e in g.lint_result.errors
        ],
    }
    (run_dir / "tests.json").write_text(json.dumps(tests_doc, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # diffs.zip — one unified diff entry per write_file action
    # ------------------------------------------------------------------
    prev_content: dict[str, str] = {}
    write_counter: dict[str, int] = {}
    action_diffs: dict[int, str] = {}
    diffs_buf = io.BytesIO()

    with zipfile.ZipFile(diffs_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, action in enumerate(trajectory):
            if action.tool == "read_file" and isinstance(action.result, str):
                prev_content[action.args.get("path", "")] = action.result
            elif action.tool == "write_file" and "path" in action.args:
                path = action.args["path"]
                new_content = action.args.get("content", "")
                before = prev_content.get(path, "")
                diff = "".join(difflib.unified_diff(
                    before.splitlines(keepends=True),
                    new_content.splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                ))
                write_counter[path] = write_counter.get(path, 0) + 1
                norm = path.replace("/", "__").replace("\\", "__")
                entry = f"write_{write_counter[path]:04d}_{norm}.diff"
                zf.writestr(entry, diff)
                action_diffs[i] = entry
                prev_content[path] = new_content

    if action_diffs:
        (run_dir / "diffs.zip").write_bytes(diffs_buf.getvalue())

    # ------------------------------------------------------------------
    # trajectory.json
    # ------------------------------------------------------------------
    def _strip_write_content(tc: dict) -> dict:
        """Remove 'content' from a write_file tool-call's args."""
        if not isinstance(tc, dict) or tc.get("name") != "write_file":
            return tc
        return {**tc, "args": {k: v for k, v in tc.get("args", {}).items() if k != "content"}}

    def _clean_message(msg: dict) -> dict:
        if "tool_calls" not in msg:
            return msg
        return {**msg, "tool_calls": [_strip_write_content(tc) for tc in msg["tool_calls"]]}

    def _action_to_dict(action, idx) -> dict:
        if action.tool == "llm_invoke":
            args = dict(action.args)
            if "messages" in args:
                args["messages"] = [_clean_message(m) for m in args["messages"]]
            result = action.result
            if isinstance(result, dict) and "tool_calls" in result:
                result = {**result, "tool_calls": [_strip_write_content(tc) for tc in result["tool_calls"]]}
            return {
                "tool": "llm_invoke",
                "timestamp": round(action.timestamp, 3),
                "args": args,
                "result": result,
            }
        args = {k: v for k, v in action.args.items() if k != "content"}
        if action.tool == "write_file" and idx in action_diffs:
            args["diff"] = action_diffs[idx]
        return {
            "tool": action.tool,
            "args": args,
            "timestamp": round(action.timestamp, 3),
        }

    trajectory_doc = {
        "task": task.name,
        "timestamp": ts_display,
        "actions": [_action_to_dict(a, i) for i, a in enumerate(trajectory)],
    }
    (run_dir / "trajectory.json").write_text(
        json.dumps(trajectory_doc, indent=2), encoding="utf-8"
    )

    # ------------------------------------------------------------------
    # code.zip (whenever any file is written)
    # ------------------------------------------------------------------
    if code_zip:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            last_content: dict[str, str] = {}
            for a in trajectory:
                if a.tool == "write_file" and "path" in a.args:
                    last_content[a.args["path"]] = a.args.get("content", "")
            for fpath, content in last_content.items():
                zf.writestr(fpath, content)
        (run_dir / "code.zip").write_bytes(buf.getvalue())

    # ------------------------------------------------------------------
    # logs/ — container stdout/stderr on ungraceful exit
    # ------------------------------------------------------------------
    if result.container_logs:
        logs_dir = run_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        (logs_dir / "container.log").write_text(result.container_logs, encoding="utf-8")

    # ------------------------------------------------------------------
    # summary.json
    # ------------------------------------------------------------------
    budget_sec = task.timeout_sec
    summary_doc = {
        "task": task.name,
        "task_instruction": task.instruction,
        "task_difficulty": task.difficulty,
        "task_language": task.language,
        "model": model,
        "timestamp": ts_display,
        "elapsed_sec": round(result.elapsed_sec, 2),
        "budget_sec": budget_sec,
        "budget_utilization": round(result.elapsed_sec / budget_sec, 4) if budget_sec else None,
        "timed_out": result.timed_out,
        "agent_error": result.agent_error,
        "reward": result.reward,
        "scores": {
            "public": {
                "score": g.public_score,
                "passed": g.public_result.passed,
                "total": g.public_result.total,
            },
            "private": {
                "score": g.private_score,
                "passed": g.private_result.passed,
                "total": g.private_result.total,
            },
            "lint": {
                "score": g.lint_score,
                "errors": len(g.lint_result.errors),
            },
        },
        "weights": {
            "public": w.public,
            "private": w.private,
            "lint": w.lint,
        },
        "tool_counts": dict(tool_counts),
        "llm_turns": llm_turns,
        "files_read": files_read,
        "files_written": files_written,
        "agent_output": agent_output,
        "files": {
            "tests": "tests.json",
            "trajectory": "trajectory.json",
            "code_zip": "code.zip" if code_zip else None,
            "diffs_zip": "diffs.zip" if action_diffs else None,
            "errors_dir": "errors" if errors_written else None,
            "logs_dir": "logs" if result.container_logs else None,
        },
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary_doc, indent=2), encoding="utf-8")

    return summary_path


def write_bulk_report(rows: list[dict]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    ts_display = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    out_dir = Path("output") / "eval" / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    n = len(rows)
    doc = {
        "meta": {
            "timestamp": ts_display,
            "n_tasks": n,
            "avg_reward": round(sum(r["reward"] for r in rows) / n, 4) if n else 0.0,
            "avg_public_score": round(sum(r["public_score"] for r in rows) / n, 4) if n else 0.0,
            "avg_private_score": round(sum(r["private_score"] for r in rows) / n, 4) if n else 0.0,
            "avg_lint_score": round(sum(r["lint_score"] for r in rows) / n, 4) if n else 0.0,
            "n_timed_out": sum(1 for r in rows if r["timed_out"]),
            "n_agent_errors": sum(1 for r in rows if r["agent_error"]),
        },
        "results": rows,
    }

    results_path = out_dir / "results.json"
    results_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return results_path
