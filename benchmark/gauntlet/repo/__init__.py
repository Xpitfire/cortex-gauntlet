"""Track R (repository issue-resolution): SWE-bench-style fix-the-bug-in-an-existing-repo family.

Complementary to Track Q (single-file from scratch) and Track P (full repo from scratch): here the arm
is handed a small existing repository at a buggy base state plus an issue, and must edit it so a hidden
test that currently fails passes. MVP corpus is stdlib-only and self-contained, so hidden tests run in
the same temp-dir pytest sandbox as Track Q (real SWE-bench repos with dependencies would need the
Docker sandbox of Track P — left as a follow-up).
"""

from .corpus import load_repo_tasks
from .models import RepoResult, RepoTask
from .run import aggregate_repo, run_repo_suite
from .score import score_repo_task

__all__ = ["RepoResult", "RepoTask", "aggregate_repo", "load_repo_tasks", "run_repo_suite",
           "score_repo_task"]
