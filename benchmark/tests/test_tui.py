"""Tests for the reusable experiment-TUI core (events → model → runner), no UI / no network."""

from gauntlet.terminal import TerminalChunk
from gauntlet.tui.events import CellRef, CellStatus, EventBus
from gauntlet.tui.model import ExperimentTree
from gauntlet.tui.runner import CellOutcome, CellSpec, ExperimentRunner


def test_copy_shortcuts_bound():
    """ctrl+c / cmd+c copy the editor selection (the user-facing fix); quit stays on q."""
    from gauntlet.tui.app import GauntletApp

    keys = {(b.key if hasattr(b, "key") else b[0]): (b.action if hasattr(b, "action") else b[1])
            for b in GauntletApp.BINDINGS}
    assert keys.get("ctrl+c") == "smart_copy" and keys.get("super+c") == "smart_copy"
    assert hasattr(GauntletApp, "action_smart_copy") and keys.get("q") == "quit"


def test_file_preview_uses_collapsible_tree():
    from types import SimpleNamespace

    from gauntlet.tui.app import GauntletApp
    from textual.widgets import Tree

    app = GauntletApp("t", [], loaded=ExperimentTree())
    tree = Tree("files")
    opened = []
    app.query_one = lambda _sel, _kind=None: tree
    app._load_editor = lambda content, language: opened.append((content, language))
    app._populate_files(SimpleNamespace(
        prompt="prompt",
        files={
            "README.md": "readme",
            "src/components/ProductCard.tsx": "card",
            "src/lib/api.ts": "api",
        },
        result="",
        error=None,
    ))

    labels = [str(child.label.plain) for child in tree.root.children]
    src = next(child for child in tree.root.children if child.label.plain == "src")
    assert labels == ["✎ prompt", "README.md", "src"]
    assert [child.label.plain for child in src.children] == ["components", "lib"]
    assert opened == [("prompt", "markdown")]


def test_terminal_selection_is_copied_when_editor_has_no_selection():
    from types import SimpleNamespace

    from gauntlet.tui.app import GauntletApp

    app = GauntletApp("t", [], loaded=ExperimentTree())
    copied = []
    editor = SimpleNamespace(selected_text="")
    terminal = SimpleNamespace(text_selection=object(), get_selection=lambda _s: ("terminal text", "\n"))
    app.query_one = lambda sel, _kind=None: editor if sel == "#editor" else terminal
    app._clipboard_copy = lambda text: copied.append(text) or "clipboard"
    app.notify = lambda *_a, **_k: None

    app.action_smart_copy()

    assert copied == ["terminal text"]


def test_terminal_output_preserves_manual_scroll_position():
    from gauntlet.tui.app import GauntletApp

    class _Terminal:
        max_scroll_y = 20
        is_vertical_scroll_end = False
        auto_scroll = True

        def __init__(self):
            self.writes = []

        def write(self, text, **kwargs):
            self.writes.append((text, kwargs))

    app = GauntletApp("t", [], loaded=ExperimentTree())
    terminal = _Terminal()
    app.query_one = lambda *_a, **_k: terminal

    app._write_terminal("new line")

    assert terminal.auto_scroll is False
    assert terminal.writes == [("new line", {"scroll_end": False})]


def test_terminal_output_follows_when_at_bottom():
    from gauntlet.tui.app import GauntletApp

    class _Terminal:
        max_scroll_y = 20
        is_vertical_scroll_end = True
        auto_scroll = False

        def __init__(self):
            self.writes = []

        def write(self, text, **kwargs):
            self.writes.append((text, kwargs))

    app = GauntletApp("t", [], loaded=ExperimentTree())
    terminal = _Terminal()
    app.query_one = lambda *_a, **_k: terminal

    app._write_terminal("new line")

    assert terminal.auto_scroll is True
    assert terminal.writes == [("new line", {"scroll_end": True})]


def _spec(name: str, harness: str, fn) -> CellSpec:
    return CellSpec(CellRef("t", "grp", name, harness), harness, f"prompt {name}", fn)


def _ok(emit):
    emit("working\n")
    return CellOutcome(CellStatus.PASS, output="result", detail={"k": "v"})


def _streamed(emit):
    emit(TerminalChunk("$ npm test\n", "cmd:1", "npm test"))
    emit(TerminalChunk("ok\n", "cmd:1", "npm test", stream_done=True))
    return CellOutcome(CellStatus.PASS, output="result")


def _fail(emit):
    return CellOutcome(CellStatus.FAIL, output="bad")


def _boom(emit):
    raise ValueError("synthetic")


def _run(specs):
    bus, tree = EventBus(), ExperimentTree()
    bus.subscribe(tree)
    finished = ExperimentRunner(bus).run("t", specs)
    return tree, finished


def test_exception_is_isolated_not_propagated():
    tree, finished = _run([_spec("a", "h1", _ok), _spec("b", "h1", _boom), _spec("c", "h1", _ok)])
    assert finished.passed == 2 and finished.errored == 1
    assert tree.done == 3 and tree.progress == 1.0
    boom = tree.cell("t/grp/b/h1")
    assert boom.status is CellStatus.ERROR
    assert boom.error and "ValueError: synthetic" in boom.error


def test_captures_prompt_output_detail():
    tree, _ = _run([_spec("a", "h1", _ok)])
    cell = tree.cell("t/grp/a/h1")
    assert cell.prompt == "prompt a"
    assert cell.output == "working\n"  # streamed
    assert cell.result == "result" and cell.detail == {"k": "v"}


def test_captures_structured_terminal_streams():
    tree, _ = _run([_spec("a", "h1", _streamed)])
    cell = tree.cell("t/grp/a/h1")
    assert cell.output == "$ npm test\nok\n"
    assert cell.terminal_streams["cmd:1"] == "$ npm test\nok\n"
    assert cell.terminal_labels["cmd:1"] == "npm test"
    assert "cmd:1" in cell.terminal_done


def test_group_status_rollup_worst_wins():
    tree, _ = _run([_spec("a", "h1", _ok), _spec("a", "h2", _fail)])
    assert tree.groups[0].status is CellStatus.FAIL


def test_preload_shows_full_plan_pending():
    refs = [(CellRef("t", "g", "x", "h1"), "H1"), (CellRef("t", "g", "y", "h2"), "H2")]
    tree = ExperimentTree()
    tree.preload("t", [("h1", "H1"), ("h2", "H2")], refs)
    assert tree.total == 2 and tree.done == 0
    assert all(c.status is CellStatus.PENDING for g in tree.groups for c in g.cells)


def test_status_glyphs_distinct():
    glyphs = {s.glyph for s in CellStatus}
    assert len(glyphs) == len(CellStatus)
