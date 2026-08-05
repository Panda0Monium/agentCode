"""
Web trajectory processing.

runs.trajectory.process is a pure function over Action objects, so it can be
tested without Django models, a database or Docker.
"""

import sys
from pathlib import Path

import pytest

from environment.schemas import Action

WEBSERVER = Path(__file__).resolve().parent.parent / "webserver"
if str(WEBSERVER) not in sys.path:
    sys.path.insert(0, str(WEBSERVER))

from runs.tasks import _make_live_entry  # noqa: E402
from runs.trajectory import process  # noqa: E402


def _action(tool, args=None, result=None, ts=1.0):
    return Action(tool=tool, args=args or {}, result=result, timestamp=ts)


# ------------------------------------------------------------------
# The silent-drop bug
# ------------------------------------------------------------------

def test_unknown_action_types_are_not_dropped():
    # Regression: process() had no else branch, so any action type it didn't
    # recognise vanished from the viewer — silently misrepresenting the run.
    steps = process([
        _action("read_file", {"path": "a.py"}, "x = 1"),
        _action("some_future_action", {"whatever": 1}),
        _action("run_lint", {}, None),
    ])["steps"]

    assert len(steps) == 3
    assert steps[1]["tool"] == "some_future_action"
    assert steps[1]["timestamp"] == 1.0


def test_every_action_produces_exactly_one_step():
    actions = [
        _action("llm_invoke", {"messages": []}, {"content": "hi", "tool_calls": []}),
        _action("read_file", {"path": "a.py"}, "x = 1"),
        _action("write_file", {"path": "a.py", "content": "x = 2"}),
        _action("list_files", {}, ["a.py"]),
        _action("run_tests", {"suite": "public"}, {"passed": 1, "total": 2, "cases": []}),
        _action("run_lint", {}, {"errors": []}),
        _action("agent_note", {"kind": "plan", "text": "1. do it"}),
        _action("mystery", {}),
    ]
    assert len(process(actions)["steps"]) == len(actions)


# ------------------------------------------------------------------
# agent_note rendering
# ------------------------------------------------------------------

def test_agent_note_carries_kind_and_text():
    steps = process([_action("agent_note", {"kind": "reflection", "text": "I missed a case."})])["steps"]
    assert steps[0] == {
        "tool": "agent_note",
        "timestamp": 1.0,
        "kind": "reflection",
        "text": "I missed a case.",
        "meta": {},
    }


def test_agent_note_extra_fields_land_in_meta():
    steps = process([
        _action("agent_note", {"kind": "critique", "text": "Needs work.", "verdict": "REVISE", "round": 2})
    ])["steps"]
    assert steps[0]["meta"] == {"verdict": "REVISE", "round": 2}


def test_agent_note_text_is_truncated():
    steps = process([_action("agent_note", {"kind": "plan", "text": "x" * 5000})])["steps"]
    assert len(steps[0]["text"]) == 3000


def test_agent_note_without_a_kind_still_renders():
    steps = process([_action("agent_note", {"text": "hmm"})])["steps"]
    assert steps[0]["kind"] == "note"


# ------------------------------------------------------------------
# Live console entries
# ------------------------------------------------------------------

def test_live_entry_for_agent_note():
    entry = _make_live_entry(_action("agent_note", {"kind": "plan", "text": "1. read\n2. write"}))
    assert entry["tool"] == "note"
    assert entry["kind"] == "plan"
    assert "1. read" in entry["text"]


def test_live_entry_truncates_long_notes():
    entry = _make_live_entry(_action("agent_note", {"kind": "plan", "text": "y" * 500}))
    assert len(entry["text"]) == 160


def test_live_entry_falls_back_for_unknown_tools():
    entry = _make_live_entry(_action("mystery", {}))
    assert entry == {"tool": "mystery", "ts": 1.0}


# ------------------------------------------------------------------
# Existing behaviour still intact
# ------------------------------------------------------------------

def test_write_file_still_produces_a_diff_against_the_prior_read():
    steps = process([
        _action("read_file", {"path": "a.py"}, "x = 1\n"),
        _action("write_file", {"path": "a.py", "content": "x = 2\n"}),
    ])["steps"]
    assert "-x = 1" in steps[1]["diff"]
    assert "+x = 2" in steps[1]["diff"]


@pytest.mark.parametrize("tool,args,result,key", [
    ("read_file", {"path": "a.py"}, "body", "content"),
    ("list_files", {}, ["a.py", "b.py"], "files"),
])
def test_known_tools_keep_their_payloads(tool, args, result, key):
    steps = process([_action(tool, args, result)])["steps"]
    assert steps[0][key] == result
