"""Tests for Track P launch discovery (pure, no container)."""

from gauntlet.project.launch import discover_launch


def test_pnpm_react_vite():
    files = {
        "package.json": '{"scripts": {"build": "vite build", "preview": "vite preview", "dev": "vite"}}',
        "pnpm-lock.yaml": "lockfileVersion: 9",
        "src/main.tsx": "x",
    }
    plan = discover_launch(files)
    assert plan.manager == "pnpm"
    assert plan.install == ["pnpm", "install"]
    assert plan.build == ["pnpm", "run", "build"]
    assert plan.serve == ["pnpm", "run", "preview"]  # preferred over dev for a served build
    assert plan.serveable


def test_npm_start_preferred():
    files = {"package.json": '{"scripts": {"start": "node server.js", "dev": "vite"}}',
             "package-lock.json": "{}"}
    plan = discover_launch(files)
    assert plan.manager == "npm" and plan.serve == ["npm", "run", "start"]


def test_nested_package_json_workdir():
    files = {"web/package.json": '{"scripts": {"preview": "vite preview"}}', "web/pnpm-lock.yaml": ""}
    plan = discover_launch(files)
    assert plan.workdir == "web" and plan.serve == ["pnpm", "run", "preview"]


def test_prefers_runnable_app_manifest_over_scaffold_and_tool_home():
    files = {
        "package.json": '{"scripts": {"format": "prettier --check ."}}',
        "package-lock.json": "{}",
        ".deepsec/package.json": '{"scripts": {"start": "node scanner.js"}}',
        ".gauntlet-raw-home/codex/.tmp/plugins/plugin/package.json": '{"scripts": {"start": "node x.js"}}',
        "frontend/package.json": '{"scripts": {"build": "next build", "start": "next start --port 3000"}}',
        "frontend/package-lock.json": "{}",
    }
    plan = discover_launch(files)
    assert plan.workdir == "frontend"
    assert plan.manager == "npm"
    assert plan.build == ["npm", "run", "build"]
    assert plan.serve == ["npm", "run", "start"]
    assert plan.port == 3000


def test_makefile_fallback():
    files = {"Makefile": "serve:\n\tpython app\n", "src/x.go": "package main"}
    plan = discover_launch(files)
    assert plan.serve == ["make", "serve"]


def test_python_entry_fallback():
    files = {"app.py": "print('hi')", "requirements.txt": "flask"}
    plan = discover_launch(files)
    assert plan.manager == "python"
    assert plan.serve == ["python3", "app.py"]
    assert plan.install == ["pip", "install", "-r", "requirements.txt"]


def test_no_plan():
    plan = discover_launch({"README.md": "# nothing runnable"})
    assert not plan.serveable and plan.manager == "unknown"
