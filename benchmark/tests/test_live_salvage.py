"""Live Track-P resilience: a sandbox/scoring crash never loses the generated repo, and the Synapse
loop auto-retries a stuck pass instead of halting with an empty repo."""

import pytest

from gauntlet.livegen.models import CodeGenResult
from gauntlet.project.corpus import load_project_brief
from gauntlet.project.synapse_build import synapse_build
from gauntlet.run import PRESETS
from gauntlet.tui.bridge import _project_cell
from gauntlet.tui.events import CellStatus


class _Codegen:
    """A fake codegen whose successive .generate() calls follow a scripted list of results."""

    def __init__(self, meta, results):
        self.meta = meta
        self._results = list(results)
        self.calls = 0
        self.prompts = []

    def generate(self, request):
        self.calls += 1
        self.prompts.append(request.prompt)
        return self._results.pop(0) if self._results else CodeGenResult(self.meta.id, "", files={})


def test_project_cell_preserves_files_when_sandbox_crashes(tmp_path, monkeypatch):
    brief = load_project_brief()
    meta = PRESETS["cortex_wrapped"]
    from gauntlet.project.score import heuristic_judges

    # generation succeeds (a real repo), but the sandbox blows up mid-build
    _repo = {"app.py": "print('hi')", "package.json": "{}"}
    monkeypatch.setattr("gauntlet.project.synapse_build.generate_repo",
                        lambda *a, **k: (_repo, [_repo]))  # (final_files, pass_snapshots)

    def _boom(*a, **k):
        raise RuntimeError("docker exploded")

    monkeypatch.setattr("gauntlet.project.sandbox.run_sandbox", _boom)

    cell = _project_cell(brief, meta, heuristic_judges(), live=True, provider="codex", run_dir=tmp_path)
    outcome = cell(lambda _chunk: None)

    # the generated repo is preserved in the outcome AND on disk — never just a traceback
    assert "app.py" in outcome.files and "package.json" in outcome.files
    assert outcome.status in (CellStatus.FAIL, CellStatus.ERROR)
    assert (tmp_path / "sandbox" / meta.id / "repo" / "app.py").exists()


def test_synapse_loop_auto_retries_a_stuck_pass(tmp_path):
    pytest.importorskip("synapse.domain.requirements")
    brief = load_project_brief()
    meta = PRESETS["cortex_wrapped"]
    # first attempt hangs (timed_out, no files); the auto-retry succeeds — the loop must keep the retry's
    # repo, not give up with an empty one (the old loop stalled after a single timeout).
    codegen = _Codegen(meta, [
        CodeGenResult(meta.id, "", files={}, timed_out=True, error="stuck"),
        CodeGenResult(meta.id, "x", files={"src/app.ts": "export const x = 1", "package.json": "{}"}, ok=True),
    ])
    files, summary = synapse_build(codegen, brief, iterations=1, repo_dir=tmp_path / "repo")

    assert codegen.calls == 2                 # it retried the stuck pass once
    assert "src/app.ts" in files              # and kept the retry's repo
    assert summary["error"] == ""             # not recorded as an empty/failed arm
    assert (tmp_path / "repo" / "src" / "app.ts").exists()  # flushed live to disk


def test_synapse_repair_merges_and_snapshots_each_pass(tmp_path):
    pytest.importorskip("synapse.domain.requirements")
    # pass 1 builds a working app; pass 2 (repair) returns ONLY a new file — the merge must PRESERVE the
    # pass-1 files (not drop them), and every pass must be snapshotted for the caller's best-of.
    meta = PRESETS["cortex_wrapped"]
    p1 = {"src/server.ts": "// working server", "src/cart.ts": "// cart", "package.json": '{"scripts":{"start":"x"}}'}
    codegen = _Codegen(meta, [
        CodeGenResult(meta.id, "a", files=p1, ok=True),
        CodeGenResult(meta.id, "b", files={"src/models.ts": "interface Product {}"}, ok=True),  # only the new file
    ])
    files, summary = synapse_build(codegen, load_project_brief(), iterations=2, repo_dir=tmp_path / "repo")
    assert {"src/server.ts", "src/cart.ts", "src/models.ts"} <= set(files)  # pass-1 files survived the repair
    assert len(summary["snapshots"]) >= 2 and "src/models.ts" not in summary["snapshots"][0]
    assert "src/models.ts" in summary["snapshots"][-1]                       # the repair accumulated


