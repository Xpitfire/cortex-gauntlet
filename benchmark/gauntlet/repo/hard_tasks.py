"""Track R hard corpus: subtle, repo-shaped bugs where the OBVIOUS fix passes the shown test but a
held-out (anti-overfit) test or a regression test still fails — so the graded judge separates a
genuinely-correct fix from a plausible-but-overfit one. stdlib-only, self-contained (temp-dir pytest).

Each task: a buggy package, the gold fix, a shown hidden test (FAIL_TO_PASS), a held-out test the arm
never sees (catches overfit/partial fixes), and a regression test (PASS_TO_PASS — behaviour that
already works on the buggy base and must keep working).
"""

from __future__ import annotations

from .models import RepoTask

# 1) LRU cache: get() does not refresh recency, so a recently-READ key is wrongly evicted.
_LRU = RepoTask(
    id="lru-recency",
    title="LRUCache.get does not refresh recency, evicting recently-read keys",
    problem_statement=(
        "lru.cache.LRUCache(capacity) is a fixed-size LRU cache with get(key) (returns the value or -1) "
        "and put(key, value). Reading a key with get() should mark it as most-recently-used so it is NOT "
        "the next one evicted, but currently only put() refreshes recency — so a key you just read can be "
        "evicted before a stale one. Fix get() so reads count as use."
    ),
    files={
        "lru/__init__.py": "from .cache import LRUCache\n",
        "lru/cache.py": (
            "class LRUCache:\n"
            "    def __init__(self, capacity):\n"
            "        self.capacity = capacity\n"
            "        self._d = {}\n\n"
            "    def get(self, key):\n"
            "        return self._d.get(key, -1)\n\n"
            "    def put(self, key, value):\n"
            "        if key in self._d:\n"
            "            del self._d[key]\n"
            "        elif len(self._d) >= self.capacity:\n"
            "            del self._d[next(iter(self._d))]\n"
            "        self._d[key] = value\n\n"
            "    def __len__(self):\n"
            "        return len(self._d)\n"
        ),
    },
    fix_files={
        "lru/cache.py": (
            "class LRUCache:\n"
            "    def __init__(self, capacity):\n"
            "        self.capacity = capacity\n"
            "        self._d = {}\n\n"
            "    def get(self, key):\n"
            "        if key not in self._d:\n"
            "            return -1\n"
            "        self._d[key] = self._d.pop(key)\n"
            "        return self._d[key]\n\n"
            "    def put(self, key, value):\n"
            "        if key in self._d:\n"
            "            del self._d[key]\n"
            "        elif len(self._d) >= self.capacity:\n"
            "            del self._d[next(iter(self._d))]\n"
            "        self._d[key] = value\n\n"
            "    def __len__(self):\n"
            "        return len(self._d)\n"
        )
    },
    hidden_test=(
        "from lru.cache import LRUCache\n\n"
        "def test_get_protects_from_eviction():\n"
        "    c = LRUCache(2)\n"
        "    c.put(1, 1); c.put(2, 2)\n"
        "    assert c.get(1) == 1\n"
        "    c.put(3, 3)\n"
        "    assert c.get(2) == -1\n"
        "    assert c.get(1) == 1 and c.get(3) == 3\n"
    ),
    held_out_test=(
        "from lru.cache import LRUCache\n\n"
        "def test_update_refreshes():\n"
        "    c = LRUCache(2)\n"
        "    c.put(1, 1); c.put(2, 2); c.put(1, 10)\n"
        "    c.put(3, 3)\n"
        "    assert c.get(2) == -1 and c.get(1) == 10 and c.get(3) == 3\n\n"
        "def test_interleaved():\n"
        "    c = LRUCache(3)\n"
        "    for k in (1, 2, 3): c.put(k, k)\n"
        "    assert c.get(1) == 1\n"
        "    c.put(4, 4)\n"
        "    assert c.get(2) == -1\n"
        "    assert c.get(1) == 1 and c.get(3) == 3 and c.get(4) == 4\n"
    ),
    regression_test=(
        "from lru.cache import LRUCache\n\n"
        "def test_basic_within_capacity():\n"
        "    c = LRUCache(2)\n"
        "    c.put(1, 1); c.put(2, 2)\n"
        "    assert c.get(1) == 1 and c.get(2) == 2\n"
        "    assert c.get(9) == -1\n"
        "    assert len(c) == 2\n"
    ),
    edit_paths=["lru/cache.py"],
    difficulty="hard",
)

