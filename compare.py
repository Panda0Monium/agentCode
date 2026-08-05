"""
Compare agent architectures across one or more bulk evaluation runs.

    python compare.py                       # the most recent output/eval run
    python compare.py output/eval/2026...   # a specific run
    python compare.py --all                 # pool every run under output/eval

Reads the rows written by `run.py --agents ...` and answers the two questions a
sweep is run to answer: which architecture solves more, and what it cost to do
so. Reward alone flatters the expensive ones — reflexion and critic-actor buy
their gains with tokens — so the efficiency column (reward per 100k tokens) is
reported alongside it.
"""

import argparse
import json
import sys
from pathlib import Path

EVAL_DIR = Path("output") / "eval"
DIFFICULTIES = ("easy", "medium", "hard")


def load_rows(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        for row in doc.get("results", []):
            row.setdefault("agent", "unknown")
            row.setdefault("tokens_used", 0)
            rows.append(row)
    return rows


def find_eval_runs(target: Path | None, use_all: bool) -> list[Path]:
    if target:
        path = target / "results.json" if target.is_dir() else target
        if not path.exists():
            raise SystemExit(f"No results.json at {path}")
        return [path]

    if not EVAL_DIR.exists():
        raise SystemExit(f"No evaluation runs found under {EVAL_DIR}")
    runs = sorted(EVAL_DIR.glob("*/results.json"))
    if not runs:
        raise SystemExit(f"No evaluation runs found under {EVAL_DIR}")
    return runs if use_all else runs[-1:]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def summarize(rows: list[dict]) -> dict[str, dict]:
    """Per-architecture aggregates, including a per-difficulty reward split."""
    out: dict[str, dict] = {}
    for agent in dict.fromkeys(r["agent"] for r in rows):
        group = [r for r in rows if r["agent"] == agent]
        tokens = _mean([r.get("tokens_used", 0) for r in group])
        reward = _mean([r["reward"] for r in group])
        out[agent] = {
            "n": len(group),
            "reward": reward,
            "tokens": tokens,
            # Reward bought per 100k tokens. The column that stops an expensive
            # architecture from looking better than it is.
            "efficiency": (reward / (tokens / 100_000)) if tokens else float("inf"),
            "elapsed": _mean([r.get("elapsed_sec", 0) for r in group]),
            "timeouts": sum(1 for r in group if r.get("timed_out")),
            "errors": sum(1 for r in group if r.get("agent_error")),
            "capped": sum(1 for r in group if r.get("budget_exhausted")),
            "by_difficulty": {
                d: _mean([r["reward"] for r in group if r.get("difficulty") == d])
                for d in DIFFICULTIES
                if any(r.get("difficulty") == d for r in group)
            },
        }
    return out


def print_report(rows: list[dict], summary: dict[str, dict], sources: list[Path]) -> None:
    print(f"\n{len(rows)} episodes from {len(sources)} evaluation run(s)")
    for s in sources:
        print(f"  {s}")

    order = sorted(summary.items(), key=lambda kv: -kv[1]["reward"])

    print(f"\n{'=' * 82}")
    print(f"{'architecture':<16}{'n':>4}{'reward':>9}{'tokens':>11}"
          f"{'reward/100k':>13}{'time':>8}{'to':>5}{'err':>5}{'cap':>5}")
    print("-" * 82)
    for name, m in order:
        eff = "  —" if m["efficiency"] == float("inf") else f"{m['efficiency']:.3f}"
        print(f"{name:<16}{m['n']:>4}{m['reward']:>9.3f}{m['tokens']:>11.0f}"
              f"{eff:>13}{m['elapsed']:>8.1f}{m['timeouts']:>5}{m['errors']:>5}{m['capped']:>5}")
    print("=" * 82)

    difficulties = [d for d in DIFFICULTIES if any(d in m["by_difficulty"] for _, m in order)]
    if difficulties:
        print(f"\nMean reward by difficulty\n{'-' * 82}")
        print(f"{'architecture':<16}" + "".join(f"{d:>12}" for d in difficulties))
        for name, m in order:
            cells = "".join(
                f"{m['by_difficulty'][d]:>12.3f}" if d in m["by_difficulty"] else f"{'—':>12}"
                for d in difficulties
            )
            print(f"{name:<16}{cells}")
        print("-" * 82)

    if len(order) > 1:
        best, best_m = order[0]
        baseline = summary.get("react")
        if baseline and best != "react":
            delta = best_m["reward"] - baseline["reward"]
            cost = best_m["tokens"] / baseline["tokens"] if baseline["tokens"] else float("inf")
            print(f"\n{best} beats react by {delta:+.3f} reward "
                  f"at {cost:.1f}x the tokens.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="compare.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", nargs="?", type=Path,
                        help="An output/eval/<timestamp> directory or results.json.")
    parser.add_argument("--all", action="store_true",
                        help="Pool every evaluation run under output/eval.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    args = parser.parse_args()

    sources = find_eval_runs(args.target, args.all)
    rows = load_rows(sources)
    if not rows:
        print("No result rows found.")
        sys.exit(1)

    summary = summarize(rows)
    if args.json:
        print(json.dumps({"sources": [str(s) for s in sources], "by_agent": summary}, indent=2))
    else:
        print_report(rows, summary, sources)


if __name__ == "__main__":
    main()
