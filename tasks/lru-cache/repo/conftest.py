import sys
from pathlib import Path

# Make src/ importable from any test subdirectory
sys.path.insert(0, str(Path(__file__).parent / "src"))