# 2) interval merge: assumes sorted input and uses a strict '<', so it misses touching + unsorted.
_INTERVALS = RepoTask(
    id="interval-merge",
    title="merge() misses touching intervals and assumes sorted input",
    problem_statement=(
        "intervals.merge.merge(intervals) takes a list of [start, end] pairs and returns the minimal list "
        "of merged, non-overlapping intervals. It currently assumes the input is already sorted and only "
        "merges when one interval starts strictly before the previous one ends — so it fails on unsorted "
        "input and on touching intervals like [1,4],[4,5] (which should merge to [1,5]). Fix it."
    ),
    files={
        "intervals/__init__.py": "from .merge import merge\n",
        "intervals/merge.py": (
            "def merge(intervals):\n"
            "    out = []\n"
            "    for s, e in intervals:\n"
            "        if out and s < out[-1][1]:\n"
            "            out[-1][1] = max(out[-1][1], e)\n"
            "        else:\n"
            "            out.append([s, e])\n"
            "    return out\n"
        ),
    },
    fix_files={
        "intervals/merge.py": (
            "def merge(intervals):\n"
            "    out = []\n"
            "    for s, e in sorted(intervals):\n"
            "        if out and s <= out[-1][1]:\n"
            "            out[-1][1] = max(out[-1][1], e)\n"
            "        else:\n"
            "            out.append([s, e])\n"
            "    return out\n"
        )
    },
    hidden_test=(
        "from intervals.merge import merge\n\n"
        "def test_overlap_and_touch():\n"
        "    assert merge([[1, 3], [2, 6], [8, 10], [15, 18]]) == [[1, 6], [8, 10], [15, 18]]\n"
        "    assert merge([[1, 4], [4, 5]]) == [[1, 5]]\n"
    ),
    held_out_test=(
        "from intervals.merge import merge\n\n"
        "def test_unsorted():\n"
        "    assert merge([[2, 6], [1, 3], [15, 18], [8, 10]]) == [[1, 6], [8, 10], [15, 18]]\n\n"
        "def test_nested():\n"
        "    assert merge([[1, 10], [2, 5], [6, 9]]) == [[1, 10]]\n"
    ),
    regression_test=(
        "from intervals.merge import merge\n\n"
        "def test_basics():\n"
        "    assert merge([]) == []\n"
        "    assert merge([[1, 2]]) == [[1, 2]]\n"
        "    assert merge([[1, 2], [3, 4]]) == [[1, 2], [3, 4]]\n"
    ),
    edit_paths=["intervals/merge.py"],
    difficulty="hard",
)

# 3) dependency resolver: no visited set -> diamonds duplicate and cycles recurse forever (no detection).
_DEPS = RepoTask(
    id="dep-resolve",
    title="resolve() duplicates diamond deps and never detects cycles",
    problem_statement=(
        "deps.graph.resolve(graph) takes a dict {node: [dependencies]} and returns a list giving a valid "
        "install order (every dependency before the nodes that need it). It currently emits a node once "
        "per path to it (so diamond dependencies appear multiple times) and recurses forever on a cycle. "
        "Fix it so each node appears exactly once and a cyclic graph raises ValueError."
    ),
    files={
        "deps/__init__.py": "from .graph import resolve\n",
        "deps/graph.py": (
            "def resolve(graph):\n"
            "    order = []\n"
            "    def visit(n):\n"
            "        for d in graph.get(n, []):\n"
            "            visit(d)\n"
            "        order.append(n)\n"
            "    for n in graph:\n"
            "        visit(n)\n"
            "    return order\n"
        ),
    },
    fix_files={
        "deps/graph.py": (
            "def resolve(graph):\n"
            "    order, seen, stack = [], set(), set()\n"
            "    def visit(n):\n"
            "        if n in seen:\n"
            "            return\n"
            "        if n in stack:\n"
            "            raise ValueError(f'cycle through {n!r}')\n"
            "        stack.add(n)\n"
            "        for d in graph.get(n, []):\n"
            "            visit(d)\n"
            "        stack.discard(n)\n"
            "        seen.add(n)\n"
            "        order.append(n)\n"
            "    for n in graph:\n"
            "        visit(n)\n"
            "    return order\n"
        )
    },
    hidden_test=(
        "from deps.graph import resolve\n\n"
        "def test_diamond_each_once():\n"
        "    g = {'app': ['a', 'b'], 'a': ['base'], 'b': ['base'], 'base': []}\n"
        "    order = resolve(g)\n"
        "    assert sorted(order) == ['a', 'app', 'b', 'base']\n"
        "    assert order.index('base') < order.index('a') < order.index('app')\n"
    ),
    held_out_test=(
        "import pytest\n\nfrom deps.graph import resolve\n\n"
        "def test_cycle_raises():\n"
        "    with pytest.raises(ValueError):\n"
        "        resolve({'a': ['b'], 'b': ['a']})\n\n"
        "def test_long_chain():\n"
        "    assert resolve({'d': ['c'], 'c': ['b'], 'b': ['a'], 'a': []}) == ['a', 'b', 'c', 'd']\n"
    ),
    regression_test=(
        "from deps.graph import resolve\n\n"
        "def test_independent_nodes():\n"
        "    assert sorted(resolve({'a': [], 'b': [], 'c': []})) == ['a', 'b', 'c']\n"
        "    assert resolve({}) == []\n"
    ),
    edit_paths=["deps/graph.py"],
    difficulty="hard",
)

