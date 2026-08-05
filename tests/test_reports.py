"""
Report writing, exercised without Docker.

write_report only reads an EpisodeResult and a Task, so the whole reporting
path can be driven from synthetic objects — which is how the architecture and
token fields get verified on a machine with no container runtime.
"""

import json
from pathlib import Path

import pytest

from environment.schemas import Action
from grader import GradeResult
from reports import write_report
from runner import EpisodeResult
from tasks.task import GraderWeights, Task
from tests.fakes import clean_lint, failing_tests, passing_tests


@pytest.fixture
def task(tmp_path):
    return Task(
        name="demo-task",
        instruction="Implement solve().",
        language="python",
        difficulty="medium",
        timeout_sec=300.0,
        weights=GraderWeights(),
        repo_path=tmp_path / "repo",
        tests_path=tmp_path / "tests",
    )


def _grade():
    return GradeResult(
        reward=0.72,
        public_score=1.0,
        private_score=0.6,
        lint_score=1.0,
        public_result=passing_tests(3),
        private_result=failing_tests(3, 2),
        lint_result=clean_lint(),
        weights=GraderWeights(),
    )


def _result(**kw):
    base = dict(
        task_name="demo-task",
        reward=0.72,
        grade=_grade(),
        trajectory=[
            Action(tool="llm_invoke", args={"messages": []}, result={"role": "ai", "content": "hi"}, timestamp=0.1),
            Action(tool="agent_note", args={"kind": "plan", "text": "1. do it"}, result=None, timestamp=0.2),
            Action(tool="agent_note", args={"kind": "reflection", "text": "missed a case"}, result=None, timestamp=0.3),
            Action(tool="agent_note", args={"kind": "plan", "text": "1. do it again"}, result=None, timestamp=0.4),
            Action(tool="write_file", args={"path": "src/solution.py", "content": "x = 1\n"}, result=None, timestamp=0.5),
        ],
        elapsed_sec=42.0,
        timed_out=False,
        agent_error=None,
    )
    base.update(kw)
    return EpisodeResult(**base)


def _summary(tmp_path, monkeypatch, task, result):
    monkeypatch.chdir(tmp_path)
    path = write_report(task, result)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_summary_records_which_architecture_ran(tmp_path, monkeypatch, task):
    doc = _summary(tmp_path, monkeypatch, task, _result(agent_name="reflexion"))
    assert doc["agent"] == "reflexion"


def test_summary_records_token_spend_and_utilization(tmp_path, monkeypatch, task):
    result = _result(
        agent_name="react",
        tokens_used=50_000,
        token_budget=250_000,
        token_usage={"total_tokens": 50_000, "calls": 12},
        budget_exhausted=False,
    )
    doc = _summary(tmp_path, monkeypatch, task, result)

    assert doc["tokens_used"] == 50_000
    assert doc["token_budget"] == 250_000
    assert doc["token_utilization"] == 0.2
    assert doc["budget_exhausted"] is False
    assert doc["token_usage"]["calls"] == 12


def test_budget_exhausted_run_is_still_a_graded_run(tmp_path, monkeypatch, task):
    result = _result(tokens_used=250_000, token_budget=250_000, budget_exhausted=True)
    doc = _summary(tmp_path, monkeypatch, task, result)

    assert doc["budget_exhausted"] is True
    assert doc["reward"] == 0.72          # graded, not discarded
    assert doc["agent_error"] is None     # and not reported as a crash


def test_notes_are_broken_down_by_kind(tmp_path, monkeypatch, task):
    # tool_counts alone would show a flat "agent_note: 3", which tells you
    # nothing about what the architecture actually did.
    doc = _summary(tmp_path, monkeypatch, task, _result())
    assert doc["tool_counts"]["agent_note"] == 3
    assert doc["note_counts"] == {"plan": 2, "reflection": 1}


def test_unbudgeted_run_reports_nulls_rather_than_fake_zeros(tmp_path, monkeypatch, task):
    doc = _summary(tmp_path, monkeypatch, task, _result())
    assert doc["token_budget"] is None
    assert doc["token_utilization"] is None


def test_existing_summary_fields_are_untouched(tmp_path, monkeypatch, task):
    # Every change to summary.json must be additive, or historical reports
    # stop being comparable to new ones.
    doc = _summary(tmp_path, monkeypatch, task, _result())
    for key in (
        "task", "task_instruction", "task_difficulty", "task_language", "model",
        "timestamp", "elapsed_sec", "budget_sec", "budget_utilization", "timed_out",
        "agent_error", "reward", "scores", "weights", "tool_counts", "llm_turns",
        "files_read", "files_written", "agent_output", "files",
    ):
        assert key in doc, f"summary.json lost the {key!r} field"
    assert doc["scores"]["public"]["passed"] == 3
    assert doc["llm_turns"] == 1
