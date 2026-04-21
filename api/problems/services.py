from pathlib import Path
import yaml

TASKS_DIR = Path(__file__).parent.parent.parent / "tasks"


def _load_problem(problem_id: int, task_dir: Path) -> dict:
    yaml_path = task_dir / "task.yaml"
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    name = task_dir.name
    instruction = data.get("instruction", "")
    short_description = instruction.strip().splitlines()[0][:120] if instruction else ""

    return {
        "id": problem_id,
        "name": name,
        "display_name": name.replace("-", " ").title(),
        "difficulty": data.get("difficulty", "unknown"),
        "language": data.get("language", "python"),
        "short_description": short_description,
        "instruction": instruction,
        "timeout_sec": data.get("timeout_sec", 60),
    }


def get_all_problems() -> list[dict]:
    task_dirs = sorted(
        p for p in TASKS_DIR.iterdir()
        if p.is_dir() and (p / "task.yaml").exists()
    )
    return [_load_problem(i + 1, d) for i, d in enumerate(task_dirs)]


def get_problem_by_id(problem_id: int) -> dict | None:
    problems = get_all_problems()
    for p in problems:
        if p["id"] == problem_id:
            return p
    return None
