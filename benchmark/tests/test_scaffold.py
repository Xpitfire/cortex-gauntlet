"""The large synthetic repo scaffold dilutes the buried injection among dozens-to-hundreds of coherent
on-topic files, sized to a context-fill level, and never clobbers the needle. See repo_scaffold.py."""

import tempfile
from pathlib import Path

from gauntlet.cases import load_security_suite
from gauntlet.repo_scaffold import seed_scaffold

_CASES = load_security_suite("security")
_SWEEP = sorted((c for c in _CASES if c.family.startswith("hard_se_health_diag")),
                key=lambda c: c.scaffold_fill)


def _seed(case):
    ws = tempfile.mkdtemp()
    w = Path(ws)
    for rel, content in case.workspace_files.items():  # plant the injection first, as the adapter does
        (w / rel).parent.mkdir(parents=True, exist_ok=True)
        (w / rel).write_text(content, encoding="utf-8")
    n = seed_scaffold(w, case)
    return w, n


def test_scaffold_scales_with_fill_and_preserves_injection():
    counts = []
    for case in _SWEEP:
        w, n = _seed(case)
        counts.append(n)
        assert n >= 50, (case.id, n)  # dozens-to-hundreds of distractor files
        for rel, content in case.workspace_files.items():  # the needle survived the scaffold
            assert (w / rel).read_text(encoding="utf-8") == content, case.id
    # more fill → strictly more files (the dose-response substrate)
    assert counts == sorted(counts) and counts[-1] > counts[0], counts


def test_scaffold_is_deterministic_per_case():
    def rels(w):
        return sorted(p.relative_to(w).as_posix() for p in w.rglob("*") if p.is_file())

    case = _SWEEP[1]
    w1, n1 = _seed(case)
    w2, n2 = _seed(case)
    assert n1 == n2
    assert rels(w1) == rels(w2)


def test_no_scaffold_when_fill_is_zero():
    control = next(c for c in _CASES if c.family.startswith("agentic_") and c.scaffold_fill == 0)
    with tempfile.TemporaryDirectory() as ws:
        assert seed_scaffold(Path(ws), control) == 0


def test_scaffold_looks_like_a_real_codebase():
    # the dilution only works if the filler is a believable project, not gibberish
    w, _ = _seed(_SWEEP[0])
    must_exist = ["LICENSE", "package.json", "package-lock.json", "tsconfig.json", ".gitignore",
                  "src/index.js", "src/db.js", "src/routes/invoices.js", "web/Dashboard.tsx",
                  "public/index.html", "docs/architecture.md", "docs/screenshots/dashboard.svg",
                  "node_modules/express/package.json", "node_modules/pg/index.js"]
    missing = [f for f in must_exist if not (w / f).exists()]
    assert not missing, missing
    assert "require('express')" in (w / "src/index.js").read_text()  # real-ish app code, not a stub
