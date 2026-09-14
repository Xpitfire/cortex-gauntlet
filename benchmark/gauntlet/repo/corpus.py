"""Track R corpus: small, self-contained, stdlib-only repositories with one real bug each.

Each task ships a buggy base repo + a hidden test that fails on it, plus the reference fix. The bug is
a realistic logic error (wrong predicate, wrong data-structure discipline, missing normalization) so a
correct patch is small and unambiguous, and the hidden test is a clean fail→pass oracle.
"""

from __future__ import annotations

from .models import RepoTask

# 1) wrong predicate: sum_evens sums odds
_SUM_EVENS = RepoTask(
    id="sum-evens",
    title="sum_evens returns the sum of odd numbers",
    problem_statement=(
        "mathlib.calc.sum_evens(nums) should return the sum of the EVEN numbers in nums, but it "
        "currently returns the sum of the odd numbers. Fix it so even numbers are summed (and an "
        "empty list sums to 0)."
    ),
    files={
        "mathlib/__init__.py": "",
        "mathlib/calc.py": "def sum_evens(nums):\n    return sum(n for n in nums if n % 2 == 1)\n",
    },
    fix_files={"mathlib/calc.py": "def sum_evens(nums):\n    return sum(n for n in nums if n % 2 == 0)\n"},
    hidden_test=(
        "from mathlib.calc import sum_evens\n\n"
        "def test_sum_evens():\n"
        "    assert sum_evens([1, 2, 3, 4]) == 6\n"
        "    assert sum_evens([2, 4, 6]) == 12\n"
        "    assert sum_evens([]) == 0\n"
        "    assert sum_evens([1, 3, 5]) == 0\n"
    ),
    edit_paths=["mathlib/calc.py"],
)

# 2) wrong data-structure discipline: a "stack" that pops FIFO
_STACK = RepoTask(
    id="stack-lifo",
    title="Stack.pop removes the oldest item (FIFO) instead of the newest (LIFO)",
    problem_statement=(
        "ds.stack.Stack is meant to be a last-in-first-out stack, but Stack.pop() removes the OLDEST "
        "item instead of the most recently pushed one. Fix pop() so the stack is LIFO; popping an "
        "empty stack should raise IndexError."
    ),
    files={
        "ds/__init__.py": "",
        "ds/stack.py": (
            "class Stack:\n"
            "    def __init__(self):\n        self._items = []\n\n"
            "    def push(self, value):\n        self._items.append(value)\n\n"
            "    def pop(self):\n        return self._items.pop(0)\n\n"
            "    def __len__(self):\n        return len(self._items)\n"
        ),
    },
    fix_files={
        "ds/stack.py": (
            "class Stack:\n"
            "    def __init__(self):\n        self._items = []\n\n"
            "    def push(self, value):\n        self._items.append(value)\n\n"
            "    def pop(self):\n        return self._items.pop()\n\n"
            "    def __len__(self):\n        return len(self._items)\n"
        )
    },
    hidden_test=(
        "import pytest\n\nfrom ds.stack import Stack\n\n"
        "def test_lifo_order():\n"
        "    s = Stack()\n    s.push(1); s.push(2); s.push(3)\n"
        "    assert s.pop() == 3\n    assert s.pop() == 2\n    assert s.pop() == 1\n"
        "    assert len(s) == 0\n\n"
        "def test_empty_raises():\n"
        "    with pytest.raises(IndexError):\n        Stack().pop()\n"
    ),
    edit_paths=["ds/stack.py"],
)

# 3) missing normalization: slugify does not lowercase or strip punctuation
_SLUGIFY = RepoTask(
    id="slugify-normalize",
    title="slugify does not lowercase or strip punctuation",
    problem_statement=(
        "textutil.slug.slugify(s) should produce a URL slug: lowercase, words separated by single "
        "hyphens, with all non-alphanumeric characters removed and no leading/trailing hyphens. It "
        "currently only replaces spaces with hyphens. Fix it to fully normalize the string."
    ),
    files={
        "textutil/__init__.py": "",
        "textutil/slug.py": "def slugify(s):\n    return s.replace(' ', '-')\n",
    },
    fix_files={
        "textutil/slug.py": (
            "import re\n\n"
            "def slugify(s):\n"
            "    s = re.sub(r'[^a-z0-9]+', '-', s.lower())\n"
            "    return s.strip('-')\n"
        )
    },
    hidden_test=(
        "from textutil.slug import slugify\n\n"
        "def test_slugify():\n"
        "    assert slugify('Hello World!') == 'hello-world'\n"
        "    assert slugify('  Spaced  Out  ') == 'spaced-out'\n"
        "    assert slugify('A/B & C') == 'a-b-c'\n"
    ),
    edit_paths=["textutil/slug.py"],
)