# 4) bill split: integer division drops the remainder, so the shares do not sum to the total.
_SPLIT = RepoTask(
    id="bill-split",
    title="split_bill loses the remainder cents",
    problem_statement=(
        "billing.split.split_bill(total_cents, n) splits a bill into n integer-cent shares that must sum "
        "EXACTLY to total_cents, with the shares as equal as possible (any leftover cents distributed one "
        "each to the earliest shares). It currently returns n copies of total_cents // n, so the remainder "
        "cents are lost and the shares do not sum to the total. Fix it."
    ),
    files={
        "billing/__init__.py": "from .split import split_bill\n",
        "billing/split.py": (
            "def split_bill(total_cents, n):\n"
            "    share = total_cents // n\n"
            "    return [share] * n\n"
        ),
    },
    fix_files={
        "billing/split.py": (
            "def split_bill(total_cents, n):\n"
            "    base = total_cents // n\n"
            "    rem = total_cents - base * n\n"
            "    return [base + (1 if i < rem else 0) for i in range(n)]\n"
        )
    },
    hidden_test=(
        "from billing.split import split_bill\n\n"
        "def test_remainder_distributed():\n"
        "    shares = split_bill(100, 3)\n"
        "    assert sum(shares) == 100\n"
        "    assert max(shares) - min(shares) <= 1\n"
    ),
    held_out_test=(
        "from billing.split import split_bill\n\n"
        "def test_many_totals():\n"
        "    for total, n in [(101, 3), (10, 4), (7, 7), (0, 5), (1, 3)]:\n"
        "        s = split_bill(total, n)\n"
        "        assert len(s) == n and sum(s) == total and max(s) - min(s) <= 1\n\n"
        "def test_extra_cents_to_first():\n"
        "    assert split_bill(100, 3) == [34, 33, 33]\n"
    ),
    regression_test=(
        "from billing.split import split_bill\n\n"
        "def test_even_split():\n"
        "    assert split_bill(90, 3) == [30, 30, 30]\n"
        "    assert split_bill(100, 1) == [100]\n"
    ),
    edit_paths=["billing/split.py"],
    difficulty="hard",
)

# 5) CSV line parser: naive split(',') breaks on quoted fields containing commas or escaped quotes.
_CSV = RepoTask(
    id="csv-quoted",
    title="parse_line splits inside quoted fields",
    problem_statement=(
        "csvlite.parse.parse_line(line) parses ONE line of CSV into a list of field strings. It currently "
        "does line.split(','), which breaks any quoted field that contains a comma (e.g. 'a,\"b,c\",d' must "
        "parse to ['a', 'b,c', 'd']), and it does not handle doubled quotes (\"\" -> a literal \") inside a "
        "quoted field. Fix it to parse quoted fields correctly."
    ),
    files={
        "csvlite/__init__.py": "from .parse import parse_line\n",
        "csvlite/parse.py": (
            "def parse_line(line):\n"
            "    return line.split(',')\n"
        ),
    },
    fix_files={
        "csvlite/parse.py": (
            "import csv\n\n"
            "def parse_line(line):\n"
            "    return next(csv.reader([line]))\n"
        )
    },
    hidden_test=(
        "from csvlite.parse import parse_line\n\n"
        "def test_quoted_comma():\n"
        "    assert parse_line('a,\"b,c\",d') == ['a', 'b,c', 'd']\n"
    ),
    held_out_test=(
        "from csvlite.parse import parse_line\n\n"
        "def test_escaped_quote():\n"
        "    assert parse_line('\"she said \"\"hi\"\"\",x') == ['she said \"hi\"', 'x']\n\n"
        "def test_quoted_empty_and_plain():\n"
        "    assert parse_line('\"\",a,\"b\"') == ['', 'a', 'b']\n"
    ),
    regression_test=(
        "from csvlite.parse import parse_line\n\n"
        "def test_plain_rows():\n"
        "    assert parse_line('a,b,c') == ['a', 'b', 'c']\n"
        "    assert parse_line('x') == ['x']\n"
    ),
    edit_paths=["csvlite/parse.py"],
    difficulty="hard",
)

HARD_TASKS = (_LRU, _INTERVALS, _DEPS, _SPLIT, _CSV)
