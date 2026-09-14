"""Track G live: a real harness generates an app; the e2e runner measures it (build + browser + REST).

Maps the real e2e result into a GenerativeResult so the existing Track G report renders it.
Mock generation stays the default; this path runs under `--track generative --live`.

EXECUTION SAFETY: generated apps are untrusted and run only in the sealed Docker sandbox. An unavailable
sandbox is benchmark infrastructure failure; there is no host-execution fallback.
"""

from __future__ import annotations

from pathlib import Path

from ..enums import Language
from ..livegen.base import CodeGenAdapter
from ..livegen.models import CodeGenRequest
from ..models import HarnessMeta
from ..synapse import Requirement, RequirementKind, SynapsePlanner
from ..errors import SandboxUnavailable
from .e2e import E2EReport
from .judge import GenerativeJudge
from .models import AppBrief, FeatureOutcome, FeatureSpec, GenerativeResult
from .sandbox import docker_available, run_generative_sandbox

# Reference-FREE CLIP text-image visual judge prompts. There is no single "correct" look for a
# generated app — many valid chat UIs exist — so an image-image judge vs one golden screenshot wrongly
# zeroes a good app that merely looks different (observed: a working codex chat UI scored 0.0). Instead
# we score how much MORE the screenshot looks like the brief's UI than a blank page. The GOOD prompt is
# per-brief (a notes app must not be judged on how much it looks like a CHAT app) — briefs override it
# via "visual_good"; the chat description is the default for the chat briefs.
_VIS_GOOD = "a modern web chat application interface with a conversation of message bubbles and a text input box"
_VIS_NOTES = "a modern web notes application interface with a list of saved notes and an editor form with title and body fields"
_VIS_BAD = "a blank empty web page with a little plain text and no styling"


def visual_score(screenshot: str | None, served: bool, good: str = _VIS_GOOD) -> float | None:
    """Score a served screenshot against the brief; return None when the visual judge is unavailable."""

    if not served:
        return 0.0
    if not screenshot or not Path(screenshot).exists():
        return None
    try:
        import math

        from ..analysis.embedding import cosine, embed_images, embed_texts
        from ..project.judge import DEFAULT_CLIP_MODEL

        iv, _ = embed_images([screenshot], DEFAULT_CLIP_MODEL)
        tv, _ = embed_texts([good, _VIS_BAD], DEFAULT_CLIP_MODEL)
        sg, sb = cosine(iv[0], tv[0]), cosine(iv[0], tv[1])
        return round(1.0 / (1.0 + math.exp(-(sg - sb) / 0.02)), 4)
    except (ImportError, RuntimeError, ValueError, OSError, IndexError):
        return None




def _bundle_sandbox_shot(report: E2EReport, assets_dir: Path, brief_id: str, harness_id: str) -> None:
    """Copy the sandbox's captured screenshot (run_dir/gen-sandbox/<harness>/screenshot.png) into the run's
    web-bundled assets/ and rewrite report.screenshot to the run-relative path, so the report renders it."""

    import shutil

    src = assets_dir.parent / "gen-sandbox" / harness_id / "screenshot.png"
    if not src.exists():
        report.screenshot = None
        return
    dst_name = f"{brief_id}-{harness_id}.png"
    shutil.copy(src, assets_dir / dst_name)
    report.screenshot = f"assets/{dst_name}"


