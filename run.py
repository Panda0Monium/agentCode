"""
Quick entry point for running a single episode.

    python run.py tasks/lru-cache          # real agent (requires env vars)
    python run.py tasks/lru-cache --noop   # submit stub unchanged, tests infra only
"""

import sys
from pathlib import Path

from reports import write_report
from runner import run_episode
from tasks import Task


def _noop_agent(session):
    pass


def main():
    if len(sys.argv) < 2:
        print("Usage: python run.py <task-dir> [--noop]")
        sys.exit(1)

    noop = "--noop" in sys.argv

    task = Task.load(Path(sys.argv[1]))
    print(f"Task:   {task.name}  ({task.difficulty})")
    print(f"Agent:  {'noop' if noop else 'llm'}")
    print(f"Timeout: {task.timeout_sec}s\n")

    if noop:
        agent = _noop_agent
    else:
        from agent import coding_agent
        agent = coding_agent(task.instruction)

    result = run_episode(task, agent)

    print(f"{'─' * 40}")
    print(result.grade.summary())
    print(f"{'─' * 40}")
    print(f"Elapsed:   {result.elapsed_sec:.1f}s")
    print(f"Timed out: {result.timed_out}")
    print(f"Steps:     {len(result.trajectory)}")
    if result.agent_error:
        print(f"\nAgent error:\n{result.agent_error}")

    path = write_report(task, result)
    print(f"Report: {path}")


if __name__ == "__main__":
    main()
