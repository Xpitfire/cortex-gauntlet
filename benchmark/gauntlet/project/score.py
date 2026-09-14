"""Score one built Candidate against the brief → a multi-signal, gated composite (SignalVector).

Objective signals come from the sandbox observation; VERTEX measures capability + architecture
trajectory similarity to the configured reference descriptors; the visual/code/UX judges are supplied
by the caller (real Claude-vision-via-harness when enabled, else a deterministic fallback). A judge
can never lift a build that failed — the composite is gated on `build`; the visual/UX judges are
additionally zeroed when the app did not serve (they read renders), while the static code_arch judge
needs only a built repo with scoreable files (it reads code, not the running app).
"""

from __future__ import annotations

import dataclasses

from ..analysis import _proc, lint_type_metrics, scan_repo, security_score, vertex_score
from ..bootstrap import app_files
from .arch import architecture_descriptors
from .judge import Judges, heuristic_judges
from .models import Candidate, ProjectBrief, ProjectResult, SignalVector
from .vertexqe import resolve_reference

# composite weights (sum to 1.0); tunable via the run config
WEIGHTS = {
    "functional": 0.26, "vertex": 0.14, "pwa_a11y": 0.09, "visual": 0.16,
    "code_arch": 0.12, "robustness": 0.08, "code_health": 0.06, "security": 0.09,
}


def _weighted_pass(passed: dict[str, bool], weights: dict[str, float] | None = None,
                   evaluable: dict[str, bool] | None = None) -> float:
    """Weighted fraction of passed items. Items the sandbox could not evaluate (`evaluable[k] is False`)
    are dropped from BOTH numerator and denominator — a stateful flow no arm could drive must not deflate
    the score, and an unreachable check must not be credited by incidental text. If everything is
    unevaluable, returns 0.0 (nothing was actually verified)."""
    items = {k: v for k, v in passed.items() if evaluable is None or evaluable.get(k, True)}
    if not items:
        return 0.0
    if weights is None:
        return sum(1 for v in items.values() if v) / len(items)
    total = sum(weights.get(k, 1.0) for k in items)
    got = sum(weights.get(k, 1.0) for k, v in items.items() if v)
    return got / total if total else 0.0


def _code_health(files: dict[str, str], n_findings: int | None) -> float:
    """Multi-file health from the shared scan: source present, tests present, no obvious secrets.
    `n_findings=None` means the scan was unavailable → the clean-tree bonus is withheld (not assumed)."""

    src = {p: c for p, c in files.items() if p.endswith((".py", ".ts", ".tsx", ".js", ".jsx"))}
    if not src:
        return 0.0
    has_tests = any("test" in p.lower() or ".test." in p or ".spec." in p for p in files)
    lt = lint_type_metrics(src, "auto")
    lint_type = (0.5 * lt.lint_score + 0.5 * lt.type_score) if lt.ran else 1.0
    secrets = any(tok in c for c in src.values() for tok in ("sk_live_", "AKIA", "-----BEGIN "))
    clean_bonus = 0.2 * (n_findings == 0) if n_findings is not None else 0.0
    score = 0.3 + 0.2 * has_tests + 0.3 * lint_type + clean_bonus - (0.4 if secrets else 0.0)
    return max(0.0, min(1.0, score))


def _resilient(fn, *, signal: str, degraded: list[str]):
    """Run a fork-prone scoring step. On the transient fd-table race, degrade ONLY this signal (record
    it in `degraded`) and return None instead of crashing the whole vector — the independently-computed
    signals must survive. A non-race exception is a real bug and propagates unchanged."""

    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — re-raised below unless it's the transient fd race
        if not _proc.is_fd_race(exc):
            raise
        degraded.append(signal)
        return None


def _vertex(brief: ProjectBrief, cand: Candidate, vertex_ref: str | None) -> tuple[float, dict]:
    # reference provenance is run-configurable: authored descriptors or public-source estimation modes
    # from brief extraction, reference-repo priors, and QE aggregates.
    cap_ref, arch_ref, ref_detail = resolve_reference(brief, cand, vertex_ref)
    cap = vertex_score(cand.capabilities, cap_ref)
    # role-level architecture descriptors derived from the repo match the anchor *sentences* far better
    # than bare directory names; derive at score time so a re-score lifts old candidates too
    arch_desc = architecture_descriptors(cand.files) or cand.module_descriptors
    arch = vertex_score(arch_desc, arch_ref)
    arch_confidence = ref_detail.get("arch_confidence", 1.0)
    capability_weight, architecture_weight = 0.7, 0.3 * arch_confidence
    combined = round(
        (capability_weight * cap.vertex + architecture_weight * arch.vertex)
        / (capability_weight + architecture_weight),
        4,
    )
    detail = {
        "capability": dataclasses.asdict(cap),
        "architecture": dataclasses.asdict(arch),
        "effective_weights": {
            "capability": round(capability_weight / (capability_weight + architecture_weight), 4),
            "architecture": round(architecture_weight / (capability_weight + architecture_weight), 4),
        },
        "backend": cap.backend,
        "arch_descriptors": arch_desc,
        **ref_detail,
    }
    return combined, detail