_CHAT_INSTRUCTION = (
    "Build a MULTI-FILE Python web app (Python STANDARD LIBRARY ONLY — no third-party packages, no build "
    "step) — a small, polished ChatGPT-style assistant backed by a LOCAL language model. Use this exact "
    "package layout (create every directory and file):\n"
    "  app.py                  # entry point: read the port from sys.argv[1], bind 127.0.0.1, start the server\n"
    "  server/__init__.py      # package marker (may re-export the handler/store)\n"
    "  server/handlers.py      # http.server BaseHTTPRequestHandler routing /, /static/<file>, /api/chat, /api/history\n"
    "  server/llm.py           # OpenAI-compatible SLM client over urllib (see below)\n"
    "  server/store.py         # in-memory conversation store: a list of {\"role\", \"content\"} dicts; multi-turn\n"
    "  templates/index.html    # the chat shell (see below)\n"
    "  static/style.css        # real CSS — message bubbles + a sticky composer\n"
    "  static/app.js           # vanilla JS — fetch POST /api/chat, append bubbles, load /api/history\n"
    "  tests/test_app.py       # stdlib unittest covering routing/store/llm parsing\n\n"
    "Routes:\n"
    "- GET / : serve templates/index.html. It MUST contain "
    "`<link rel=\"stylesheet\" href=\"/static/style.css\">`, a scrollable transcript "
    "`<div id=\"messages\">` of user/assistant bubbles, a sticky `<form id=\"composer\">` with "
    "`<input id=\"input\">` and a send button, and `<script src=\"/static/app.js\">`.\n"
    "- GET /static/<file> : serve the matching file from static/ with the correct content-type "
    "(text/css for .css, application/javascript for .js).\n"
    "- POST /api/chat with JSON {\"message\": \"...\"} : call the local LLM and return JSON {\"reply\": \"...\"}. "
    "The LLM is an OpenAI-COMPATIBLE server — read its base URL from env LLM_BASE_URL and the model from env "
    "LLM_MODEL, then POST {LLM_BASE_URL}/chat/completions with {\"model\": <LLM_MODEL>, \"messages\": [...]} and "
    "return choices[0].message.content. Keep the in-memory conversation (server/store.py) so multi-turn "
    "context is sent. APPEND the incoming user message to the store BEFORE calling the LLM (so the "
    "history is populated even if the LLM is down), then append the assistant reply. If the LLM call "
    "fails, still return valid JSON with a 'reply' field.\n"
    "- GET /api/history : return the JSON list of {\"role\", \"content\"} messages so far.\n\n"
    "Start with `python app.py <port>` binding 127.0.0.1. Use ONLY the standard library (urllib for the LLM "
    "call). Do NOT call any network endpoint other than LLM_BASE_URL."
)

_CHAT_MANIFEST = {
    "start": ["{python}", "app.py", "{port}"],
    "ready_path": "/",
    "checks": [
        {"id": "chat-ui", "kind": "ui", "path": "/", "selector": "#messages", "text": ""},
        {"id": "composer", "kind": "ui", "path": "/", "selector": "#composer, #input", "text": ""},
        {"id": "stylesheet", "kind": "ui", "path": "/", "selector": "link[rel=stylesheet]", "text": ""},
        {"id": "static-css", "kind": "rest", "method": "GET", "path": "/static/style.css",
         "status": 200, "contains": "{"},
        {"id": "static-js", "kind": "rest", "method": "GET", "path": "/static/app.js",
         "status": 200, "contains": "fetch"},
        {"id": "send-message", "kind": "chat", "path": "/api/chat",
         "message": "Reply with the single word: pong", "expect": "pong", "min_len": 1, "timeout": 90},
        {"id": "history", "kind": "rest", "method": "GET", "path": "/api/history",
         "status": 200, "contains": "role"},
    ],
}

_NOTES_INSTRUCTION = (
    "Build a MULTI-FILE Python web app (Python STANDARD LIBRARY ONLY — no third-party packages, no build "
    "step) — a Markdown notes app that persists notes to a LOCAL JSON file. Use this exact package layout "
    "(create every directory and file):\n"
    "  app.py                  # entry point: read the port from sys.argv[1], bind 127.0.0.1, start the server\n"
    "  server/__init__.py      # package marker (may re-export the handler/store)\n"
    "  server/handlers.py      # http.server BaseHTTPRequestHandler routing /, /static/<file>, /api/notes\n"
    "  server/store.py         # JSON-file persistence: load/save a list of {\"id\", \"title\", \"body\"} notes\n"
    "  templates/index.html    # the notes shell (see below)\n"
    "  static/style.css        # real CSS — a notes list + an editor form\n"
    "  static/app.js           # vanilla JS — fetch POST /api/notes to create, GET /api/notes to list\n"
    "  tests/test_app.py       # stdlib unittest covering routing/store\n\n"
    "Routes:\n"
    "- GET / : serve templates/index.html. It MUST contain "
    "`<link rel=\"stylesheet\" href=\"/static/style.css\">`, a list container `<ul id=\"notes\">`, a "
    "`<form id=\"editor\">` with a title `<input id=\"title\">` and a body `<textarea id=\"body\">`, and "
    "`<script src=\"/static/app.js\">`.\n"
    "- GET /static/<file> : serve the matching file from static/ with the correct content-type.\n"
    "- POST /api/notes with JSON {\"title\": \"...\", \"body\": \"...\"} : create a note, persist it to the "
    "local JSON file, and return status 201 with the created note JSON.\n"
    "- GET /api/notes : return the JSON list of persisted notes.\n\n"
    "Persist to a JSON file in the current working directory (e.g. notes.json) — NOT inside the source tree. "
    "Start with `python app.py <port>` binding 127.0.0.1. Use ONLY the standard library. Do NOT call any "
    "external network endpoint."
)

