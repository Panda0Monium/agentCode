import logging
import os
import sys
import traceback
from pathlib import Path

logger = logging.getLogger('runs')

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
        user    = run.user
        api_key = user.model_api_key
        if not api_key:
            from allauth.socialaccount.models import SocialAccount, SocialToken
            social = SocialAccount.objects.filter(user=user, provider='huggingface').first()
            if social:
                token = SocialToken.objects.filter(account=social).first()
                if token:
                    api_key = token.token
        if not api_key:
            raise RuntimeError('No API key available. Re-login with Hugging Face to refresh the session token.')
        os.environ['AGENTCODE_API_KEY'] = api_key
        os.environ['AGENTCODE_API_URL'] = user.model_api_url
        os.environ['AGENTCODE_MODEL']   = user.model_name

        task = Task.load(_ROOT / 'tasks' / run.task_name)
        result = run_episode(task, coding_agent(task.instruction))

        if result.agent_error:
            logger.error('Run %s agent error:\n%s', run.uuid, result.agent_error)

        run.status        = Run.Status.DONE
        run.reward        = result.reward
        run.public_score  = result.grade.public_score
        run.private_score = result.grade.private_score
        run.lint_score    = result.grade.lint_score
        run.trajectory    = process_trajectory(result.trajectory)
        run.error         = result.agent_error or ''
        run.completed_at  = timezone.now()
        run.save()

    except Exception:
        tb = traceback.format_exc()
        logger.error('Run %s failed:\n%s', run.uuid, tb)
        run.status       = Run.Status.FAILED
        run.error        = tb
        run.completed_at = timezone.now()
        run.save()