def _score_candidate(cand: Candidate) -> Candidate:
    """Candidate view used for scoring: full repo execution result, app-only files for static signals."""

    files = app_files(cand.files)
    descriptors = architecture_descriptors(files)
    capabilities = cand.capabilities if files else []
    return dataclasses.replace(cand, files=files, module_descriptors=descriptors,
                               capabilities=capabilities)


def score_project(brief: ProjectBrief, cand: Candidate, judges: Judges | None = None,
                  *, sandbox_backend: str = "mock", vertex_ref: str | None = None) -> ProjectResult:
    """Score `cand`. `sandbox_backend` records HOW it was executed (mock|docker|static-only) — kept
    independent of the judge backend so report provenance reflects reality, not an inference."""

    judges = judges or heuristic_judges()
    degraded: list[str] = []  # signals a transient fd-race made unavailable — excluded from the composite
    score_cand = _score_candidate(cand)
    score_files = score_cand.files
    score_detail = {"score_file_count": len(score_files),
                    "excluded_setup_file_count": max(0, len(cand.files) - len(score_files))}
    # one Semgrep/Bandit pass, shared by code_health + security; a transient scan race degrades only those
    scan = None if not score_files else _resilient(lambda: scan_repo(score_files),
                                                   signal="security", degraded=degraded)
    if not score_files:
        findings, sec_tool, security, n_findings = [], "not run (no scoreable app files)", 0.0, None
    elif scan is None:  # scan unavailable → security unverified (no credit), findings unknown
        findings, sec_tool, security, n_findings = [], "unavailable (transient fd-race)", 0.0, None
    else:
        findings, sec_tool = scan
        security, n_findings = security_score(findings), len(findings)
    code_health = _code_health(score_files, n_findings)
    if not cand.built:  # hard gate: nothing else can rescue a non-building repo
        signals = SignalVector(0, 0.0, 0.0, code_health, 0.0, security, 0.0, 0.0, 0.0, 0.0, 0.0,
                               detail={"reason": "build failed", "security_tool": sec_tool,
                                       "findings": len(findings), "judge_backend": judges.backend,
                                       "degraded": degraded, **score_detail})
        return ProjectResult(brief.id, cand.harness_id, signals, files=cand.files,
                             screenshots=cand.screenshots, sandbox_backend=sandbox_backend,
                             error=cand.error, capabilities=list(score_cand.capabilities),
                             module_descriptors=list(score_cand.module_descriptors))

    journey_w = {j["id"]: j.get("weight", 1) for j in brief.acceptance.get("journeys", [])}
    functional = _weighted_pass(cand.journey_pass, journey_w, evaluable=cand.journey_eval) if score_files else 0.0
    pwa_a11y = _weighted_pass(cand.pwa_a11y) if score_files else 0.0
    robustness = _weighted_pass(cand.robustness) if score_files else 0.0
    vres = _resilient(lambda: _vertex(brief, score_cand, vertex_ref), signal="vertex", degraded=degraded) \
        if score_files else None
    vertex, vertex_detail = vres if vres is not None else (0.0, {"reason": "unavailable (transient fd-race)"})
    if not score_files:
        vertex_detail = {"reason": "no scoreable app files"}

    # visual/ux are gated on serving (a built-but-not-served app gets no aesthetic/UX credit);
    # code_arch is static and needs only scoreable files. The judges FORK
    # under load — the CLIP judge runs torch/st.encode, code_arch runs eslint/tsc — so a transient
    # fd-race degrades only that judge (not the whole vector), exactly like scan_repo/_vertex above.
    gate = cand.served and bool(score_files)
    visual = (_resilient(lambda: judges.visual(brief, score_cand), signal="visual", degraded=degraded)
              if gate else 0.0) or 0.0
    code_arch = (_resilient(lambda: judges.code_arch(brief, score_cand),
                            signal="code_arch", degraded=degraded) if score_files else 0.0) or 0.0
    ux = (_resilient(lambda: judges.ux(brief, score_cand), signal="ux", degraded=degraded)
          if gate else 0.0) or 0.0

    parts = {"functional": functional, "vertex": vertex, "pwa_a11y": pwa_a11y, "visual": visual,
             "code_arch": code_arch, "robustness": robustness, "code_health": code_health,
             "security": security}
    # Missing infrastructure cannot improve the score by removing its weight.
    if degraded:
        from ..errors import EvaluationUnavailable

        raise EvaluationUnavailable("Project signals unavailable: " + ", ".join(degraded))
    composite = round(sum(WEIGHTS[k] * parts[k] for k in WEIGHTS), 4)
    signals = SignalVector(
        build=1, functional=round(functional, 4), pwa_a11y=round(pwa_a11y, 4),
        code_health=round(code_health, 4), robustness=round(robustness, 4), security=round(security, 4),
        vertex=vertex, visual=round(visual, 4), code_arch=round(code_arch, 4), ux=round(ux, 4),
        composite=composite,
        detail={"weights": WEIGHTS, "vertex": vertex_detail, "judge_backend": judges.backend,
                "served": cand.served, "security_tool": sec_tool, "findings": len(findings),
                "degraded": degraded, **score_detail},
    )
    return ProjectResult(brief.id, cand.harness_id, signals, files=cand.files,
                         screenshots=cand.screenshots, sandbox_backend=sandbox_backend,
                         capabilities=list(score_cand.capabilities),
                         module_descriptors=list(score_cand.module_descriptors))
