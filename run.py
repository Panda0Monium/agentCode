"""
Entry point for running episodes: one task, a whole dataset, or a sweep across
agent architectures.

    python run.py tasks/default/lru-cache                        # single task, ReAct
    python run.py tasks/default/lru-cache --agent reflexion      # a different architecture
    python run.py tasks/default/lru-cache --agents react,tdd     # compare two on one task
    python run.py tasks/classeval --all                          # whole dataset, 4 workers
    python run.py tasks/classeval --all --agents react,reflexion # dataset x architectures
    python run.py tasks/default/lru-cache --noop                 # harness smoke test, no LLM
    python run.py --list-agents                                  # what's available

Sweeps are the point: --agents runs the cartesian product of tasks and
architectures and writes a by_agent comparison block into the bulk report.
"""

import argparse
import io
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from reports import write_bulk_report, write_report
from runner import run_episode
from tasks import Task


class _ThreadLocalStdout:
    """
    A stdout stand-in that routes each thread's writes to its own buffer.

    ``contextlib.redirect_stdout`` swaps the *global* ``sys.stdout``, so
    concurrent episodes overwrite each other's capture and output is silently
    lost — during a sweep, entire episodes vanish from the console while the
    results still land in the report. This proxy is installed once and
    dispatches per thread instead.
    """

    def __init__(self, real):
        self._real = real
        self._local = threading.local()

    def _target(self):
        return getattr(self._local, "buf", None) or self._real

    def write(self, s):
        return self._target().write(s)

    def flush(self):
        return self._target().flush()

    def __getattr__(self, name):
        return getattr(self._real, name)

    @contextmanager
    def capture(self):
        prev = getattr(self._local, "buf", None)
        buf = io.StringIO()
        self._local.buf = buf
        try:
            yield buf
        finally:
            self._local.buf = prev


_proxy: _ThreadLocalStdout | None = None


def _install_stdout_proxy() -> _ThreadLocalStdout:
    """Installed only for parallel runs, so importing this module is harmless."""
    global _proxy
    if _proxy is None:
        _proxy = _ThreadLocalStdout(sys.stdout)
        sys.stdout = _proxy
    return _proxy


@contextmanager
def _capture():
    """Capture this thread's stdout, whether or not the proxy is installed."""
    if _proxy is not None:
        with _proxy.capture() as buf:
            yield buf
    else:
        buf = io.StringIO()
        with redirect_stdout(buf):
            yield buf


