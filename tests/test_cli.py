"""
CLI argument handling and sweep aggregation.

These run without Docker: they exercise parsing, job expansion and the by_agent
rollup, stopping short of actually launching episodes.
"""

import json
import time
from pathlib import Path

import pytest

import run as cli
from reports import write_bulk_report


AGENTS = ["react", "noop"]


def _parse(argv):
    return cli._build_parser(AGENTS).parse_args(argv)


# ------------------------------------------------------------------
# Parsing
# ------------------------------------------------------------------

def test_defaults_to_react():
    args = _parse(["tasks/default/lru-cache"])
    assert cli._resolve_agents(args, AGENTS) == ["react"]
    assert args.all is False
    assert args.workers == 4


def test_noop_is_shorthand_for_the_noop_architecture():
    # The documented `run.py <dir> --noop` invocation must keep working.
    args = _parse(["tasks/default/lru-cache", "--noop"])
    assert cli._resolve_agents(args, AGENTS) == ["noop"]


def test_agent_selects_one_architecture():
    args = _parse(["tasks/default/lru-cache", "--agent", "noop"])
    assert cli._resolve_agents(args, AGENTS) == ["noop"]


def test_agents_sweeps_several_and_beats_noop():
    args = _parse(["tasks/default", "--all", "--agents", "react,noop", "--noop"])
    assert cli._resolve_agents(args, AGENTS) == ["react", "noop"]


def test_agents_tolerates_whitespace_and_trailing_commas():
    args = _parse(["t", "--agents", " react , noop , "])
    assert cli._resolve_agents(args, AGENTS) == ["react", "noop"]


def test_unknown_architecture_in_a_sweep_fails_loudly():
    args = _parse(["t", "--agents", "react,teleport"])
    with pytest.raises(SystemExit) as excinfo:
        cli._resolve_agents(args, AGENTS)
    assert "teleport" in str(excinfo.value)


def test_unknown_architecture_for_agent_is_rejected_by_argparse():
    with pytest.raises(SystemExit):
        _parse(["t", "--agent", "teleport"])


def test_flags_may_precede_the_target():
    # The old hand-rolled parser assumed sys.argv[1] was the target.
    args = _parse(["--agent", "noop", "--workers", "8", "tasks/default/lru-cache"])
    assert args.target == Path("tasks/default/lru-cache")
    assert args.workers == 8


def test_max_tokens_is_parsed_as_an_int():
    args = _parse(["t", "--max-tokens", "50000"])
    assert args.max_tokens == 50_000


def test_bad_workers_value_is_rejected_rather_than_silently_defaulted():
    # The previous _parse_workers swallowed ValueError and returned 4.
    with pytest.raises(SystemExit):
        _parse(["t", "--workers", "lots"])


# ------------------------------------------------------------------
# Sweep aggregation
# ------------------------------------------------------------------

def _row(agent, reward, tokens=1000, **kw):
    base = dict(
        task="demo", agent=agent, difficulty="medium", reward=reward,
        public_score=reward, public_passed=1, public_total=1,
        private_score=reward, private_passed=1, private_total=1,
        lint_score=1.0, lint_errors=0, elapsed_sec=10.0,
        tokens_used=tokens, token_budget=250_000, budget_exhausted=False,
        timed_out=False, agent_error=None,
    )
    base.update(kw)
    return base


def test_by_agent_groups_and_averages_per_architecture():
    rows = [
        _row("react", 0.5, tokens=1000),
        _row("react", 0.7, tokens=2000),
        _row("reflexion", 0.9, tokens=9000),
    ]
    by_agent = cli._summarize_by_agent(rows)

    assert by_agent["react"]["n"] == 2
    assert by_agent["react"]["avg_reward"] == 0.6
    assert by_agent["react"]["avg_tokens"] == 1500.0
    assert by_agent["reflexion"]["n"] == 1
    assert by_agent["reflexion"]["avg_tokens"] == 9000.0


def test_by_agent_counts_failure_modes_separately():
    rows = [
        _row("react", 0.0, timed_out=True),
        _row("react", 0.0, agent_error="boom"),
        _row("react", 0.4, budget_exhausted=True),
    ]
    m = cli._summarize_by_agent(rows)["react"]
    assert (m["n_timed_out"], m["n_agent_errors"], m["n_budget_exhausted"]) == (1, 1, 1)


def test_bulk_report_carries_the_comparison_block(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rows = [_row("react", 0.5), _row("reflexion", 0.9)]
    path = write_bulk_report(rows, by_agent=cli._summarize_by_agent(rows))
    doc = json.loads(Path(path).read_text(encoding="utf-8"))

    assert doc["meta"]["agents"] == ["react", "reflexion"]
    assert doc["meta"]["by_agent"]["reflexion"]["avg_reward"] == 0.9
    # results rows stay exactly as handed in — additive only
    assert doc["results"] == rows


# ------------------------------------------------------------------
# Concurrent output capture
# ------------------------------------------------------------------

def test_concurrent_captures_do_not_clobber_each_other():
    """
    Regression: run_task captured stdout with contextlib.redirect_stdout, which
    swaps the *global* sys.stdout. Under --workers > 1 the episodes overwrote
    each other's capture and whole episodes silently vanished from the console
    while still appearing in the report.
    """
    import sys
    from concurrent.futures import ThreadPoolExecutor

    real_stdout = sys.stdout
    proxy = cli._install_stdout_proxy()
    try:
        def work(n):
            with cli._capture() as buf:
                print(f"episode-{n}")
                time.sleep(0.01)          # force the threads to interleave
                print(f"done-{n}")
            return buf.getvalue()

        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(work, range(8)))

        for n, text in enumerate(results):
            assert text == f"episode-{n}\ndone-{n}\n", f"thread {n} captured: {text!r}"
    finally:
        sys.stdout = real_stdout
        cli._proxy = None
        assert proxy is not None


def test_capture_works_without_the_proxy_installed():
    # The single-episode path never installs the proxy.
    assert cli._proxy is None
    with cli._capture() as buf:
        print("solo")
    assert buf.getvalue() == "solo\n"


def test_bulk_report_without_a_sweep_still_works(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = write_bulk_report([_row("react", 0.5)])
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    assert doc["meta"]["by_agent"] == {}
    assert doc["meta"]["avg_reward"] == 0.5