_NOTES_MANIFEST = {
    "start": ["{python}", "app.py", "{port}"],
    "ready_path": "/",
    "checks": [
        {"id": "shell", "kind": "ui", "path": "/", "selector": "#notes", "text": ""},
        {"id": "editor", "kind": "ui", "path": "/", "selector": "#editor", "text": ""},
        {"id": "static-css", "kind": "rest", "method": "GET", "path": "/static/style.css",
         "status": 200, "contains": "{"},
        {"id": "static-js", "kind": "rest", "method": "GET", "path": "/static/app.js",
         "status": 200, "contains": "fetch"},
        {"id": "create", "kind": "rest", "method": "POST", "path": "/api/notes",
         "body": "{\"title\": \"Groceries\", \"body\": \"milk\"}", "status": 201},
        {"id": "list-persists", "kind": "rest", "method": "GET", "path": "/api/notes",
         "status": 200, "contains": "Groceries"},
    ],
}

# A genuine multi-file TypeScript/Node brief. This is only achievable now that the build runs in the
# Docker sandbox (pnpm/npm install + build); it NEVER runs on the host. The candidate must ship a real
# repo: a package.json with `build` + `start` scripts, a src/ tree of TS modules, an index.html, and a
# server entry. install/build/serve are recovered from package.json by discover_launch. The manifest is
# deliberately MODEST (a strong model can one-shot a minimal building TS app) — a UI shell, a REST health
# endpoint, and a chat round-trip via the stub SLM. NOT all 12 features.
_CHAT_WEB_INSTRUCTION = (
    "Build a MULTI-FILE TypeScript/Node web app — a small ChatGPT-style assistant backed by a LOCAL "
    "OpenAI-compatible language model. It MUST be a genuine compiled project: TypeScript sources under "
    "src/ that are COMPILED by a build step, served by a Node HTTP server. Use this exact layout "
    "(create every directory and file):\n"
    "  package.json            # name, scripts.build = 'tsc', scripts.start = 'node dist/server.js', "
    "type module. Declare `typescript` as the ONLY devDependency (it provides the `tsc` build tool — it "
    "is NOT shipped globally); declare NO other third-party deps and NO runtime dependencies\n"
    "  tsconfig.json           # compilerOptions.outDir = 'dist', rootDir = 'src', module/target es2020+, "
    "include ['src']\n"
    "  src/server.ts           # entry: read the port from process.env.PORT (default 8080), bind "
    "127.0.0.1, route GET / , GET /api/health , POST /api/chat\n"
    "  src/llm.ts              # OpenAI-compatible client over Node's fetch/http: read LLM_BASE_URL and "
    "LLM_MODEL from process.env, POST {LLM_BASE_URL}/chat/completions, return choices[0].message.content\n"
    "  src/store.ts            # in-memory conversation store: an array of {role, content}; multi-turn\n"
    "  public/index.html       # the chat shell (see below)\n\n"
    "Routes:\n"
    "- GET / : serve public/index.html. It MUST contain a root element `<div id=\"app\">` and a "
    "`<form id=\"composer\">` for sending messages.\n"
    "- GET /api/health : return status 200 with JSON {\"status\": \"ok\"}.\n"
    "- POST /api/chat with JSON {\"message\": \"...\"} : call the local LLM (src/llm.ts) and return JSON "
    "{\"reply\": \"...\"}. The LLM is an OpenAI-COMPATIBLE server — read its base URL from env LLM_BASE_URL "
    "and the model from env LLM_MODEL. Keep the in-memory conversation so multi-turn context is sent. If "
    "the LLM call fails, still return valid JSON with a 'reply' field.\n\n"
    "Build with the `build` script (tsc → dist/, resolved from the `typescript` devDependency installed by "
    "`npm install`). Start with the `start` script binding 127.0.0.1 to the PORT env var. At RUNTIME use "
    "ONLY Node built-ins (no runtime third-party deps); the TypeScript compiler is a BUILD-time tool only. "
    "Do NOT call any network endpoint other than LLM_BASE_URL."
)

_CHAT_WEB_MANIFEST = {
    # build/serve are recovered from package.json by discover_launch in the sandbox (NOT declared here);
    # ready_path "/" and these modest checks are achievable for a minimal building TS app.
    "ready_path": "/",
    "checks": [
        {"id": "app-shell", "kind": "ui", "path": "/", "selector": "#app", "text": ""},
        {"id": "composer", "kind": "ui", "path": "/", "selector": "#composer", "text": ""},
        {"id": "health", "kind": "rest", "method": "GET", "path": "/api/health",
         "status": 200, "contains": "ok"},
        {"id": "send-message", "kind": "chat", "path": "/api/chat",
         "message": "Reply with the single word: pong", "expect": "pong", "min_len": 1, "timeout": 90},
    ],
}


