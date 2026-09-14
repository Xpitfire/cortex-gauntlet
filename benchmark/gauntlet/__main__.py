"""Enable `python -m gauntlet` from the benchmark/ directory."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
