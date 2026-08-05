"""
Run submission: architecture validation and token-budget clamping.

These exercise the pure helpers in runs.views plus the registry bridge, without
standing up a database or the Django request cycle.
"""

import sys
from pathlib import Path

import pytest

WEBSERVER = Path(__file__).resolve().parent.parent / "webserver"
if str(WEBSERVER) not in sys.path:
    sys.path.insert(0, str(WEBSERVER))


@pytest.fixture(scope="module", autouse=True)
def django_settings():
    import django
    from django.conf import settings

    if not settings.configured:
        import os
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()


# ------------------------------------------------------------------
# The registry bridge
# ------------------------------------------------------------------

def test_available_architectures_come_from_the_registry():
    from runs.agentcode import available_architectures

    names = [a["name"] for a in available_architectures()]
    assert "react" in names
    for a in available_architectures():
        assert a["label"] and a["description"]


def test_noop_is_not_offered_to_users():
    # It exists to smoke-test the harness, not to be selected in the UI.
    from runs.agentcode import architecture_names

    assert "noop" not in architecture_names()


def test_default_token_budget_tracks_difficulty():
    from agents.budget import DIFFICULTY_TOKEN_BUDGETS
    from runs.agentcode import default_token_budget

    assert default_token_budget("easy") == DIFFICULTY_TOKEN_BUDGETS["easy"]
    assert default_token_budget("hard") == DIFFICULTY_TOKEN_BUDGETS["hard"]
    assert default_token_budget("") > 0  # unknown difficulty still resolves


# ------------------------------------------------------------------
# Token budget parsing
# ------------------------------------------------------------------

def test_blank_budget_means_use_the_task_default():
    from runs.views import _parse_token_budget

    assert _parse_token_budget("") == (None, None)
    assert _parse_token_budget(None) == (None, None)


def test_budget_is_clamped_to_the_configured_ceiling():
    from django.conf import settings
    from runs.views import _parse_token_budget

    value, err = _parse_token_budget("99999999")
    assert err is None
    assert value == settings.AGENTCODE_MAX_TOKEN_BUDGET


def test_budget_below_the_floor_is_rejected():
    from runs.views import MIN_TOKEN_BUDGET, _parse_token_budget

    value, err = _parse_token_budget("100")
    assert value is None
    assert str(MIN_TOKEN_BUDGET) in err


def test_non_numeric_budget_is_rejected():
    from runs.views import _parse_token_budget

    value, err = _parse_token_budget("lots")
    assert value is None
    assert "whole number" in err


def test_valid_budget_passes_through():
    from runs.views import _parse_token_budget

    assert _parse_token_budget(" 50000 ") == (50_000, None)
