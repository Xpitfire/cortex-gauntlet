"""Unit tests (stdlib unittest) for the chat app's store + SLM response parsing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.llm import parse_completion  # noqa: E402
from server.store import ConversationStore  # noqa: E402


class StoreTests(unittest.TestCase):
    def test_multi_turn_history_is_ordered(self) -> None:
        store = ConversationStore()
        store.add("user", "hi")
        store.add("assistant", "hello")
        self.assertEqual(
            store.history(), [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        )

    def test_history_is_a_copy(self) -> None:
        store = ConversationStore()
        store.add("user", "hi")
        store.history().append({"role": "x", "content": "y"})
        self.assertEqual(len(store.history()), 1)


class LLMParseTests(unittest.TestCase):
    def test_parses_choices_content(self) -> None:
        payload = {"choices": [{"message": {"role": "assistant", "content": "pong"}}]}
        self.assertEqual(parse_completion(payload), "pong")

    def test_empty_choices_returns_empty(self) -> None:
        self.assertEqual(parse_completion({"choices": []}), "")


if __name__ == "__main__":
    unittest.main()
