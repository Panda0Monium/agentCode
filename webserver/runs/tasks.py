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


def _make_live_entry(action) -> dict:
    """Convert one Action into a compact dict for the live console."""
    tool = action.tool
    ts   = round(action.timestamp, 1)
    if tool == 'llm_invoke':
        result     = action.result or {}
        text       = result.get('content') or ''
        if isinstance(text, list):
            text = ' '.join(p.get('text', '') for p in text if isinstance(p, dict))
        tool_calls = result.get('tool_calls') or []
        summary    = (text[:120].strip() if text else
                      ('Calling: ' + ', '.join(tc.get('name', '') for tc in tool_calls) if tool_calls else 'Thinking...'))
        return {'tool': 'llm', 'ts': ts, 'text': summary}
    if tool == 'read_file':
        return {'tool': 'read', 'ts': ts, 'path': action.args.get('path', '')}
    if tool == 'write_file':
        return {'tool': 'write', 'ts': ts, 'path': action.args.get('path', '')}
    if tool == 'list_files':
        files = action.result if isinstance(action.result, list) else []
        return {'tool': 'list', 'ts': ts, 'count': len(files)}
    if tool == 'run_tests':
        r = action.result
        if hasattr(r, 'passed'):
            return {'tool': 'tests', 'ts': ts, 'passed': r.passed, 'total': r.total}
        if isinstance(r, dict):
            return {'tool': 'tests', 'ts': ts, 'passed': r.get('passed', 0), 'total': r.get('total', 0)}
        return {'tool': 'tests', 'ts': ts, 'passed': 0, 'total': 0}
    if tool == 'run_lint':
        r = action.result
        if hasattr(r, 'errors'):
            return {'tool': 'lint', 'ts': ts, 'errors': len(r.errors)}
        if isinstance(r, dict):
            return {'tool': 'lint', 'ts': ts, 'errors': len(r.get('errors', []))}
        return {'tool': 'lint', 'ts': ts, 'errors': 0}
    return {'tool': tool, 'ts': ts}


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
        api_url = user.model_api_url
        model   = user.model_name

        if not api_key:
            from allauth.socialaccount.models import SocialAccount, SocialToken

            hf_social = SocialAccount.objects.filter(user=user, provider='huggingface').first()
            if hf_social:
                token = SocialToken.objects.filter(account=hf_social).first()
                if token:
                    api_key = token.token
                    api_url = api_url or 'https://api-inference.huggingface.co/v1'
                    model   = model   or 'Qwen/Qwen2.5-Coder-32B-Instruct'

            if not api_key:
                gh_social = SocialAccount.objects.filter(user=user, provider='github').first()
                if gh_social:
                    token = SocialToken.objects.filter(account=gh_social).first()
                    if token:
                        api_key = token.token
                        api_url = api_url or 'https://models.inference.ai.azure.com'
                        model   = model   or 'gpt-4o-mini'

        if not api_key:
            raise RuntimeError('No API key available. Sign in with HuggingFace or GitHub to run the agent.')
        os.environ['AGENTCODE_API_KEY'] = api_key
        os.environ['AGENTCODE_API_URL'] = api_url
        os.environ['AGENTCODE_MODEL']   = model

        task     = Task.load(_ROOT / 'tasks' / run.task_name)
        live_log: list = []

        def on_action(action):
            live_log.append(_make_live_entry(action))
            Run.objects.filter(pk=run_id).update(live_log=live_log)

        result = run_episode(task, coding_agent(task.instruction), on_action=on_action)

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
