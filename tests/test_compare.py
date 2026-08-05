import json

import compare


def _row(agent, reward, tokens=100_000, difficulty="medium", **kw):
    base = dict(task="demo", agent=agent, difficulty=difficulty, reward=reward,
                tokens_used=tokens, elapsed_sec=10.0, timed_out=False,
                agent_error=None, budget_exhausted=False)
    base.update(kw)
    return base


def _write_eval(tmp_path, rows, name="20260101T000000"):
    d = tmp_path / "output" / "eval" / name
    d.mkdir(parents=True)
    path = d / "results.json"
    path.write_text(json.dumps({"meta": {}, "results": rows}), encoding="utf-8")
    return path


def test_summarize_averages_per_architecture():
    rows = [_row("react", 0.4), _row("react", 0.6), _row("reflexion", 0.9)]
    s = compare.summarize(rows)
    assert s["react"]["n"] == 2
    assert s["react"]["reward"] == 0.5
    assert s["reflexion"]["reward"] == 0.9


def test_efficiency_penalises_expensive_architectures():
    # Same reward, ten times the tokens — the efficiency column is what makes
    # that visible, since reward alone would call them equal.
    rows = [_row("cheap", 0.8, tokens=100_000), _row("pricey", 0.8, tokens=1_000_000)]
    s = compare.summarize(rows)
    assert s["cheap"]["efficiency"] == 0.8
    assert s["pricey"]["efficiency"] < s["cheap"]["efficiency"]


def test_zero_token_rows_do_not_divide_by_zero():
    s = compare.summarize([_row("noop", 0.0, tokens=0)])
    assert s["noop"]["efficiency"] == float("inf")


def test_by_difficulty_split():
    rows = [
        _row("react", 0.9, difficulty="easy"),
        _row("react", 0.3, difficulty="hard"),
        _row("react", 0.5, difficulty="hard"),
    ]
    s = compare.summarize(rows)
    assert s["react"]["by_difficulty"]["easy"] == 0.9
    assert s["react"]["by_difficulty"]["hard"] == 0.4


def test_failure_modes_are_counted():
    rows = [
        _row("react", 0.0, timed_out=True),
        _row("react", 0.0, agent_error="boom"),
        _row("react", 0.2, budget_exhausted=True),
    ]
    m = compare.summarize(rows)["react"]
    assert (m["timeouts"], m["errors"], m["capped"]) == (1, 1, 1)


def test_rows_missing_new_fields_still_load(tmp_path, monkeypatch):
    # Bulk reports written before this feature have no agent/tokens columns.
    monkeypatch.chdir(tmp_path)
    path = _write_eval(tmp_path, [{"task": "old", "reward": 0.5}])
    rows = compare.load_rows([path])
    assert rows[0]["agent"] == "unknown"
    assert rows[0]["tokens_used"] == 0


def test_finds_the_most_recent_run_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_eval(tmp_path, [_row("react", 0.1)], name="20260101T000000")
    _write_eval(tmp_path, [_row("react", 0.9)], name="20260202T000000")

    found = compare.find_eval_runs(None, use_all=False)
    assert len(found) == 1
    assert "20260202T000000" in str(found[0])


def test_all_pools_every_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_eval(tmp_path, [_row("react", 0.1)], name="20260101T000000")
    _write_eval(tmp_path, [_row("react", 0.9)], name="20260202T000000")

    rows = compare.load_rows(compare.find_eval_runs(None, use_all=True))
    assert len(rows) == 2
    assert compare.summarize(rows)["react"]["reward"] == 0.5


def test_report_renders_without_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rows = [_row("react", 0.5, difficulty="easy"), _row("reflexion", 0.9, tokens=500_000)]
    path = _write_eval(tmp_path, rows)

    compare.print_report(rows, compare.summarize(rows), [path])
    out = capsys.readouterr().out
    assert "react" in out and "reflexion" in out
    assert "reward/100k" in out
    assert "beats react" in out
