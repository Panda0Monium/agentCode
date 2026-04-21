"""
Task: the unit of work given to an agent.

Load from a directory that contains:
    task.yaml
    repo/           <- starting codebase state
    tests/
        public/     <- agent-visible tests
        private/    <- grader-only tests
"""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class GraderWeights:
    public: float = 0.3
    private: float = 0.6
    lint: float = 0.1

    def __post_init__(self):
        total = self.public + self.private + self.lint
        if not abs(total - 1.0) < 1e-6:
            raise ValueError(f"Grader weights must sum to 1.0, got {total}")


@dataclass(frozen=True)
class Task:
    name: str
    instruction: str
    language: str
    difficulty: str          # easy | medium | hard
    timeout_sec: float
    weights: GraderWeights
    repo_path: Path
    tests_path: Path
    docker_image: str = "agentcode-sandbox"

    @classmethod
    def load(cls, task_dir: str | Path) -> "Task":
        task_dir = Path(task_dir)
        with open(task_dir / "task.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        w = data.get("grader_weights", {})
        weights = GraderWeights(
            public=w.get("public", 0.3),
            private=w.get("private", 0.6),
            lint=w.get("lint", 0.1),
        )

        return cls(
            name=data["name"],
            instruction=data["instruction"].strip(),
            language=data["language"],
            difficulty=data["difficulty"],
            timeout_sec=float(data["timeout_sec"]),
            weights=weights,
            repo_path=task_dir / "repo",
            tests_path=task_dir / "tests",
            docker_image=data.get("docker_image", "agentcode-sandbox"),
        )
