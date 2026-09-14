"""End-to-end: the Cortex project-template + the real Synapse Orchestrator loop, as a DRY RUN.

Bootstraps the sha256-pinned `project-template.tar.gz` into a temp workspace, then drives the REAL
`synapse.Orchestrator` with a deterministic stub executor — no LLM, no tokens. The executor "delivers"
requirements by copying the template's own service exemplar into a build dir; the observation builder
derives completion from honest, non-hidden signals (required files present + a stubbed `make check`
gate marker), never from any hidden acceptance. Validates the product cycle: template bootstrap →
plan → execute → validate → repair → complete, and that the loop beats a one-shot pass on the same brief.
"""

import hashlib
import json
import tarfile
from pathlib import Path

import pytest

from gauntlet.paths import ROOT

pytest.importorskip("synapse")  # skip cleanly where the Synapse package is not installed

from synapse.application.orchestrator import OrchestrationContext, Orchestrator  # noqa: E402
from synapse.domain.contracts import EvidenceRef, ExecutionObservation  # noqa: E402

_TEMPLATES = ROOT.parent / ".template-cache"
_ARCHIVE = _TEMPLATES / "project-template.tar.gz"
_MANIFEST = _TEMPLATES / "project-template.manifest.json"
_EXEMPLAR = Path(".agents/examples/modules/python/service_template")

# brief → 5 requirements (req-1..req-5); each maps to a build artifact the executor delivers
_INSTRUCTION = ("create the dto; implement the repository; implement the service; "
                "add unit tests; verify make check passes")
_FILE_FOR = {"req-1": "dto.py", "req-2": "repository.py", "req-3": "service.py",
             "req-4": "test_service.py", "req-5": "BUILD_OK"}
_EXEMPLAR_SRC = {"req-1": "dto.py", "req-2": "repository.py", "req-3": "service.py",
                 "req-4": "test_service.py.example"}
_SOURCE_IDS = ("req-1", "req-2", "req-3", "req-4")


def _bootstrap(dest: Path) -> Path:
    """Extract the pinned template archive into `dest` and return the workspace root."""

    if not _ARCHIVE.exists() or not _MANIFEST.exists():
        pytest.skip("project template archive not present")
    ws = dest / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    with tarfile.open(_ARCHIVE) as tar:
        tar.extractall(ws, filter="data")  # filter='data' = safe extraction (no traversal/links)
    return ws


def _deliver(ws: Path, build: Path, rid: str) -> None:
    """Deliver one requirement by copying the template's service exemplar into the build dir."""

    target = build / _FILE_FOR[rid]
    target.parent.mkdir(parents=True, exist_ok=True)
    if rid == "req-5":  # the make-check gate: passes once all source + tests are in place
        if all((build / _FILE_FOR[r]).exists() for r in _SOURCE_IDS):
            target.write_text("make check: ok\n")
        return
    target.write_text((ws / _EXEMPLAR / _EXEMPLAR_SRC[rid]).read_text())  # copy from the template


def _observe(build: Path) -> ExecutionObservation:
    """Honest observation: a requirement is complete iff its build artifact now exists on disk."""

    completed = [rid for rid, rel in _FILE_FOR.items() if (build / rel).exists()]
    return ExecutionObservation(
        completed_requirement_ids=set(completed),
        satisfied_expectation_ids={f"exp-{rid}" for rid in completed},
        evidence=[EvidenceRef(id=f"ev-{rid}", kind="file", locator=f"req:{rid}",
                              summary=_FILE_FOR[rid]) for rid in completed],
    )


def test_bootstrap_pins_and_exposes_template_gates(tmp_path: Path) -> None:
    """The archive sha256 matches the manifest and the template ships its engineering gates."""

    manifest = json.loads(_MANIFEST.read_text()) if _MANIFEST.exists() else pytest.skip("no manifest")
    digest = hashlib.sha256(_ARCHIVE.read_bytes()).hexdigest()
    assert digest == manifest["archive_sha256"]  # pinned: the bootstrap input cannot drift unnoticed

    ws = _bootstrap(tmp_path)
    assert (ws / "Makefile").exists()  # `make check` quality gate
    assert (ws / ".agents" / "instructions").is_dir()  # engineering ground-truth
    assert (ws / _EXEMPLAR / "dto.py").exists()  # the dto/repository/service encapsulation exemplar
    assert (ws / _EXEMPLAR / "service.py").exists()


def test_template_plus_loop_completes_where_one_shot_stalls(tmp_path: Path) -> None:
    """Real Orchestrator on the bootstrapped template: the loop repairs the tail a one-shot pass drops."""

    ws = _bootstrap(tmp_path)
    cortex_build = ws / "build-cortex"
    raw_build = ws / "build-raw"

    def looped(context: OrchestrationContext) -> ExecutionObservation:
        for rid in context.open_requirement_ids():  # deliver the first still-open requirement per pass
            if not (cortex_build / _FILE_FOR[rid]).exists():
                _deliver(ws, cortex_build, rid)
                break
        return _observe(cortex_build)

    def one_shot(_context: OrchestrationContext) -> ExecutionObservation:
        for rid in _SOURCE_IDS[:2]:  # delivers only the head once, never repairs the tail
            _deliver(ws, raw_build, rid)
        return _observe(raw_build)

    cortex = Orchestrator(max_iterations=8).run_from_instruction(_INSTRUCTION, looped)
    raw = Orchestrator(max_iterations=8).run_from_instruction(_INSTRUCTION, one_shot)

    # cortex arm (template + loop) reaches verified completion via repair
    assert cortex.passed
    assert cortex.completed_requirement_ids == {"req-1", "req-2", "req-3", "req-4", "req-5"}
    assert cortex.iterations > 1  # the value is the loop: multiple repair passes, not one shot
    delivered = (cortex_build / "dto.py").read_text()
    assert delivered == (ws / _EXEMPLAR / "dto.py").read_text()  # delivery used the template exemplar

    # raw arm (one-shot, no loop) drops the tail; Synapse surfaces exactly what was skipped
    assert not raw.passed
    assert raw.completed_requirement_ids == {"req-1", "req-2"}
    open_ids = {i.requirement_id for i in raw.verdict.issues if i.requirement_id}
    assert {"req-3", "req-4", "req-5"}.issubset(open_ids)
