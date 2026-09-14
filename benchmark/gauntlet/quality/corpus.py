"""Load the Track Q task corpus from suites/quality."""

from __future__ import annotations

import json
from pathlib import Path

from ..enums import Language
from ..paths import SUITES
from .models import QualityTask, RequirementSpec


def load_quality_tasks(name: str = "quality") -> list[QualityTask]:
    suite_dir = SUITES / name
    manifest = json.loads((suite_dir / "manifest.json").read_text())
    data = json.loads((suite_dir / Path(manifest["tasks"])).read_text())
    tasks: list[QualityTask] = []
    for t in data["tasks"]:
        requirements = [
            RequirementSpec(
                id=r["id"], text=r.get("text", r["id"]), kind=r["kind"], category=r["category"],
                good_code=r.get("good_code", ""), bad_code=r.get("bad_code", ""), cwe=r.get("cwe"),
                test=r.get("test", ""), evidence=r.get("evidence", ""),
            )
            for r in t["requirements"]
        ]
        tasks.append(
            QualityTask(
                id=t["id"], title=t["title"], language=Language(t["language"]),
                instruction=t["instruction"], scaffold=t["scaffold"], requirements=requirements,
                files=t.get("files", {}),
            )
        )
    return tasks
