"""Phase 1 — live code generation: drive a real coding-agent CLI to write code, then analyze it.

The abstraction is harness-agnostic; real adapters drive codex / claude / cortex (+Synapse) /
opencode, and a Fake adapter makes the generate→analyze→score pipeline testable without a live,
authenticated CLI. Used by Track Q (and later Track G) under the `--live` flag; mock stays default.
"""

from .adapters import build_codegen
from .base import CodeGenAdapter, SubprocessCodeGen
from .fake import FakeCodeGen
from .models import CodeGenRequest, CodeGenResult

__all__ = [
    "CodeGenAdapter", "CodeGenRequest", "CodeGenResult", "FakeCodeGen",
    "SubprocessCodeGen", "build_codegen",
]