def run_task(
    task_dir: Path,
    agent_name: str = "react",
    bulk: bool = False,
    max_tokens: int | None = None,
) -> tuple[str, dict | None]:
    with _capture() as buf:
        task = Task.load(task_dir)

        # Imported lazily so the provider client is only built when an
        # architecture actually calls an LLM — --noop needs no API key.
        from agents import build_agent
        agent = build_agent(agent_name, task, max_tokens=max_tokens)

        result = run_episode(task, agent)
        g = result.grade

        if bulk:
            status = ""
            if result.timed_out:
                status = "  [TIMEOUT]"
            elif result.agent_error:
                status = "  [ERROR]"
            elif result.budget_exhausted:
                status = "  [BUDGET]"
            print(
                f"{task.name}  [{task.difficulty}]"
                f"  agent={result.agent_name}"
                f"  reward={result.reward:.3f}"
                f"  pub={g.public_result.passed}/{g.public_result.total}"
                f"  priv={g.private_result.passed}/{g.private_result.total}"
                f"  lint={g.lint_score:.2f}"
                f"  tok={result.tokens_used}"
                f"  {result.elapsed_sec:.1f}s{status}"
            )
        else:
            print(f"Task:    {task.name}  ({task.difficulty})")
            print(f"Agent:   {result.agent_name}")
            # The effective budget, which multi-round architectures scale up —
            # printing the task's raw timeout here reads as a missed timeout.
            effective = result.timeout_sec or task.timeout_sec
            scaled = "" if effective == task.timeout_sec else f"  (task {task.timeout_sec}s x{effective / task.timeout_sec:g})"
            print(f"Timeout: {effective}s{scaled}")
            print(f"Tokens:  {result.tokens_used} / {result.token_budget or 'unlimited'}"
                  f"{'  [EXHAUSTED]' if result.budget_exhausted else ''}\n")
            print("-" * 40)
            print(g.summary())
            print("-" * 40)
            print(f"Elapsed:   {result.elapsed_sec:.1f}s")
            print(f"Timed out: {result.timed_out}")
            print(f"Steps:     {len(result.trajectory)}")
            if result.agent_error:
                print(f"\nAgent error:\n{result.agent_error}")

        metrics = None
        if agent_name != "noop":
            if bulk:
                metrics = {
                    "task": task.name,
                    "agent": result.agent_name,
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
                    "tokens_used": result.tokens_used,
                    "token_budget": result.token_budget,
                    "budget_exhausted": result.budget_exhausted,
                    "timed_out": result.timed_out,
                    "agent_error": result.agent_error,
                }
            else:
                path = write_report(task, result)
                print(f"Report: {path}")

    return buf.getvalue(), metrics


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def _build_parser(agent_choices: list[str]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("target", nargs="?", type=Path,
                        help="A task directory, or a parent directory when using --all.")
    parser.add_argument("--all", action="store_true",
                        help="Run every task directory under target.")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel episodes (default: 4).")
    parser.add_argument("--agent", default=None, choices=agent_choices,
                        help="Agent architecture to run (default: react).")
    parser.add_argument("--agents", default=None,
                        help="Comma-separated architectures to sweep, e.g. react,reflexion.")
    parser.add_argument("--max-tokens", type=int, default=None, dest="max_tokens",
                        help="Override the per-run token budget (default: from task difficulty).")
    parser.add_argument("--noop", action="store_true",
                        help="Shorthand for --agent noop. Runs the harness with no LLM.")
    parser.add_argument("--list-agents", action="store_true",
                        help="List available architectures and exit.")
    return parser


def _resolve_agents(args, agent_choices: list[str]) -> list[str]:
    """--noop beats --agent; --agents beats both."""
    if args.agents:
        names = [n.strip() for n in args.agents.split(",") if n.strip()]
        unknown = [n for n in names if n not in agent_choices]
        if unknown:
            raise SystemExit(
                f"Unknown architecture(s): {', '.join(unknown)}. "
                f"Available: {', '.join(agent_choices)}"
            )
        return names
    if args.noop:
        return ["noop"]
    return [args.agent or "react"]


def _print_agents() -> None:
    from agents import list_agents
    width = max(len(s.name) for s in list_agents())
    print("Available agent architectures:\n")
    for spec in list_agents():
        print(f"  {spec.name.ljust(width)}  {spec.description}")


def _summarize_by_agent(rows: list[dict]) -> dict:
    """
    Per-architecture aggregates — the table the whole feature exists to produce.
    """
    by_agent: dict[str, dict] = {}
    for name in dict.fromkeys(r["agent"] for r in rows):
        group = [r for r in rows if r["agent"] == name]
        n = len(group)
        by_agent[name] = {
            "n": n,
            "avg_reward": round(sum(r["reward"] for r in group) / n, 4),
            "avg_public": round(sum(r["public_score"] for r in group) / n, 4),
            "avg_private": round(sum(r["private_score"] for r in group) / n, 4),
            "avg_lint": round(sum(r["lint_score"] for r in group) / n, 4),
            "avg_tokens": round(sum(r.get("tokens_used", 0) for r in group) / n, 1),
            "avg_elapsed_sec": round(sum(r["elapsed_sec"] for r in group) / n, 2),
            "n_timed_out": sum(1 for r in group if r["timed_out"]),
            "n_agent_errors": sum(1 for r in group if r["agent_error"]),
            "n_budget_exhausted": sum(1 for r in group if r.get("budget_exhausted")),
        }
    return by_agent


def _print_comparison(by_agent: dict) -> None:
    print(f"\n{'=' * 78}")
    print(f"{'agent':<16}{'n':>4}{'reward':>9}{'public':>9}{'private':>9}"
          f"{'lint':>7}{'tokens':>10}{'time':>8}")
    print("-" * 78)
    for name, m in sorted(by_agent.items(), key=lambda kv: -kv[1]["avg_reward"]):
        print(f"{name:<16}{m['n']:>4}{m['avg_reward']:>9.3f}{m['avg_public']:>9.3f}"
              f"{m['avg_private']:>9.3f}{m['avg_lint']:>7.2f}"
              f"{m['avg_tokens']:>10.0f}{m['avg_elapsed_sec']:>8.1f}")
    print("=" * 78)


def main():
    from agents import agent_names
    agent_choices = agent_names()

    parser = _build_parser(agent_choices)
    args = parser.parse_args()

    if args.list_agents:
        _print_agents()
        return

    if args.target is None:
        parser.error("target is required (a task directory, or a parent directory with --all)")

    agents_to_run = _resolve_agents(args, agent_choices)

    if args.all:
        task_dirs = sorted(d for d in args.target.iterdir() if (d / "task.yaml").exists())
        if not task_dirs:
            print(f"No tasks found under {args.target}")
            sys.exit(1)
    else:
        task_dirs = [args.target]

    # A sweep is the cartesian product of tasks and architectures.
    jobs = [(d, a) for d in task_dirs for a in agents_to_run]
    bulk = args.all or len(jobs) > 1

    if not bulk:
        output, _ = run_task(jobs[0][0], jobs[0][1], max_tokens=args.max_tokens)
        print(output)
        return

    print(f"Running {len(task_dirs)} task(s) x {len(agents_to_run)} architecture(s) "
          f"= {len(jobs)} episodes ({args.workers} workers)\n")

    # Episodes run concurrently and each captures its own stdout; without this
    # they would fight over the global one and lose each other's output.
    _install_stdout_proxy()

    all_metrics: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(run_task, d, a, True, args.max_tokens): (d, a)
            for d, a in jobs
        }
        completed = 0
        for future in as_completed(futures):
            completed += 1
            task_dir, agent_name = futures[future]
            print(f"[{completed}/{len(jobs)}] {task_dir.name} ({agent_name})")
            try:
                output, metrics = future.result()
                print(output)
                if metrics is not None:
                    all_metrics.append(metrics)
            except Exception as e:
                print(f"ERROR: {e}\n")

    if all_metrics:
        by_agent = _summarize_by_agent(all_metrics)
        bulk_path = write_bulk_report(all_metrics, by_agent=by_agent)
        n = len(all_metrics)
        avg_reward = sum(r["reward"] for r in all_metrics) / n
        n_timeout = sum(1 for r in all_metrics if r["timed_out"])
        n_errors = sum(1 for r in all_metrics if r["agent_error"])
        print(f"\n{'=' * 40}")
        print(f"Episodes: {n}  |  avg reward: {avg_reward:.3f}  |  "
              f"timed out: {n_timeout}  |  errors: {n_errors}")
        print(f"{'=' * 40}")
        if len(by_agent) > 1:
            _print_comparison(by_agent)
        print(f"Bulk report: {bulk_path}")


if __name__ == "__main__":
    main()
