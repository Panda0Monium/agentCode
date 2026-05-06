"""
Quick entry point for running one episode or all tasks under a directory.

    python run.py tasks/default/lru-cache                      # single task, real agent
    python run.py tasks/default/lru-cache --noop               # single task, noop agent
    python run.py tasks/classeval --all                        # all tasks, 4 workers (default)
    python run.py tasks/classeval --all --noop                 # all tasks, noop agent
    python run.py tasks/classeval --all --workers 8            # all tasks, 8 parallel workers
"""

import io
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stdout
from pathlib import Path

from reports import write_bulk_report, write_report
from runner import run_episode
from tasks import Task


def _noop_agent(session):
    pass


def run_task(task_dir: Path, noop: bool, bulk: bool = False) -> tuple[str, dict | None]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        task = Task.load(task_dir)

        if noop:
            agent = _noop_agent
        else:
            from agent import coding_agent
            agent = coding_agent(task.instruction)

        result = run_episode(task, agent)
        g = result.grade

        if bulk:
            status = ""
            if result.timed_out:
                status = "  [TIMEOUT]"
            elif result.agent_error:
                status = "  [ERROR]"
            print(
                f"{task.name}  [{task.difficulty}]"
                f"  reward={result.reward:.3f}"
                f"  pub={g.public_result.passed}/{g.public_result.total}"
                f"  priv={g.private_result.passed}/{g.private_result.total}"
                f"  lint={g.lint_score:.2f}"
                f"  {result.elapsed_sec:.1f}s{status}"
            )
        else:
            print(f"Task:   {task.name}  ({task.difficulty})")
            print(f"Agent:  {'noop' if noop else 'llm'}")
            print(f"Timeout: {task.timeout_sec}s\n")
            print("-" * 40)
            print(g.summary())
            print("-" * 40)
            print(f"Elapsed:   {result.elapsed_sec:.1f}s")
            print(f"Timed out: {result.timed_out}")
            print(f"Steps:     {len(result.trajectory)}")
            if result.agent_error:
                print(f"\nAgent error:\n{result.agent_error}")

        metrics = None
        if not noop:
            if bulk:
                metrics = {
                    "task": task.name,
                    "difficulty": task.difficulty,
                    "reward": result.reward,
                    "public_score": g.public_score,
                    "public_passed": g.public_result.passed,
                    "public_total": g.public_result.total,
                    "private_score": g.private_score,
                    "private_passed": g.private_result.passed,
                    "private_total": g.private_result.total,
                    "lint_score": g.lint_score,
                    "lint_errors": len(g.lint_result.errors),
                    "elapsed_sec": round(result.elapsed_sec, 2),
                    "timed_out": result.timed_out,
                    "agent_error": result.agent_error,
                }
            else:
                path = write_report(task, result)
                print(f"Report: {path}")

    return buf.getvalue(), metrics


def _parse_workers(argv: list[str], default: int = 4) -> int:
    try:
        idx = argv.index("--workers")
        return int(argv[idx + 1])
    except (ValueError, IndexError):
        return default


def main():
    if len(sys.argv) < 2:
        print("Usage: python run.py <task-dir> [--noop]")
        print("       python run.py <parent-dir> --all [--noop] [--workers N]")
        sys.exit(1)

    noop = "--noop" in sys.argv
    run_all = "--all" in sys.argv
    target = Path(sys.argv[1])

    if run_all:
        task_dirs = sorted(d for d in target.iterdir() if (d / "task.yaml").exists())
        if not task_dirs:
            print(f"No tasks found under {target}")
            sys.exit(1)

        workers = _parse_workers(sys.argv)
        print(f"Running {len(task_dirs)} tasks under {target} ({workers} workers)\n")

        all_metrics: list[dict] = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(run_task, d, noop, True): d for d in task_dirs}
            completed = 0
            for future in as_completed(futures):
                completed += 1
                task_dir = futures[future]
                print(f"[{completed}/{len(task_dirs)}] {task_dir.name}")
                try:
                    output, metrics = future.result()
                    print(output)
                    if metrics is not None:
                        all_metrics.append(metrics)
                except Exception as e:
                    print(f"ERROR: {e}\n")

        if all_metrics:
            bulk_path = write_bulk_report(all_metrics)
            n = len(all_metrics)
            avg_reward = sum(r["reward"] for r in all_metrics) / n
            n_timeout = sum(1 for r in all_metrics if r["timed_out"])
            n_errors = sum(1 for r in all_metrics if r["agent_error"])
            print(f"\n{'=' * 40}")
            print(f"Tasks: {n}  |  avg reward: {avg_reward:.3f}  |  timed out: {n_timeout}  |  errors: {n_errors}")
            print(f"{'=' * 40}")
            print(f"Bulk report: {bulk_path}")
    else:
        output, _ = run_task(target, noop)
        print(output)


if __name__ == "__main__":
    main()
