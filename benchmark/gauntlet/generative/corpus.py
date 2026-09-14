"""Load app briefs from suites/generative."""

from __future__ import annotations

import json
from pathlib import Path

from ..enums import Language
from ..paths import SUITES
from .models import AppBrief, FeatureSpec


def load_briefs(name: str = "generative") -> list[AppBrief]:
    suite_dir = SUITES / name
    manifest = json.loads((suite_dir / "manifest.json").read_text())
    data = json.loads((suite_dir / Path(manifest["briefs"])).read_text())
    briefs: list[AppBrief] = []
    for b in data["briefs"]:
        features = [
            FeatureSpec(id=f["id"], name=f["name"], category=f["category"], e2e=f["e2e"])
            for f in b["features"]
        ]
        briefs.append(
            AppBrief(
                id=b["id"], title=b["title"], language=Language(b["language"]), stack=b["stack"],
                instruction=b["instruction"], features=features,
                architecture=b.get("architecture", ""), acceptance=b.get("acceptance", ""),
                mandated_stack=b.get("mandated_stack"),
            )
        )
    return briefs
