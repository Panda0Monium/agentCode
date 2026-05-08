import os
import sys
import traceback
from pathlib import Path

# Make the agentCode root importable (runner, agent, tasks, etc. live there)
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / '.env')


def execute_run(run_id: int) -> None:
    from django.utils import timezone
    from runs.models import Run
    from runs.trajectory import process as process_trajectory
    from tasks.task import Task
    from runner import run_episode
    from agent import coding_agent

    # Atomically claim the run — only one worker wins this UPDATE.
    # If another worker already claimed it, updated=0 and we bail out.
    claimed = Run.objects.filter(pk=run_id, status=Run.Status.PENDING).update(
        status=Run.Status.RUNNING,
        started_at=timezone.now(),
    )
    if not claimed:
        return

    run = Run.objects.select_related('user').get(pk=run_id)

    try:
        user = run.user
        os.environ['AGENTCODE_API_KEY'] = user.model_api_key
        os.environ['AGENTCODE_API_URL'] = user.model_api_url
        os.environ['AGENTCODE_MODEL']   = user.model_name

        task = Task.load(_ROOT / 'tasks' / run.task_name)
        result = run_episode(task, coding_agent(task.instruction))

        run.status        = Run.Status.DONE
        run.reward        = result.reward
        run.public_score  = result.grade.public_score
        run.private_score = result.grade.private_score
        run.lint_score    = result.grade.lint_score
        run.trajectory    = process_trajectory(result.trajectory)
        run.completed_at  = timezone.now()
        run.save()

    except Exception:
        run.status       = Run.Status.FAILED
        run.error        = traceback.format_exc()
        run.completed_at = timezone.now()
        run.save()
