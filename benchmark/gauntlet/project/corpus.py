"""Load the Track P storefront brief (open prompt + hidden acceptance + seed catalog + screenshots)."""

from __future__ import annotations

import json

from ..paths import SUITES
from .models import ProjectBrief

_FIXTURE = SUITES / "generative" / "fixtures" / "storefront"


def load_project_brief() -> ProjectBrief:
    """Read BRIEF.md, acceptance.json, catalog.json and enumerate the reference screenshots."""

    acceptance = json.loads((_FIXTURE / "acceptance.json").read_text())
    catalog = json.loads((_FIXTURE / "catalog.json").read_text())
    prompt = (_FIXTURE / "BRIEF.md").read_text()
    shots = sorted(str(p.relative_to(_FIXTURE)) for p in (_FIXTURE / "screenshots").glob("*.png"))
    return ProjectBrief(
        id="storefront", title="Fashion storefront (Atelier)", prompt=prompt,
        acceptance=acceptance, screenshots=shots, catalog=catalog,
    )


def fixture_dir():
    return _FIXTURE


def copy_reference_screenshots(out_dir) -> None:
    """Copy the reference frames next to a report so its `screenshots/*.png` resolve when opened.

    Idempotent; a no-op if the fixture has no screenshots. Used by every path that writes a Track P
    report (CLI run, TUI run) so a generated report never shows broken images.
    """

    import shutil
    from pathlib import Path

    src = _FIXTURE / "screenshots"
    if not src.is_dir():
        return
    dst = Path(out_dir) / "screenshots"
    dst.mkdir(parents=True, exist_ok=True)
    for png in src.glob("*.png"):
        shutil.copy(png, dst / png.name)
