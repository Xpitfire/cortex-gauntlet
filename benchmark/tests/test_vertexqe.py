"""VERTEX-QE: estimated references (brief / repo / qe / consensus) for VERTEX, and the validation study.

The default mode is `authored` and must reproduce authored-reference VERTEX exactly; the estimation modes must
estimate non-empty references from public sources and keep the score bounded in [0,1].
"""

import os

from gauntlet.analysis.vertex import vertex_score
from gauntlet.project import vertexqe as Q
from gauntlet.project.corpus import load_project_brief
from gauntlet.project.models import Candidate

_BRIEF = load_project_brief()
_CAND = Candidate(harness_id="t", built=True, served=True,
                  capabilities=["browse a category and filter products", "add an item to the cart"],
                  files={"src/server/api.js": "//", "src/models/cart.js": "//", "tests/cart.test.js": "//",
                         "public/index.html": "<html></html>"})


def _mode(mode: str):
    prev = os.environ.get("GAUNTLET_VERTEX_REF")
    os.environ["GAUNTLET_VERTEX_REF"] = mode
    try:
        return Q.resolve_reference(_BRIEF, _CAND)
    finally:
        os.environ.pop("GAUNTLET_VERTEX_REF", None) if prev is None else os.environ.__setitem__(
            "GAUNTLET_VERTEX_REF", prev)


def test_vertex_ref_auto_resolves_by_execution_mode():
    assert Q.resolve_ref_mode("auto", live=False) == "authored"
    assert Q.resolve_ref_mode("auto", live=True) == "qe"


def test_vertex_ref_env_fallback_is_still_supported(monkeypatch):
    monkeypatch.setenv("GAUNTLET_VERTEX_REF", "repo")
    assert Q.ref_mode() == "repo"


def test_brief_extraction_yields_capability_and_architecture():
    cap, arch = Q.extract_brief_descriptors(_BRIEF)
    assert len(cap) >= 4 and len(arch) >= 4               # the 5 shopper outcomes + 5 engineering bullets
    assert all(isinstance(s, str) and s for s in cap + arch)
    assert "**" not in " ".join(cap + arch)               # markdown stripped


def test_authored_mode_is_unchanged():
    cap_ref, arch_ref, detail = _mode("authored")
    assert cap_ref == _BRIEF.capability_descriptors and arch_ref == _BRIEF.architecture_anchors
    assert detail["ref_mode"] == "authored"


def test_estimation_modes_estimate_nonempty_references_without_the_authored_file():
    for mode in ("brief", "repo", "qe"):
        cap_ref, arch_ref, detail = _mode(mode)
        assert cap_ref and arch_ref, mode
        assert cap_ref != _BRIEF.capability_descriptors    # not the authored ground truth
        v = vertex_score(_CAND.capabilities, cap_ref).vertex
        assert 0.0 <= v <= 1.0


def test_repo_corpus_loads_and_dedups():
    assert len(Q.load_arch_corpus()) >= 4
    pool = Q.repo_arch_reference()
    assert pool and len(pool) == len(set(pool))            # deduped


def test_consensus_is_leave_one_out_and_needs_agreement():
    pools = [["backend API server with routing", "data models for cart and order"],
             ["backend API server with routing", "data models for cart and order"],
             ["a totally unrelated descriptor about gardening"]]
    cons = Q.consensus_descriptors(pools, exclude=2, k=2)  # the two agreeing arms support shared descriptors
    assert cons
    alone = Q.consensus_descriptors(pools, exclude=0, k=2)  # excluding one agreer leaves <k support
    assert len(alone) <= len(cons)


def test_aggregate_confidence_drops_when_sources_disagree():
    _, hi = Q.aggregate_reference([["a", "b", "c"], ["a", "b", "c"]])
    _, lo = Q.aggregate_reference([["a", "b"], ["x", "y"]])
    assert hi > lo


def test_contrastive_calibrates_against_negatives():
    assert Q.contrastive_score(0.8, []) == 0.8                       # no negatives → identity
    high = Q.contrastive_score(0.8, [0.2, 0.1])                      # matches own brief >> others
    low = Q.contrastive_score(0.8, [0.79, 0.81])                     # indistinguishable from others
    assert high > low and 0.0 <= low <= 1.0 and 0.0 <= high <= 1.0


def test_score_pool_returns_a_qe_score_per_arm():
    pool = [_CAND, Candidate(harness_id="u", built=True, served=True,
                             capabilities=["complete checkout and payment"],
                             files={"server/app.ts": "//", "tests/a.test.ts": "//"})]
    rows = Q.score_pool(_BRIEF, pool)
    assert len(rows) == 2 and all(0.0 <= r["vertex_qe"] <= 1.0 for r in rows)