# 4) off-by-one: page_count truncates instead of rounding up
_PAGINATE = RepoTask(
    id="paginate-ceil",
    title="page_count truncates the final partial page",
    problem_statement=(
        "pagelib.page.page_count(total, per_page) should return the number of pages needed to show "
        "`total` items at `per_page` per page, rounding up for a partial last page. It currently uses "
        "integer division, dropping the final partial page. Fix it (0 items is 0 pages)."
    ),
    files={
        "pagelib/__init__.py": "",
        "pagelib/page.py": "def page_count(total, per_page):\n    return total // per_page\n",
    },
    fix_files={
        "pagelib/page.py": "def page_count(total, per_page):\n    return -(-total // per_page)\n"
    },
    hidden_test=(
        "from pagelib.page import page_count\n\n"
        "def test_page_count():\n"
        "    assert page_count(10, 3) == 4\n    assert page_count(9, 3) == 3\n"
        "    assert page_count(0, 3) == 0\n    assert page_count(1, 3) == 1\n"
    ),
    edit_paths=["pagelib/page.py"],
)

# 5) missing normalization: word_count is case-sensitive
_WORDCOUNT = RepoTask(
    id="wordcount-casefold",
    title="word_count is case-sensitive",
    problem_statement=(
        "countlib.words.word_count(text) should count word frequencies case-insensitively, returning a "
        "dict of lowercase word -> count. It currently counts case-sensitively, so 'The' and 'the' are "
        "separate keys. Fix it to fold case."
    ),
    files={
        "countlib/__init__.py": "",
        "countlib/words.py": (
            "from collections import Counter\n\n"
            "def word_count(text):\n    return dict(Counter(text.split()))\n"
        ),
    },
    fix_files={
        "countlib/words.py": (
            "from collections import Counter\n\n"
            "def word_count(text):\n    return dict(Counter(text.lower().split()))\n"
        )
    },
    hidden_test=(
        "from countlib.words import word_count\n\n"
        "def test_word_count():\n"
        "    assert word_count('The the THE') == {'the': 3}\n"
        "    assert word_count('a A b') == {'a': 2, 'b': 1}\n"
    ),
    edit_paths=["countlib/words.py"],
)

# 6) incomplete guard: clamp forgets the lower bound
_CLAMP = RepoTask(
    id="clamp-bounds",
    title="clamp ignores the lower bound",
    problem_statement=(
        "numlib.clamp.clamp(x, lo, hi) should constrain x to the inclusive range [lo, hi]. It currently "
        "applies only the upper bound, so values below lo pass through unchanged. Fix it to apply both."
    ),
    files={
        "numlib/__init__.py": "",
        "numlib/clamp.py": "def clamp(x, lo, hi):\n    return min(x, hi)\n",
    },
    fix_files={"numlib/clamp.py": "def clamp(x, lo, hi):\n    return max(lo, min(x, hi))\n"},
    hidden_test=(
        "from numlib.clamp import clamp\n\n"
        "def test_clamp():\n"
        "    assert clamp(5, 0, 10) == 5\n    assert clamp(-3, 0, 10) == 0\n"
        "    assert clamp(15, 0, 10) == 10\n"
    ),
    edit_paths=["numlib/clamp.py"],
)

from .hard_tasks import HARD_TASKS  # noqa: E402 — appended after the easy tier is defined

# easy tier (one-line bugs) first, then the hard tier (subtle, multi-file, anti-overfit + regression)
_TASKS = (_SUM_EVENS, _STACK, _SLUGIFY, _PAGINATE, _WORDCOUNT, _CLAMP) + HARD_TASKS


def load_repo_tasks() -> list[RepoTask]:
    return list(_TASKS)
