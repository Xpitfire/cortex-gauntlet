"""Build the VERTEX-QE reference-repo architecture prior from real, criteria-selected repositories.

Principle (docs paper section 5.1.1): the architecture reference is the EMPIRICAL DISTRIBUTION
of how high-quality repos in the domain are structured. This script makes that auditable — it clones a
documented set of permissively-licensed, maintained, popular full-stack web repos, runs the SAME
`architecture_descriptors` extractor used on candidates, and writes ONLY the extracted descriptors (no
source) to `arch_corpus.json`. Selection is explicit and committed, so there is no cherry-picking.

Run: `python -m tools.build_arch_corpus` (needs git + network). Without it, the committed seed (canonical
patterns) is used. Add/curate repos in `_REPOS` below; keep the set domain-matched, diverse, and
permissively licensed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gauntlet.project.arch import architecture_descriptors  # noqa: E402

_OUT = (Path(__file__).resolve().parents[1] / "suites" / "generative" / "fixtures"
        / "storefront" / "arch_corpus.json")

# Documented selection: domain-matched (full-stack web storefront / e-commerce), permissive license
# (MIT / BSD-3), actively maintained, widely adopted, and architecturally DIVERSE (modular service,
# SSR framework, layered/hexagonal, Django GraphQL, Rails MVC) so typicality rewards any good style.
# Each entry is auditable; `ref` is optional (omit → the repo's default branch).
_REPOS: list[dict] = [
    {"name": "medusajs/medusa", "style": "modular service commerce (Node/Express)",
     "url": "https://github.com/medusajs/medusa", "license": "MIT"},
    {"name": "vercel/commerce", "style": "SSR storefront + headless provider API (Next.js)",
     "url": "https://github.com/vercel/commerce", "license": "MIT"},
    {"name": "vendure-ecommerce/vendure", "style": "layered / hexagonal GraphQL (NestJS)",
     "url": "https://github.com/vendure-ecommerce/vendure", "license": "MIT"},
    {"name": "saleor/saleor", "style": "layered backend, GraphQL (Python/Django)",
     "url": "https://github.com/saleor/saleor", "license": "BSD-3-Clause"},
    {"name": "spree/spree", "style": "MVC monolith, API-driven (Ruby on Rails)",
     "url": "https://github.com/spree/spree", "license": "BSD-3-Clause"},
]

_TEXT_EXT = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py", ".html", ".css", ".json", ".md")


def _read_tree(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in _TEXT_EXT and ".git" not in p.parts:
            try:
                files[str(p.relative_to(root))] = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
    return files


def main() -> int:
    if not _REPOS:
        print("no repos curated in tools/build_arch_corpus.py::_REPOS — keeping the committed seed.")
        return 0
    repos = []
    for spec in _REPOS:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "repo"
            clone = ["git", "clone", "--depth", "1"]
            if spec.get("ref"):  # else clone the repo's default branch (main/master/develop vary)
                clone += ["--branch", spec["ref"]]
            subprocess.run([*clone, spec["url"], str(dest)], check=True, capture_output=True)
            descriptors = architecture_descriptors(_read_tree(dest))
        repos.append({"name": spec["name"], "style": spec.get("style", ""),
                      "license": spec.get("license", ""), "descriptors": descriptors})
        print(f"  {spec['name']}: {len(descriptors)} descriptors")
    payload = json.loads(_OUT.read_text())
    payload["repos"] = repos
    _OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {len(repos)} repos → {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
