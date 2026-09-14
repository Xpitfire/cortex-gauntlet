"""Phase 5 — validate VERTEX-QE against the authored reference (the breakthrough evidence).

On the storefront brief we hold BOTH the hand-authored reference and the pool of harness arms, so we can
ask the only question that matters before trusting the estimator on un-authored briefs: *does VERTEX-QE
rank the arms the same way VERTEX-authored does?* This computes authored VERTEX and every estimated-reference
mode per arm over a finished run's pool and reports Spearman rank correlation. High correlation →
the estimator is validated → the authored reference can be dropped for new briefs.

Run: `python -m gauntlet.project.validate_vertexqe <run_dir>` (a tui-project / project run dir).
Caveat: correlation strength scales with the number of (brief, arm) points — one brief × N arms is
indicative, not conclusive; point it at runs across many briefs to harden the claim.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..analysis.vertex import vertex_score
from . import vertexqe as Q
from .arch import architecture_descriptors
from .corpus import load_project_brief
from .models import Candidate, ProjectBrief
from .sandbox import _capabilities

_BIN = (".png", ".jpg", ".jpeg", ".webp", ".ico", ".gif", ".woff", ".woff2", ".ttf")


def _load_pool(run_dir: Path) -> list[Candidate]:
    """Reconstruct the candidate arms persisted under <run_dir>/sandbox/<harness>/{repo,result.json}."""

    brief = load_project_brief()
    pool: list[Candidate] = []
    for arm in sorted((run_dir / "sandbox").glob("*")):
        repo_dir, res_path = arm / "repo", arm / "result.json"
        if not repo_dir.is_dir() or not res_path.exists():
            continue
        files = {}
        for p in repo_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() not in _BIN:
                try:
                    files[str(p.relative_to(repo_dir))] = p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
        res = json.loads(res_path.read_text())
        pool.append(Candidate(
            harness_id=arm.name, built=True, served=bool(res.get("served")), files=files,
            capabilities=_capabilities(brief.acceptance, res),
            module_descriptors=architecture_descriptors(files)))
    return pool


def _vertex_authored(brief: ProjectBrief, c: Candidate) -> float:
    cap = vertex_score(c.capabilities, brief.capability_descriptors).vertex
    arch = vertex_score(architecture_descriptors(c.files) or c.module_descriptors,
                        brief.architecture_anchors).vertex
    return round(0.7 * cap + 0.3 * arch, 4)


def _vertex_mode(brief: ProjectBrief, c: Candidate, mode: str) -> float:
    from .score import _vertex

    return _vertex(brief, c, mode)[0]


def _spearman(a: list[float], b: list[float]) -> float | None:
    """Spearman rank correlation (Pearson on ranks); None if undefined (n<2 or a constant input)."""

    n = len(a)
    if n < 2:
        return None

    def ranks(xs: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: xs[i])
        r = [0.0] * n
        i = 0
        while i < n:  # average ranks for ties
            j = i
            while j + 1 < n and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    va = sum((x - ma) ** 2 for x in ra) ** 0.5
    vb = sum((y - mb) ** 2 for y in rb) ** 0.5
    return round(cov / (va * vb), 4) if va and vb else None


def validate(run_dir: Path) -> dict:
    brief = load_project_brief()
    pool = _load_pool(run_dir)
    if not pool:
        return {"error": f"no candidate arms under {run_dir}/sandbox"}
    authored = [_vertex_authored(brief, c) for c in pool]
    modes = ["brief", "repo", "qe"]
    per_mode = {m: [_vertex_mode(brief, c, m) for c in pool] for m in modes}
    qe_pool = {r["harness_id"]: r["vertex_qe"] for r in Q.score_pool(brief, pool)}
    consensus = [qe_pool[c.harness_id] for c in pool]
    rows = []
    for i, c in enumerate(pool):
        rows.append({"harness_id": c.harness_id, "authored": authored[i],
                     **{m: per_mode[m][i] for m in modes}, "consensus": consensus[i]})
    correlations = {m: _spearman(authored, per_mode[m]) for m in modes}
    correlations["consensus"] = _spearman(authored, consensus)
    return {"n_arms": len(pool), "per_arm": rows, "spearman_vs_authored": correlations}


def accumulate(results_root: Path) -> dict:
    """Pool the persisted (authored, qe) pairs from EVERY project runrecord under `results_root` and
    compute the overall rank-correlation. This is how the validation hardens: one brief × N arms is
    indicative, but pooling pairs across many runs/briefs converges to a conclusive Spearman."""

    pairs: list[dict] = []
    runs = 0
    for rr in sorted(results_root.rglob("runrecord.json")):
        try:
            rec = json.loads(rr.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        block = (rec.get("aggregates") or {}).get("vertex_qe") or {}
        if block.get("pairs"):
            pairs.extend(block["pairs"])
            runs += 1
    auth = [p["authored"] for p in pairs]
    qe = [p["qe"] for p in pairs]
    return {"runs_pooled": runs, "n_pairs": len(pairs),
            "spearman_vs_authored": _spearman(auth, qe)}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m gauntlet.project.validate_vertexqe <run_dir> | --accumulate <results_root>",
              file=sys.stderr)
        return 2
    if sys.argv[1] == "--accumulate":
        out = accumulate(Path(sys.argv[2] if len(sys.argv) > 2 else "results"))
    else:
        out = validate(Path(sys.argv[1]))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
