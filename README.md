# AgentCode

A **software engineering benchmark and RL environment** where an AI agent edits code in a sandboxed repository, is evaluated by an automated grader, and receives a dense scalar reward.

![Architecture](docs/architecture.png)

## Overview

agentCode presents a coding agent with a stub implementation and a set of programming tasks. The agent reads, writes, and tests files inside an isolated Docker container. After the agent finishes, a grader injects hidden private tests and computes a final reward based on test scores and code quality.

```
reward = w_public × public_score + w_private × private_score + w_lint × lint_score
```

## Tasks

| Name | Difficulty | Description |
|---|---|---|
| `lru-cache` | Medium | Implement `LRUCache` with O(1) `get`/`put` |
| `lfu-cache` | Hard | Implement `LFUCache` with O(1) `get`/`put`, frequency + LRU tie-break eviction |
| `flask-lru-cache` | Medium | Flask HTTP server exposing an LRU cache over REST |
| `rate-limited-client` | Hard | HTTP client with token-bucket rate limiting and exponential backoff retry |

## Setup

```bash
pip install -r requirements.txt

docker build -f docker/base.Dockerfile -t agentcode-base .
docker build -f docker/flask.Dockerfile -t agentcode-flask .
docker build -f docker/requests.Dockerfile -t agentcode-requests .
docker build -t agentcode-sandbox .
```

## Running an Episode

```bash
# Noop agent (tests infrastructure)
python run.py tasks/default/lru-cache --noop

# LLM agent
export AGENTCODE_API_KEY=...
export AGENTCODE_API_URL=http://localhost:8000/v1
export AGENTCODE_MODEL=...
python run.py tasks/default/lru-cache
```

### Bulk evaluation

```bash
# Run all tasks in a directory (4 workers by default)
python run.py tasks/classeval --all

# Control parallelism
python run.py tasks/classeval --all --workers 8

# Noop pass (infrastructure check, no output written)
python run.py tasks/classeval --all --noop
```

Available tools:

```python
session.read_file(path)           -> str
session.write_file(path, content)
session.list_files(path="")       -> list[str]
session.run_tests(suite="public") -> TestResult   # .score = passed/total
session.run_lint()                -> LintResult   # .score = 1 - 0.05*errors
```

## Outputs

### Single episode

Each episode writes to `output/episodes/{task}_{timestamp}/`:

| File / Directory | Contents |
|---|---|
| `summary.json` | Task metadata, model, reward, per-suite scores, tool counts, timing |
| `tests.json` | Pass/fail result for every public and private test case |
| `trajectory.json` | Full action log — every tool call and LLM invocation in order |
| `code.zip` | Final state of all files written by the agent |
| `diffs.zip` | One diff per `write_file` call, in order |
| `errors/` | One `.txt` per failed test case with the full pytest traceback |

The trajectory records every step the agent took, including the full LLM message history at each turn:

```json
{
  "task": "lfu-cache",
  "timestamp": "2026-03-11T04:21:14",
  "actions": [
    {
      "tool": "llm_invoke",
      "timestamp": 13.295,
      "args": { "messages": ["system", "human"] },
      "result": { "role": "ai", "tool_calls": [{ "name": "write_file", ... }] }
    },
    {
      "tool": "write_file",
      "timestamp": 13.297,
      "args": { "path": "src/lfu_cache.py", "diff": "write_0001_src__lfu_cache.py.diff" }
    },
    { "tool": "run_tests", ... },
    { "tool": "run_lint", ... }
  ]
}
```

### Bulk evaluation

Bulk runs (`--all`) write a single metrics file instead of per-task reports:

`output/eval/<timestamp>/results.json`

```json
{
  "meta": {
    "timestamp": "2026-05-01T12:34:56",
    "n_tasks": 100,
    "avg_reward": 0.4231,
    "avg_public_score": 0.3812,
    "avg_private_score": 0.4105,
    "avg_lint_score": 0.9520,
    "n_timed_out": 2,
    "n_agent_errors": 0
  },
  "results": [
    {
      "task": "classeval-area-calculator",
      "difficulty": "easy",
      "reward": 0.85,
      "public_score": 0.833,
      "public_passed": 5,
      "public_total": 6,
      "private_score": 1.0,
      "private_passed": 1,
      "private_total": 1,
      "lint_score": 1.0,
      "lint_errors": 0,
      "elapsed_sec": 47.3,
      "timed_out": false,
      "agent_error": null
    }
  ]
}
```

Noop runs (`--noop`) produce no output in either mode.

## Frontend (Coming Soon)

![Frontend](docs/Frontend1.png)

![Leaderboard](docs/Leaderboard1.png)