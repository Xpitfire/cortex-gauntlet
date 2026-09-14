"""Test config: force the deterministic VERTEX embedding fallback so tests are fast + reproducible
regardless of whether sentence-transformers is installed locally."""

import os

os.environ.setdefault("GAUNTLET_VERTEX_MODEL", "none")
