"""Release regressions: private inputs and stale artifacts cannot cross trust boundaries."""
from dataclasses import asdict, replace
from datetime import datetime
import hashlib
import json

import pytest

from gauntlet import docs, paper, report, site
from gauntlet.adapters import subprocess_base
from gauntlet.agentic_corpus import SCENARIOS, load_private_scenarios
from gauntlet.cases import load_security_suite
from gauntlet.errors import EvaluationUnavailable
from tools import public_snapshot


def _paper_assets(directory):
    directory.mkdir(parents=True)
    pdf, archive = b"test PDF artifact", b"test source artifact"
    (directory / paper.PDF_NAME).write_bytes(pdf)
    (directory / paper.SOURCE_NAME).write_bytes(archive)
    manifest = {"source_sha256": paper.source_digest(),
                "template_sha256": paper.template_digest(),
                "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                "archive_sha256": hashlib.sha256(archive).hexdigest()}
    (directory / "manifest.json").write_text(json.dumps(manifest))


@pytest.mark.parametrize("path", [".git", ".git/config", ".gitconfig.absent", "../escape"])
def test_case_files_cannot_control_git_or_escape_workspace(tmp_path, path):
    case = replace(load_security_suite()[0], workspace_files={path: "untrusted case data"})
    with pytest.raises(ValueError):
        subprocess_base._seed_workspace_files(tmp_path, case)
    assert not tuple(tmp_path.iterdir())


def test_preexisting_git_pointer_is_rejected_before_git_setup(tmp_path, monkeypatch):
    (tmp_path / ".git").write_text("gitdir: ../outside-repository\n")
    monkeypatch.setattr(subprocess_base.subprocess, "run", lambda *a, **kw: pytest.fail("Git must not run"))
    with pytest.raises(EvaluationUnavailable):
        subprocess_base._git_init_workspace(tmp_path)


def test_private_family_cannot_escape_asset_directory(tmp_path, monkeypatch):
    private = tmp_path / "private.json"
    private.write_text(json.dumps([asdict(replace(SCENARIOS[0], family="../../escape", held_out=True))]))
    monkeypatch.setenv("GAUNTLET_PRIVATE_SECURITY_SCENARIOS", str(private))
    with pytest.raises(ValueError):
        load_private_scenarios()


def test_lone_agent_instructions_do_not_enable_governed_execution(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text("Ordinary project instructions\n")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(subprocess_base, "_repo_root", lambda: tmp_path)
    with pytest.raises(EvaluationUnavailable):
        subprocess_base._link_governance(workspace, "codex")
    assert not tuple(workspace.iterdir())


def test_paper_downloads_do_not_expire_at_month_boundary(tmp_path, monkeypatch):
    _paper_assets(tmp_path / "paper")

    class Future(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2030, 10, 1, tzinfo=tz)

    monkeypatch.setattr(docs, "datetime", Future)
    assert "paper/cortex-gauntlet.pdf" in docs._paper_downloads(tmp_path / "docs.html")


def test_changed_style_revokes_paper_downloads(tmp_path, monkeypatch):
    style = tmp_path / "conference.sty"
    style.write_bytes(paper.STYLE_FILES[0].read_bytes())
    monkeypatch.setattr(paper, "STYLE_FILES", (style,))
    _paper_assets(tmp_path / "paper")
    style.write_text(style.read_text().replace("9.0 true in", "8.0 true in"))

    with pytest.raises(ValueError, match="stale"):
        docs._paper_downloads(tmp_path / "docs.html")


def test_stale_paper_failure_preserves_published_archive(tmp_path, monkeypatch):
    archive = tmp_path / "site/runs/previous/report.html"
    archive.parent.mkdir(parents=True)
    archive.write_text("previous published report")
    (tmp_path / "package.json").write_text("{}")
    paper_dir = tmp_path / "site/paper"
    paper_dir.mkdir()
    (paper_dir / "manifest.json").write_text('{"source_sha256":"stale"}')
    monkeypatch.setattr(site, "DIST", tmp_path / "site")
    monkeypatch.setattr(site, "RESULTS", tmp_path / "absent-results")
    monkeypatch.setattr(site, "PACKAGE_FILE", tmp_path / "package.json")
    monkeypatch.setattr(site, "build_package", lambda *a: {"collections": []})
    with pytest.raises(ValueError):
        site.build_site()
    assert archive.read_text() == "previous published report"


def test_snapshot_rejects_symlinked_source_directory(tmp_path, monkeypatch):
    root = tmp_path / "source"
    private = root / "private"
    private.mkdir(parents=True)
    (private / "data.json").write_text("private data must not be copied")
    (root / "public").symlink_to(private, target_is_directory=True)
    reviewed_site = tmp_path / "site"
    _paper_assets(reviewed_site / "paper")
    monkeypatch.setattr(public_snapshot, "ROOT", root)
    monkeypatch.setattr(public_snapshot, "PATTERNS", ("public/data.json",))
    destination = tmp_path / "release"
    with pytest.raises(ValueError):
        public_snapshot.build(destination, reviewed_site)
    assert not destination.exists()


@pytest.mark.parametrize("previous", [None, "previous published report"])
def test_restricted_report_rejects_missing_disclosure_anchor(tmp_path, monkeypatch, previous):
    monkeypatch.setattr(
        report, "_TEMPLATE", report._TEMPLATE.replace('<footer id="method"></footer>', "")
    )
    record = {"track": "security", "publication": {"evidence_redacted": True}}
    output = tmp_path / "report.html"
    if previous is not None:
        output.write_text(previous)
    with pytest.raises(ValueError, match="publication footer"):
        report.build_report(record, output)
    if previous is None:
        assert not output.exists()
    else:
        assert output.read_text() == previous
