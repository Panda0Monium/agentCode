"""
What the lint score is allowed to measure.

lint_score feeds the reward, so its definition has to be a property of the
benchmark rather than of the host filesystem, the task author's file count, or
whichever ruff release happened to be installed when the image was built.
"""

import re
from pathlib import Path

import pytest

from environment.tools import LINT_EXCLUDE, LINT_IGNORE, lint_command

DOCKER_DIR = Path(__file__).resolve().parent.parent / "docker"


# ------------------------------------------------------------------
# The lint invocation
# ------------------------------------------------------------------

def test_exe002_is_ignored():
    """
    EXE002 measures the filesystem, not the code. Bind-mounting from a host
    without POSIX permission bits presents every file as 0777, so it fires once
    per .py file — including files the agent never wrote and cannot chmod — and
    never fires on Linux at all. Left in, local and production scores are not
    comparable.
    """
    assert "EXE002" in LINT_IGNORE
    assert "--ignore" in lint_command()
    assert "EXE002" in lint_command()


def test_harness_owned_tests_are_excluded():
    # Private tests are injected by the grader *after* the agent stops, so
    # linting them scores the agent on files it cannot see.
    assert "tests" in LINT_EXCLUDE
    assert "--exclude" in lint_command()


def test_command_still_emits_json_and_cannot_fail_the_step():
    cmd = lint_command()
    assert "--output-format json" in cmd
    assert cmd.strip().endswith("|| true")  # a lint failure must not kill the episode


def test_agent_source_is_still_in_scope():
    # The fix must not become "lint nothing" — src/ is the deliverable.
    cmd = lint_command()
    assert cmd.startswith("ruff check .")
    assert "src" not in LINT_EXCLUDE


# ------------------------------------------------------------------
# Image reproducibility
# ------------------------------------------------------------------

# The root Dockerfile builds agentcode-sandbox, the fallback for any task.yaml
# without an explicit docker_image — it carries the same defect and the same fix.
DOCKERFILES = sorted(DOCKER_DIR.glob("*.Dockerfile")) + [DOCKER_DIR.parent / "Dockerfile"]


@pytest.mark.parametrize("path", DOCKERFILES, ids=lambda p: p.name)
def test_pip_version_specs_are_quoted(path):
    """
    Regression: `pip install pytest>=8.0` inside a shell RUN is a redirection.
    pip received a bare `pytest`, the constraint was silently dropped, and a
    file called `=8.0` was created at /. Every image floated to whatever was
    latest at build time — and since ruff decides lint_score, that silently
    repriced every task between rebuilds.
    """
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue  # prose about the bug, not an instruction
        if "pip install" not in stripped:
            continue
        # Any version comparator must sit inside quotes.
        for match in re.finditer(r'(\S*[<>=]=?\S*)', stripped):
            token = match.group(1)
            if token.startswith(("'", '"')) or "==" not in token and ">=" not in token:
                continue
            assert re.search(rf'["\']{re.escape(token)}["\']', stripped), (
                f"{path.name}: unquoted version spec {token!r} — the shell reads "
                f"this as a redirection"
            )


def test_scoring_tools_are_pinned_exactly():
    """ruff and pytest are part of the reward function, so they must not float."""
    text = (DOCKER_DIR / "base.Dockerfile").read_text(encoding="utf-8")
    assert re.search(r'"ruff==\d+\.\d+', text), "ruff must be pinned exactly"
    assert re.search(r'"pytest==\d+\.\d+', text), "pytest must be pinned exactly"
