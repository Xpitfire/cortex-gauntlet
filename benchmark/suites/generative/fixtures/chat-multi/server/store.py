"""In-memory multi-turn conversation store: an ordered list of {"role", "content"} messages."""

from __future__ import annotations


class ConversationStore:
    def __init__(self) -> None:
        self._messages: list[dict[str, str]] = []

    def add(self, role: str, content: str) -> None:
        self._messages.append({"role": role, "content": content})

    def history(self) -> list[dict[str, str]]:
        return list(self._messages)
