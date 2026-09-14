"""Put benchmark/ on sys.path so `import gauntlet` works when running pytest here."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
