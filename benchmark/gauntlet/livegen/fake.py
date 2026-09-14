"""Deterministic offline code generator — stands in for a live CLI so the pipeline is testable."""

from __future__ import annotations

from ..models import HarnessMeta
from .models import CodeGenRequest, CodeGenResult


class FakeCodeGen:
    def __init__(self, meta: HarnessMeta, code: str) -> None:
        self.meta = meta
        self._code = code

    def generate(self, request: CodeGenRequest) -> CodeGenResult:
        return CodeGenResult(
            backend=self.meta.id, main_code=self._code,
            files={request.main_file: self._code}, ok=bool(self._code.strip()),
        )