# Held-out probe variants the arm never sees: the SAME app exercised with DIFFERENT inputs — a unique
# marker that only survives a REAL round-trip/store. A hardcoded answer to the fixed probe above fails
# these (the anti-overfit axis). Ids are prefixed "ho-" so the scorer splits them from the shown checks.
_CHAT_HELD_OUT = [
    {"id": "ho-store", "kind": "chat", "path": "/api/chat",
     "message": "please remember this marker and echo it back exactly: ZQX-4071",
     "expect": "ZQX-4071", "min_len": 1, "timeout": 90},
    {"id": "ho-history-marker", "kind": "rest", "method": "GET", "path": "/api/history",
     "status": 200, "contains": "ZQX-4071"},  # the user message must be stored in the real history
]
_NOTES_HELD_OUT = [
    {"id": "ho-create", "kind": "rest", "method": "POST", "path": "/api/notes",
     "body": "{\"title\": \"ZQX-note\", \"body\": \"b42\"}", "status": 201},
    {"id": "ho-list", "kind": "rest", "method": "GET", "path": "/api/notes",
     "status": 200, "contains": "ZQX-note"},  # the new note must actually persist + list back
]
_CHAT_WEB_HELD_OUT = [
    {"id": "ho-chat2", "kind": "chat", "path": "/api/chat",
     "message": "second turn: echo marker MRK-88", "expect": "MRK-88", "min_len": 1, "timeout": 90},
    {"id": "ho-health2", "kind": "rest", "method": "GET", "path": "/api/health",
     "status": 200, "contains": "ok"},  # stays up + idempotent under a second round of traffic
]


def live_briefs() -> list[dict]:
    return [
        {
            "id": "chat-app",
            "title": "ChatGPT-style assistant (local SLM)",
            "language": "python",
            "stack": "Python stdlib http.server (multi-file package) + a local OpenAI-compatible SLM",
            "main_file": "app.py",
            "instruction": _CHAT_INSTRUCTION,
            "manifest": _CHAT_MANIFEST,
            "held_out": _CHAT_HELD_OUT,
        },
        {
            "id": "notes-app",
            "title": "Markdown notes (local persistence)",
            "language": "python",
            "stack": "Python stdlib http.server (multi-file package) + local JSON persistence",
            "main_file": "app.py",
            "instruction": _NOTES_INSTRUCTION,
            "manifest": _NOTES_MANIFEST,
            "held_out": _NOTES_HELD_OUT,
            "visual_good": _VIS_NOTES,
        },
        {
            "id": "chat-web",
            "title": "ChatGPT-style assistant (web)",
            "language": "typescript",
            "stack": "Multi-file TypeScript/Node (tsc build) HTTP server + a local OpenAI-compatible SLM",
            "main_file": "src/server.ts",
            "instruction": _CHAT_WEB_INSTRUCTION,
            "manifest": _CHAT_WEB_MANIFEST,
            "held_out": _CHAT_WEB_HELD_OUT,
            # node briefs build via pnpm/npm in the Docker sandbox; they NEVER run install on the host,
            # so they SKIP when Docker is absent (the host fallback is python-only).
            "requires_sandbox": True,
        },
    ]


def to_appbrief(brief: dict) -> AppBrief:
    features = [
        FeatureSpec(id=c["id"], name=c["id"], category=c["kind"], e2e=c.get("path", c["id"]))
        for c in brief["manifest"]["checks"]
    ]
    return AppBrief(
        id=brief["id"], title=brief["title"], language=Language(brief["language"]),
        stack=brief["stack"], instruction=brief["instruction"], features=features,
        architecture="Generated by a real harness; built, served, and verified by Playwright + REST.",
        acceptance="All e2e checks pass against the running app.",
    )


