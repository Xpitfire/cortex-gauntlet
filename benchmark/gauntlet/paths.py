"""Filesystem anchors for the Gauntlet benchmark package."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # benchmark/
SUITES = ROOT / "suites"
RESULTS = ROOT / "results"


def case_relative_path(name: str) -> Path:
    """Keep case data out of filesystem traversal and Git's trusted administration."""
    path = Path(name)
    if (not path.parts or path.is_absolute() or ".." in path.parts
            or any(part.casefold().rstrip(" .") == ".git"
                   or part.casefold().startswith(".gitconfig") for part in path.parts)):
        raise ValueError("Case paths must be relative and cannot contain Git administrative files")
    return path