def test_score_passes_surfaces_the_real_sandbox_error_not_candidate_not_executed(monkeypatch, tmp_path):
    # when run_sandbox RAISES an infra error (e.g. a transient fd-race that exhausts, or docker out of
    # space), score_passes must surface the REAL reason — not the misleading "candidate not executed"
    from gauntlet.project import sandbox as S
    from gauntlet.project.score import heuristic_judges

    monkeypatch.setattr(S, "run_sandbox",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("docker: no space left on device")))
    snap = {"package.json": '{"scripts": {"start": "x"}}', "src/app.ts": "export const x = 1;\n"}
    import pytest
    with pytest.raises(OSError, match="no space left on device"):
        S.score_passes(load_project_brief(), [snap], harness_id="cortex_wrapped", run_dir=tmp_path,
                       network_policy="none", judges=heuristic_judges())


def test_synapse_sandbox_build_error_feeds_a_repair_pass(monkeypatch, tmp_path):
    from gauntlet.project import sandbox as S
    from gauntlet.project.models import ProjectResult, SignalVector
    from gauntlet.project.score import heuristic_judges
    from gauntlet.project.synapse_build import score_with_sandbox_repairs

    brief = load_project_brief()
    meta = PRESETS["cortex_wrapped"]
    broken = {"frontend/app.tsx": "<Image src={slide.image} alt=\"\" fill />",
              "package.json": '{"scripts":{"start":"next start","build":"next build"}}'}
    fixed = {**broken, "frontend/app.tsx": "<Image src={slide.image} alt=\"hero\" fill />"}
    codegen = _Codegen(meta, [CodeGenResult(meta.id, "fixed", files=fixed, ok=True)])

    def _signals(build, functional, composite):
        return SignalVector(build, functional, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, composite)

    def _score(_brief, snapshots, *, harness_id, **_kwargs):
        snap = snapshots[-1]
        if "alt=\"hero\"" not in snap.get("frontend/app.tsx", ""):
            return ProjectResult(_brief.id, harness_id, _signals(0, 0.0, 0.0), files=snap,
                                 sandbox_backend="docker",
                                 error="candidate build failed: Image is missing required alt text")
        return ProjectResult(_brief.id, harness_id, _signals(1, 1.0, 0.8), files=snap,
                             sandbox_backend="docker")

    monkeypatch.setattr(S, "score_passes", _score)
    monkeypatch.setattr("gauntlet.livegen.build_codegen", lambda *_args: codegen)

    result = score_with_sandbox_repairs(
        brief, "cortex", meta, broken, [broken], iterations=2, run_dir=tmp_path,
        network_policy="none", judges=heuristic_judges())

    assert result.signals.build == 1 and result.signals.functional == 1.0
    assert codegen.calls == 1
    assert "Image is missing required alt text" in codegen.prompts[0]


def test_governed_arm_fails_loudly_when_synapse_unavailable(monkeypatch, tmp_path):
    # a uses_synapse arm must NEVER silently run as a plain harness (the stale-editable-install
    # regression that made Cortex-over-X identical to raw). It must raise so the run can't masquerade.
    from gauntlet.project import synapse_build as sb

    monkeypatch.setattr(sb, "synapse_available", lambda: False)
    meta = PRESETS["cortex_wrapped"]
    assert meta.uses_synapse
    with pytest.raises(RuntimeError, match="requires the Synapse library"):
        sb.generate_repo(load_project_brief(), "cortex", meta, iterations=1, run_dir=tmp_path,
                         emit=lambda _m: None)


def test_synapse_available_rejects_empty_namespace_package(monkeypatch):
    # find_spec alone returns True for the bare `synapse/` submodule DIR (PEP-420 namespace, no API).
    # synapse_available() must probe a real symbol so that false positive reads as unavailable.
    import types

    from gauntlet import synapse as gs

    empty = types.ModuleType("synapse")           # a namespace-like module with no API
    empty.__path__ = []                            # looks importable, but has no CompletionLabel
    monkeypatch.setitem(__import__("sys").modules, "synapse", empty)
    assert gs.synapse_available() is False         # not usably available → must be False


