"""
Bridge from the Django app to the AgentCode harness at the repo root.

The harness (runner, agents, tasks) lives one level above the Django project,
so it has to be put on sys.path before it can be imported. That bootstrap used
to live only in tasks.py; views.py needs the agent registry too, so it lives
here and both import from it.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / '.env')

ROOT = _ROOT

# Kept small and lazy: importing the registry pulls in langchain, which is slow
# enough that it should not happen at Django startup for every request.


def available_architectures() -> list[dict]:
    """
    The architectures a user may pick, in registration order.

    Returned as plain dicts so templates and JSON responses can consume them
    without importing anything from the harness.
    """
    from agents import list_agents

    return [
        {'name': s.name, 'label': s.label, 'description': s.description}
        for s in list_agents()
        if s.name != 'noop'  # harness-only, nothing for a user to learn from
    ]


def architecture_names() -> set[str]:
    return {a['name'] for a in available_architectures()}


def default_token_budget(difficulty: str) -> int:
    from agents.budget import DEFAULT_TOKEN_BUDGET, DIFFICULTY_TOKEN_BUDGETS

    return DIFFICULTY_TOKEN_BUDGETS.get((difficulty or '').lower(), DEFAULT_TOKEN_BUDGET)
