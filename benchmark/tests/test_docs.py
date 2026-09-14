"""Execute the selected symbolic identities and finite mathematical examples."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_proofs_script_passes():
    import pytest

    pytest.importorskip("sympy")  # dev-only dependency for the symbolic proof checks
    proofs = ROOT / "docs" / "proofs.py"
    result = subprocess.run([sys.executable, str(proofs)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
