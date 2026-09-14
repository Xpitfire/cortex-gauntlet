"""Build a clean-history, positive-allowlist Gauntlet release directory.

Run from an authorized upstream checkout. The site input must be the reviewed,
screened website candidate; raw result directories are never read or copied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = (
    "benchmark/gauntlet/**/*.py",
    "benchmark/gauntlet/paper_template.tex",
    "benchmark/gauntlet/iclr2027_conference.sty",
    "benchmark/gauntlet/iclr2027_conference.bst",
    "benchmark/gauntlet/tui/app.tcss",
    "benchmark/gauntlet/analysis/rules/security.yaml",
    "benchmark/tests/**/*.py",
    "benchmark/conftest.py",
    "benchmark/.python-version",
    "benchmark/pyproject.toml", "benchmark/uv.lock",
    "benchmark/package.json", "benchmark/package-lock.json", "benchmark/eslint.config.mjs",
    "benchmark/requirements-tui.txt",
    "benchmark/README.md", "benchmark/BENCHMARK.md",
    "benchmark/docs/*.md", "benchmark/docs/proofs.py",
    "benchmark/agent-harness/*.md",
    "benchmark/adapters/README.md", "benchmark/schemas/README.md",
    "benchmark/suites/security/manifest.json", "benchmark/suites/security/SUITE.md",
    "benchmark/suites/security/cases/seeds.json",
    "benchmark/suites/quality/manifest.json", "benchmark/suites/quality/SUITE.md",
    "benchmark/suites/quality/tasks.json",
    "benchmark/suites/generative/manifest.json", "benchmark/suites/generative/SUITE.md",
    "benchmark/suites/generative/briefs.json",
    "benchmark/suites/generative/fixtures/storefront/BRIEF.md",
    "benchmark/suites/generative/fixtures/storefront/acceptance.json",
    "benchmark/suites/generative/fixtures/storefront/catalog.json",
    "benchmark/suites/generative/fixtures/storefront/arch_corpus.json",
    "benchmark/suites/generative/fixtures/todo-app/app.py",
    "benchmark/suites/generative/fixtures/todo-app/e2e.json",
    "benchmark/suites/generative/fixtures/chat-multi/app.py",
    "benchmark/suites/generative/fixtures/chat-multi/e2e.json",
    "benchmark/suites/generative/fixtures/chat-multi/server/*.py",
    "benchmark/suites/generative/fixtures/chat-multi/static/app.js",
    "benchmark/suites/generative/fixtures/chat-multi/static/style.css",
    "benchmark/suites/generative/fixtures/chat-multi/templates/index.html",
    "benchmark/suites/generative/fixtures/chat-multi/tests/test_app.py",
    "benchmark/tools/build_arch_corpus.py", "benchmark/tools/build_og_cover.py",
    "benchmark/tools/public_snapshot.py",
    "benchmark/sandbox/Dockerfile", "benchmark/sandbox/network_guard.py",
    "benchmark/site/results-package.json", "benchmark/site/Dockerfile", "benchmark/site/default.conf",
    "LICENSE",
)
DENIED = {"__pycache__", "node_modules", ".venv", ".lint-tmp", ".gauntlet-decoy", "private", "vendor"}


def build(destination: Path, site: Path) -> dict:
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Snapshot destination must be empty; existing work is never overwritten")
    site = site.resolve()
    manifest = json.loads((site / "paper/manifest.json").read_text())
    for filename, key in (("cortex-gauntlet.pdf", "pdf_sha256"),
                          ("cortex-gauntlet-arxiv.zip", "archive_sha256")):
        if hashlib.sha256((site / "paper" / filename).read_bytes()).hexdigest() != manifest[key]:
            raise ValueError("Paper artifact differs from the screened candidate manifest")
    for pattern in PATTERNS:
        if not any(ROOT.glob(pattern)):
            raise FileNotFoundError(f"Required public source pattern is absent: {pattern}")
    selected = sorted({path for pattern in PATTERNS for path in ROOT.glob(pattern)})
    inventory = {}

    def copy(source: Path, relative: Path, provenance: str, trusted_root: Path) -> None:
        origin = source.relative_to(trusted_root)
        if (not source.resolve().is_relative_to(trusted_root.resolve())
                or any((trusted_root / Path(*origin.parts[:i])).is_symlink()
                       for i in range(1, len(origin.parts) + 1))):
            raise ValueError(f"Source must stay inside its trusted root without symlinks: {relative}")
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"Only regular files are publishable: {relative}")
        if DENIED.intersection(relative.parts) or any(p.startswith(".env") for p in relative.parts):
            raise ValueError(f"Disallowed publication path: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        data = target.read_bytes()
        inventory[relative.as_posix()] = {
            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "provenance": provenance,
        }

    for source in selected:
        provenance = ("unmodified ICLR 2027 style; upstream copyright notices retained"
                      if source.name in {"iclr2027_conference.sty", "iclr2027_conference.bst"}
                      else "upstream Apache-2.0 benchmark source")
        copy(source, source.relative_to(ROOT), provenance, ROOT)
    for name in ("results-package.json", "results-package.csv"):
        copy(site / name, Path("published") / name, "screened public quantitative export", site)
    for name in ("cortex-gauntlet.pdf", "cortex-gauntlet-arxiv.zip", "manifest.json", "submission.txt"):
        copy(site / "paper" / name, Path("published/paper") / name, "canonical paper publication build", site)
    generated = {
        "README.md": (
            "# Cortex Gauntlet\n\n"
            "A standalone snapshot of the five-track coding-agent harness benchmark.\n\n"
            "- [Setup, scope and safety](benchmark/README.md)\n"
            "- [Paper and latest results](https://benchmark.cortex.a2olabs.com)\n"
            "- [Rendered paper PDF](published/paper/cortex-gauntlet.pdf)\n"
            "- [arXiv source archive](published/paper/cortex-gauntlet-arxiv.zip)\n"
            "- [Quantitative results](published/results-package.json)\n\n"
            "This repository has independent history. It does not contain private Cortex/Synapse "
            "implementations, raw captures, private Security holdouts, Cortex production profiles, "
            "compose files, "
            "or screenshot fixtures/media without established redistribution rights. "
            "The screened interactive archive remains on the canonical website.\n\n"
            "Copyright 2026 Alpha Omega Labs. See [LICENSE](LICENSE) and [NOTICE](NOTICE).\n"
        ),
        "NOTICE": (
            "Cortex Gauntlet\nCopyright 2026 Alpha Omega Labs\n\n"
            "Standalone benchmark snapshot from Cortex, licensed under the Apache License, Version 2.0.\n"
            "Cortex control-plane geolocation data and its third-party data notices are outside this snapshot.\n"
            "ICLR 2027 style files are unmodified copies from ICLR/Master-Template revision "
            "46ed6f4c6cef5b175dde23639e77d44c3463b230; their upstream copyright notices are retained.\n"
            "Referenced products, trademarks and external CDN assets remain with their respective owners.\n"
            "No redistribution grant for omitted third-party screenshots or private integrations is asserted.\n"
        ),
        ".gitignore": (
            ".venv/\n__pycache__/\n*.py[cod]\n*.egg-info/\nnode_modules/\n.env*\n"
            ".DS_Store\n.pytest_cache/\n.ruff_cache/\n.mypy_cache/\n.lint-tmp/\n"
            "benchmark/results/\nbenchmark/.gauntlet-decoy/\nbenchmark/site/public/\n"
            "benchmark/suites/security/private/\nbenchmark/suites/security/assets/\n"
            "benchmark/suites/generative/fixtures/storefront/screenshots/\n"
        ),
    }
    for name, content in generated.items():
        (destination / name).write_text(content)
        data = content.encode()
        inventory[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                           "provenance": "standalone release metadata"}
    result = {"repository": "https://github.com/Xpitfire/cortex-gauntlet",
              "source_project": "Cortex / Alpha Omega Labs", "license": "Apache-2.0",
              "paper_date": manifest["publication_date"], "files": inventory}
    (destination / "release-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return {"files": len(inventory) + 1, "bytes": sum(v["bytes"] for v in inventory.values())}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.destination, args.site)))
