import sys
from pathlib import Path

# Let a plain `pytest` import the `src` package from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
