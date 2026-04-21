"""
Episode runner: wires Task → Session → Agent → Grader into one call.

An agent is any callable that accepts a Session and returns nothing:

    def my_agent(session: Session) -> None:
        files = session.list_files()
        code = session.read_file("src/lru_cache.py")
        session.write_file("src/lru_cache.py", improved_code)
        result = session.run_tests()

Usage:

    from tasks import Task
    from runner import run_episode

    task = Task.load("tasks/lru-cache")
    result = run_episode(task, my_agent)
    print(result.grade.summary())
    print(f"reward: {result.reward:.4f}")
"""

from __future__ import annotations

import traceback
from collections.abc import Callable
from dataclasses import dataclass

from environment.schemas import Action
from environment.session import Session
from grader import GradeResult, Grader
from tasks.task import Task


@dataclass
class EpisodeResult:
    task_name: str
    reward: float
    grade: GradeResult
    trajectory: list[Action]
    elapsed_sec: float
    timed_out: bool
    agent_error: str | None   # non-timeout exception from agent, if any
    container_logs: str | None = None  # set when episode exits ungracefully


def run_episode(
    task: Task,
    agent: Callable[[Session], None],
) -> EpisodeResult:
    """
    Run one full agent episode and return the graded result.

    The agent may call session tools freely until it returns or the
    timeout fires. Either way, the grader scores whatever state the
    files are in at that point.
    """
    grader = Grader()
    timed_out = False
    agent_error = None

    print("[episode] starting session...")
    with Session.from_task(task) as session:
        try:
            agent(session)
        except TimeoutError:
            timed_out = True
        except Exception:
            agent_error = traceback.format_exc()

        elapsed = session.elapsed_sec
        trajectory = session.trajectory

        # Fetch container logs before the sandbox is torn down
        container_logs = None
        if timed_out or agent_error:
            container_logs = session.sandbox.logs() or None

        print(f"[episode] agent done ({len(trajectory)} steps) — grading...")
        grade = grader.grade(session, task)
    print("[episode] grading complete")

    return EpisodeResult(
        task_name=task.name,
        reward=grade.reward,
        grade=grade,
        trajectory=trajectory,
        elapsed_sec=elapsed,
        timed_out=timed_out,
        agent_error=agent_error,
        container_logs=container_logs,
    )
