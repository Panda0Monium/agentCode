import sys
from pathlib import Path

# These tests exercise the host-side harness (agents, registry, budget,
# trajectory processing) — not the sandboxed task repos under tasks/*/tests,
# which are run by pytest *inside* a container.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