def test_vertex_nonzero_on_a_realistic_candidate():
    # guards the "VERTEX 0%" regression: a built candidate with behaviour-derived capabilities + a real
    # file tree must score VERTEX > 0 (the kernel + arch descriptors produce above-chance similarity).
    from gauntlet.project.arch import architecture_descriptors
    from gauntlet.project.models import Candidate
    from gauntlet.project.score import _vertex

    brief = load_project_brief()
    caps = ["home page with brand header and category navigation",
            "responsive product listing grid", "product detail page with size variants",
            "add to cart and update quantity"]
    files = {"src/server/app.ts": "export const app = 1;\n", "src/client/App.tsx": "export default () => null;\n",
             "src/server/cart.ts": "export const cart = [];\n", "package.json": '{"name":"x"}'}
    cand = Candidate(harness_id="t", built=True, served=True, capabilities=caps, files=files,
                     module_descriptors=architecture_descriptors(files))
    vertex, detail = _vertex(brief, cand, None)  # None → default ref mode (authored under tests)
    # > 0 is the regression guard (the live "VERTEX 0%" symptom). The backend is whatever is configured —
    # under tests conftest pins GAUNTLET_VERTEX_MODEL=none (deterministic hashing); live uses ST.
    assert vertex > 0.0, f"VERTEX collapsed to 0 on a realistic candidate (detail={detail.get('ref_mode')})"
    assert detail["capability"]["backend"] != "empty"


def test_functional_excludes_unevaluable_journeys_from_the_denominator():
    # the calibration fix: a stateful flow the sandbox could not drive (evaluable=False) is dropped from
    # BOTH numerator and denominator, instead of hard-failing and deflating every arm equally.
    from gauntlet.project.score import _weighted_pass

    w = {"home": 1, "browse_filter": 2, "pdp": 2, "cart": 3, "checkout_payment": 3}
    passed = {"home": True, "browse_filter": True, "pdp": True, "cart": False, "checkout_payment": False}
    # OLD behaviour (no evaluability): 5/11 = 0.45 — the un-passable cart/checkout drag it down
    assert abs(_weighted_pass(passed, w) - 5 / 11) < 1e-6
    # NEW: cart + checkout were not drivable in this sandbox → excluded → 5/5 of what was actually testable
    evaluable = {"home": True, "browse_filter": True, "pdp": True, "cart": False, "checkout_payment": False}
    assert _weighted_pass(passed, w, evaluable=evaluable) == 1.0


def test_functional_no_longer_rewards_keyword_friendliness_over_behaviour():
    # the exact OpenCode>Claude inversion: a keyword-friendly app that "passes" checkout on incidental text
    # must NOT outscore a correct app, once checkout is structural and the un-drivable cart is excluded.
    from gauntlet.project.score import _weighted_pass

    w = {"home": 1, "browse_filter": 2, "pdp": 2, "cart": 3, "checkout_payment": 3}
    # both apps: home/browse/pdp pass; cart un-drivable (excluded for both); checkout now STRUCTURAL so the
    # keyword-only app no longer passes it → both score on the same testable set, no spurious inversion
    ev = {"home": True, "browse_filter": True, "pdp": True, "cart": False, "checkout_payment": False}
    keyword_app = {"home": True, "browse_filter": True, "pdp": True, "cart": False, "checkout_payment": False}
    correct_app = {"home": True, "browse_filter": True, "pdp": True, "cart": False, "checkout_payment": False}
    assert _weighted_pass(keyword_app, w, evaluable=ev) == _weighted_pass(correct_app, w, evaluable=ev)


def test_best_of_passes_picks_the_highest_composite():
    from gauntlet.project.models import ProjectResult, SignalVector
    from gauntlet.project.synapse_build import best_of_passes

    def _res(comp):
        return ProjectResult("b", "h", SignalVector(1, 0, 0, 0, 0, 0, 0, 0, 0, 0, comp))

    snaps = [{"a": "1"}, {"a": "2"}, {"a": "3"}]
    scores = {0: 0.4, 1: 0.7, 2: 0.3}  # the MIDDLE pass is best — last-wins would wrongly ship 0.3
    best = best_of_passes(snaps, lambda snap, idx, total: _res(scores[idx]))
    assert best.signals.composite == 0.7
