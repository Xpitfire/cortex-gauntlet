"""Track P (Project) — a single open-ended prompt builds a full-repo web app (storefront), executed
in a sandbox and scored on a multi-signal vector (objective + VERTEX similarity + LLM judges).

Costly to run live (especially with Cortex+Synapse), so it defaults to one repetition (seeds=1).
"""

from .corpus import load_project_brief
from .models import Candidate, ProjectBrief, ProjectResult, SignalVector
from .run import DEFAULT_PROJECT_HARNESSES, build_project_record, run_project_suite
from .score import score_project

__all__ = [
    "Candidate",
    "DEFAULT_PROJECT_HARNESSES",
    "ProjectBrief",
    "ProjectResult",
    "SignalVector",
    "build_project_record",
    "load_project_brief",
    "run_project_suite",
    "score_project",
]