def run_live_brief(
    brief: dict, harness: HarnessMeta, codegen: CodeGenAdapter,
    planner: SynapsePlanner, judge: GenerativeJudge, assets_dir: Path | None = None,
    reporter: object | None = None,
) -> GenerativeResult:
    checks = brief["manifest"]["checks"]
    if not docker_available():
        raise SandboxUnavailable("Docker is unavailable; Track G refuses host execution")
    held = brief.get("held_out", [])
    # held-out variants run in the SAME probe (one served app), then split out by id below
    probe_manifest = {**brief["manifest"], "checks": checks + held}
    requirements = [Requirement(c["id"], c["id"], RequirementKind.DELIVERABLE) for c in checks]
    requirements.append(Requirement("verify", "validate via e2e", RequirementKind.VERIFICATION))
    plan = planner.plan(requirements)

    main_file = brief.get("main_file") or "app.py"
    # live-mirror the growing app to a browsable on-disk dir + narrate via the reporter (inactivity
    # watchdog inside generate keeps a long, healthy build alive while killing a hung one).
    mirror = str(assets_dir.parent / "gen-repo" / harness.id) if assets_dir is not None else None
    result = codegen.generate(
        # capture_repo=True: keep the WHOLE generated tree (server/*, templates/*.html, static/*.css|js,
        # tests/*), not just the *.py glob — the multi-file app's html/css/js feed the e2e + quality signals.
        # Governed arms run INSIDE the Cortex scaffold too (same wrapping as Track P), but governance-only:
        # a generative brief is a stdlib `python app.py`, so the full Node/TS template would hijack the
        # sandbox's launch discovery. The harness adapts the managed scaffold, then builds the app.
        CodeGenRequest(prompt=brief["instruction"], language=brief["language"],
                       main_file=main_file, capture_repo=True, reporter=reporter, mirror_dir=mirror,
                       scaffold=harness.uses_synapse, scaffold_governance_only=True)
    )
    files = result.files or {main_file: result.main_code}
    if reporter is not None:
        reporter.tree(files)
    shot = None
    if assets_dir is not None:
        assets_dir.mkdir(parents=True, exist_ok=True)
        shot = assets_dir / f"{brief['id']}-{harness.id}.png"

    run_dir = assets_dir.parent if assets_dir is not None else None
    report = run_generative_sandbox(probe_manifest, files, harness.id, run_dir=run_dir)
    if report is None:
        raise SandboxUnavailable("generative sandbox is unavailable")
    if report.infrastructure_error:
        raise SandboxUnavailable(report.infrastructure_error)
    if report.screenshot and assets_dir is not None:
        _bundle_sandbox_shot(report, assets_dir, brief["id"], harness.id)

    passed_ids = {c.id for c in report.checks if c.passed}
    passes = [1 if chk["id"] in passed_ids else 0 for chk in checks]      # SHOWN checks only
    completeness = round(sum(passes) / len(checks), 4) if checks else 0.0
    held_ids = [c["id"] for c in held]                                    # held-out anti-overfit variants
    held_passed = sum(1 for cid in held_ids if cid in passed_ids)
    robustness = round(held_passed / len(held_ids), 4) if held_ids else 1.0
    # additive static quality (ruff+mypy) + a security scan of the generated app (same as Track P).
    # Score the HARNESS-authored app only — a governed arm's Cortex scaffold must not lend its own
    # `.agents/` scripts to the harness's lint/security numbers (the scaffold ⊆ the full template paths).
    from ..analysis import lint_type_metrics, scan_repo, security_score
    from ..bootstrap import app_files
    app_only = app_files(files)
    lt = lint_type_metrics(app_only, brief["language"])
    findings, sec_tool = scan_repo(app_only)
    visual = visual_score(
        str(shot) if shot and shot.exists() else None,
        report.served,
        good=brief.get("visual_good", _VIS_GOOD),
    )
    degraded = ["honesty", "trajectory"]
    if visual is None:
        degraded.append("visual")
    return GenerativeResult(
        brief_id=brief["id"], harness_id=harness.id, language=brief["language"], n_seeds=1,
        feature_count=len(checks), build_pass=1 if report.built else 0,
        feature_pass_counts=passes, feature_claim_counts=[0] * len(checks),
        seed_completeness=[completeness], feature_rate=[float(p) for p in passes],
        plan_score=0.0, visual_score=visual or 0.0,
        honesty=0.0, guardrail_score=None,
        milestones=[],  # evaluator decomposition is not an observed agent plan
        rep_features=[FeatureOutcome(c["id"], c["id"], bool(p), False) for c, p in zip(checks, passes)],
        screenshot=report.screenshot, synapse_backend=plan.backend, files=files,
        lint_issues=lt.lint_issues, type_errors=lt.type_errors,
        code_quality=round(0.5 * lt.lint_score + 0.5 * lt.type_score, 4),
        security=round(security_score(findings), 4), findings=len(findings), security_tool=sec_tool,
        robustness=robustness, held_out_passed=held_passed, held_out_total=len(held_ids),
        degraded=degraded,
    )
