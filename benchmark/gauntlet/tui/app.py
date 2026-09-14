"""The Gauntlet experiment IDE — a Textual, full-screen, syntax-highlighted live view of a run.

Far left: a mouse-clickable experiment tree (track → group → item × harness) with live status
glyphs. Centre: a styled cell header + metric chips, a file browser (prompt, model output, every
generated file, traceback) and a syntax-highlighted read-only editor, plus a streaming terminal
pane. Right: a per-harness pass/fail roll-up. Top: a themed progress bar over all cells. The run
executes in a worker thread; events are marshalled to the UI thread.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

from rich.markup import escape
from textual import work
from textual.app import App, ComposeResult, ScreenStackError
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.theme import Theme
from textual.widgets import Footer, ProgressBar, RichLog, Static, TabbedContent, TabPane, TextArea, Tree
from textual.widgets.tree import TreeNode

from .events import (
    CellFinished,
    CellOutput,
    CellStarted,
    CellStatus,
    Event,
    EventBus,
    Observer,
    RunFinished,
    RunStarted,
)
from .model import ExperimentTree
from .render import cell_header, group_header, language_for, status_label, summary_table
from .runner import CellSpec, ExperimentRunner

# true-black, high-contrast theme (vivid accents on #000) — the IDE's default look
NOIR = Theme(
    name="gauntlet-noir", dark=True,
    background="#000000", surface="#0a0b10", panel="#0c0e15", boost="#15171f",
    foreground="#e8e8f2", primary="#7aa2f7", secondary="#bb9af7", accent="#7dcfff",
    success="#9ece6a", warning="#e0af68", error="#f7768e",
)
EDITOR_THEME = "monokai"  # vivid tree-sitter syntax highlighting on the dark editor
# a file-browser entry: (label, kind, payload) where kind is "file" or "cell"
_PROMPT = "✎ prompt"
_TRACE = "⚠ traceback"
_MAIN_STREAM = "terminal"


class _Forwarder(Observer):
    """Worker-thread observer that marshals every event onto the UI thread."""

    def __init__(self, app: GauntletApp) -> None:
        self._app = app

    def on_event(self, event: Event) -> None:
        self._app.call_from_thread(self._app.apply_event, event)


class GauntletApp(App):
    """IDE-style live runner for a list of experiment cells."""

    CSS_PATH = "app.tcss"
    # Footer is rendered in this order — grouped: Copy · View · Run · Quit.
    BINDINGS = [
        # Copy — selection (else whole file) / file / prompt. ctrl+c is priority=True so it beats the
        # app's default ctrl+c regardless of focused pane; quit lives on q, away from the copy keys.
        Binding("ctrl+c", "smart_copy", "Copy", priority=True),
        Binding("super+c", "smart_copy", "Copy", priority=True, show=False),
        Binding("ctrl+y", "smart_copy", "Copy", show=False),
        ("y", "copy_file", "Copy file"),
        ("p", "copy_prompt", "Copy prompt"),
        # View — tree / editor display
        ("f", "toggle_follow", "Follow"),
        ("e", "expand_all", "Expand"),
        ("c", "collapse_all", "Collapse"),
        ("w", "toggle_wrap", "Wrap"),
        # Run control
        Binding("ctrl+z", "pause", "Pause"),  # graceful pause after the current cell (resume later)
        Binding("r", "resume", "Resume"),     # after a pause: retry from the checkpoint (skips done cells)
        # App
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self, track: str, specs: list[CellSpec],
        finalize: Callable[[list], str | None] | None = None,
        loaded: ExperimentTree | None = None,
        checkpoint: object | None = None,
        workers: int = 1,
    ) -> None:
        super().__init__()
        self._track = track
        self._specs = specs
        self._finalize = finalize
        self._checkpoint = checkpoint  # resume completed cells + pause (not fail) on a rate limit
        # NOTE: NOT `self._workers` — Textual's App reserves that name for its WorkerManager (App.workers
        # returns self._workers); clobbering it crashes shutdown with `'int' has no attribute cancel_node`.
        self._cell_workers = workers  # >1 runs provider arms concurrently (one thread per harness)
        self._loaded = loaded  # viewer mode: a pre-scored tree to browse (no run)
        self._tree_model = loaded if loaded is not None else ExperimentTree()
        self._cell_nodes: dict[str, TreeNode] = {}
        self._group_nodes: dict[str, TreeNode] = {}
        self._follow = True
        self._run_started: float | None = None  # monotonic start, for the elapsed clock
        self._paused = False         # run stopped on an infra issue / user pause — resumable in-TUI
        self._resumed_once = False   # so a re-pause reads "still couldn't continue"
        self._selected_key: str | None = None
        self._editor_state: tuple[str, str] = ("", "")  # (content, language) of the open file
        self._terminal_logs: dict[str, RichLog] = {}
        self._terminal_panes: dict[str, str] = {}
        self._terminal_seq = 0

    @staticmethod
    def _terminal_should_follow(terminal: RichLog) -> bool:
        return terminal.max_scroll_y <= 0 or terminal.is_vertical_scroll_end

    # ---- layout ---------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static("Gauntlet", id="title")
            yield ProgressBar(total=max(len(self._specs), 1), show_eta=False, id="pbar")
            yield Static("", id="counts")
        with Horizontal(id="body"):
            with VerticalScroll(id="tree-pane"):
                yield Tree(self._track, id="tree")
            with Vertical(id="main-pane"):
                yield Static("Select a cell to inspect its prompt, files, and output.", id="cellbar")
                with Horizontal(id="workarea"):
                    yield Tree("files", id="filetree")
                    yield TextArea("", id="editor", read_only=True, show_line_numbers=True, soft_wrap=True)
                with TabbedContent(initial="terminal-tab-main", id="terminal-tabs"):
                    with TabPane("main", id="terminal-tab-main"):
                        yield RichLog(id="terminal", classes="terminal-log",
                                      highlight=True, markup=False, wrap=False)
            with VerticalScroll(id="side-pane"):
                yield Static("", id="summary")
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(NOIR)
        self.theme = "gauntlet-noir"
        editor = self.query_one("#editor", TextArea)
        if EDITOR_THEME in editor.available_themes:
            editor.theme = EDITOR_THEME
        if self._loaded is None:  # live run: seed the plan, then start the worker
            cells = [(s.ref, s.harness_label) for s in self._specs]
            harnesses = list(dict.fromkeys((s.ref.harness_id, s.harness_label) for s in self._specs))
            self._tree_model.preload(self._track, harnesses, cells)
        self._build_tree()
        filetree = self.query_one("#filetree", Tree)
        filetree.show_root = False
        filetree.border_title = "files"
        self.query_one("#editor", TextArea).border_title = "editor"
        terminal = self.query_one("#terminal", RichLog)
        terminal.border_title = "terminal"
        self._terminal_logs = {_MAIN_STREAM: terminal}
        self._terminal_panes = {_MAIN_STREAM: "terminal-tab-main"}
        self.query_one("#side-pane", VerticalScroll).border_title = "harnesses"
        self._refresh_summary()
        self._update_counts()
        if self._loaded is None:
            self._run_started = time.monotonic()
            self.set_interval(1.0, self._update_counts)  # tick the clock/elapsed even between events
            self._run_experiment()
        else:  # viewer mode: nothing runs; reflect the loaded totals + open the first cell
            self.query_one("#pbar", ProgressBar).advance(self._tree_model.done)
            self._set_status(f"loaded {self._tree_model.done} cells — viewing (q to quit)")
            first = next((c for g in self._tree_model.groups for c in g.cells), None)
            if first is not None:
                self._follow = False
                self._show_cell(first.ref.key)

    def _build_tree(self) -> None:
        tree = self.query_one("#tree", Tree)
        tree.show_root = False
        tree.root.expand()
        for group in self._tree_model.groups:
            node = tree.root.add(self._group_label(group.name, group.status), data=("group", group.name),
                                 expand=False)
            self._group_nodes[group.name] = node
            for cell in group.cells:
                leaf = node.add_leaf(status_label(cell.status, cell.harness_label), data=("cell", cell.ref.key))
                self._cell_nodes[cell.ref.key] = leaf

    # ---- run ------------------------------------------------------------
    @work(thread=True, exclusive=True)
    def _run_experiment(self) -> None:
        bus = EventBus()
        bus.subscribe(_Forwarder(self))
        ExperimentRunner(bus).run(self._track, self._specs, self._finalize,
                                  checkpoint=self._checkpoint, workers=self._cell_workers)

    def apply_event(self, event: Event) -> None:
        """Runs on the UI thread: update the model + widgets for one event."""

        self._tree_model.on_event(event)
        if isinstance(event, RunStarted):
            self._set_status(f"running {event.total} cells…")
        elif isinstance(event, CellStarted):
            self._refresh_node(event.ref.key)
            if self._follow:
                self._show_cell(event.ref.key, follow=True)
            self._set_status(f"▶ {event.ref.group} / {event.ref.name} [{event.harness_label}]")
        elif isinstance(event, CellOutput):
            if event.ref.key == self._selected_key:
                self._write_terminal(event.chunk.rstrip("\n"), stream_id=event.stream_id,
                                     stream_label=event.stream_label, stream_done=event.stream_done)
        elif isinstance(event, CellFinished):
            self._refresh_node(event.ref.key)
            self.query_one("#pbar", ProgressBar).advance(1)
            self._update_counts()
            self._refresh_summary()
            if event.ref.key == self._selected_key:
                cell = self._tree_model.cell(event.ref.key)
                if cell is not None:
                    self.query_one("#cellbar", Static).update(cell_header(cell))
                    self._populate_files(cell)
        elif isinstance(event, RunFinished):
            if event.paused:  # stopped on an infra issue (or a user pause) — offer in-TUI resume
                self._paused = True
                again = " still" if self._resumed_once else ""
                verb = "couldn't continue —" if self._resumed_once else "paused —"
                self._set_status(f"⏸{again} {verb} {event.pause_reason}  ·  "
                                 f"fix it, then press r to resume  (q to quit)")
                return
            self._paused = False
            done = f"✓{event.passed} ✗{event.failed} ⚠{event.errored} –{event.skipped}"
            tail = f" · saved {event.report_path}" if event.report_path else ""
            self._set_status(f"done — {done}{tail}  (q to quit)")

    # ---- tree node labels ----------------------------------------------
    def _refresh_node(self, key: str) -> None:
        cell = self._tree_model.cell(key)
        node = self._cell_nodes.get(key)
        if cell is None or node is None:
            return
        node.set_label(status_label(cell.status, cell.harness_label))
        group = next((g for g in self._tree_model.groups if g.name == cell.ref.group), None)
        group_node = self._group_nodes.get(cell.ref.group)
        if group is not None and group_node is not None:
            group_node.set_label(self._group_label(group.name, group.status))

    def _group_label(self, name: str, status: CellStatus = CellStatus.PENDING):
        return status_label(status, name)

    # ---- main view ------------------------------------------------------
    def _show_cell(self, key: str, *, follow: bool = False) -> None:
        cell = self._tree_model.cell(key)
        if cell is None:
            return
        self._selected_key = key
        self.query_one("#cellbar", Static).update(cell_header(cell))
        self._populate_files(cell)
        self._reset_terminal_tabs()
        streams = cell.terminal_streams or ({_MAIN_STREAM: cell.output} if cell.output else {})
        for stream_id, text in streams.items():
            self._write_terminal(text.rstrip("\n"), stream_id=stream_id,
                                 stream_label=cell.terminal_labels.get(stream_id, stream_id),
                                 stream_done=stream_id in cell.terminal_done, force_follow=True)
        if follow:
            node = self._cell_nodes.get(key)
            if node is not None and node.parent is not None:
                node.parent.expand()

    def _write_terminal(self, text: str, *, stream_id: str = _MAIN_STREAM, stream_label: str = "terminal",
                        stream_done: bool = False, force_follow: bool = False) -> None:
        if not text and not stream_done:
            return
        terminal = self._terminal_log(stream_id, stream_label)
        follow = force_follow or self._terminal_should_follow(terminal)
        terminal.auto_scroll = follow
        if text:
            terminal.write(text, scroll_end=follow)
        if stream_done:
            self._mark_terminal_done(stream_id)

    def _terminal_log(self, stream_id: str, stream_label: str) -> RichLog:
        stream_id = stream_id or _MAIN_STREAM
        if stream_id in self._terminal_logs:
            return self._terminal_logs[stream_id]
        if stream_id == _MAIN_STREAM:
            terminal = self.query_one("#terminal", RichLog)
            self._terminal_logs[stream_id] = terminal
            self._terminal_panes[stream_id] = "terminal-tab-main"
            return terminal
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stream_id)[:48].strip("-_")
        safe = safe or f"stream-{len(self._terminal_logs)}"
        self._terminal_seq += 1
        pane_id = f"terminal-tab-{safe}-{self._terminal_seq}"
        log = RichLog(id=f"terminal-{safe}-{self._terminal_seq}", classes="terminal-log",
                      highlight=True, markup=False, wrap=False)
        log.border_title = stream_label
        self._terminal_logs[stream_id] = log
        self._terminal_panes[stream_id] = pane_id
        self.query_one("#terminal-tabs", TabbedContent).add_pane(TabPane(stream_label, log, id=pane_id))
        return log

    def _mark_terminal_done(self, stream_id: str) -> None:
        pane_id = self._terminal_panes.get(stream_id)
        if pane_id:
            tab = self.query_one("#terminal-tabs", TabbedContent).get_tab(pane_id)
            tab.label = f"✓ {tab.label_text}"

    def _reset_terminal_tabs(self) -> None:
        terminal = self.query_one("#terminal", RichLog)
        terminal.clear()
        terminal.auto_scroll = True
        tabs = self.query_one("#terminal-tabs", TabbedContent)
        for stream_id, pane_id in list(self._terminal_panes.items()):
            if stream_id != _MAIN_STREAM:
                tabs.remove_pane(pane_id)
        self._terminal_logs = {_MAIN_STREAM: terminal}
        self._terminal_panes = {_MAIN_STREAM: "terminal-tab-main"}

    def _populate_files(self, cell) -> None:
        entries: list[tuple[str, str, str | None]] = []  # (label, content, language)
        if cell.prompt:
            entries.append((_PROMPT, cell.prompt, "markdown"))
        for path, content in sorted(cell.files.items()):  # sorted → files cluster by folder
            entries.append((path, content, language_for(path)))
        if not cell.files and cell.result:
            entries.append(("output", cell.result, None))
        if cell.error:
            entries.append((_TRACE, cell.error, "python"))

        tree = self.query_one("#filetree", Tree)
        tree.clear()
        tree.root.expand()
        folders: dict[tuple[str, ...], TreeNode] = {}
        for label, content, language in entries:
            colour = "red" if label == _TRACE else ("yellow" if label == _PROMPT else "default")
            parts = tuple(p for p in label.split("/") if p)
            parent = tree.root
            for idx, folder in enumerate(parts[:-1]):
                key = parts[:idx + 1]
                if key not in folders:
                    folders[key] = parent.add(escape(folder), expand=False)
                parent = folders[key]
            parent.add_leaf(f"[{colour}]{escape(parts[-1] if parts else label)}[/]",
                            data=("file", content, language))
        if entries:
            self._load_editor(entries[0][1], entries[0][2])

    def _load_editor(self, content: str, language: str | None) -> None:
        self._editor_state = (content, language or "")
        editor = self.query_one("#editor", TextArea)
        editor.language = language if language in editor.available_languages else None
        editor.load_text(content)  # resets cursor/selection to the top of the new file

    def _show_group(self, name: str) -> None:
        group = next((g for g in self._tree_model.groups if g.name == name), None)
        if group is None:
            return
        self._selected_key = None
        self.query_one("#cellbar", Static).update(group_header(name, group.status, len(group.cells)))
        tree = self.query_one("#filetree", Tree)
        tree.clear()
        tree.root.expand()
        for cell in group.cells:
            tree.root.add_leaf(status_label(cell.status, cell.harness_label),
                               data=("cell_link", cell.ref.key))
        self._load_editor(f"# {name}\n\nSelect a harness on the left to open its result.", None)

    # ---- right pane + chrome -------------------------------------------
    def _refresh_summary(self) -> None:
        self.query_one("#summary", Static).update(summary_table(self._tree_model))

    def _update_counts(self) -> None:
        t = self._tree_model
        clock = ""
        if self._run_started is not None:  # wall-clock now + elapsed since the run began
            elapsed = int(time.monotonic() - self._run_started)
            clock = (f"  [grey50]⏱ {datetime.now().strftime('%H:%M:%S')} "
                     f"+{elapsed // 3600:d}:{elapsed % 3600 // 60:02d}:{elapsed % 60:02d}[/]")
        self.query_one("#counts", Static).update(
            f"[{CellStatus.PASS.color}]✓{t.count(CellStatus.PASS)}[/] "
            f"[{CellStatus.FAIL.color}]✗{t.count(CellStatus.FAIL)}[/] "
            f"[{CellStatus.ERROR.color}]⚠{t.count(CellStatus.ERROR)}[/] "
            f"[{CellStatus.SKIP.color}]–{t.count(CellStatus.SKIP)}[/] · {t.done}/{t.total}{clock}"
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#title", Static).update(escape(f"Gauntlet · {self._track} — {text}"))

    # ---- interaction ----------------------------------------------------
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if event.control.id == "filetree":
            if data is None:
                if event.node.allow_expand:
                    event.node.collapse() if event.node.is_expanded else event.node.expand()
                return
            kind, *payload = data
            if kind == "file":
                self._load_editor(payload[0], payload[1])
            elif kind == "cell_link":
                self._show_cell(payload[0])
            return
        if not data:
            return
        kind, value = data
        self._follow = False  # manual browse pins the view
        if kind == "cell":
            self._show_cell(value)
        elif kind == "group":
            self._show_group(value)

    def action_toggle_follow(self) -> None:
        self._follow = not self._follow
        self._set_status(f"follow {'on' if self._follow else 'off'}")

    def action_pause(self) -> None:
        """Pause gracefully: the current cell finishes and is checkpointed, then the run stops. Resume
        later with `--resume`. Drops a PAUSE sentinel the runner thread watches between cells."""
        cp = self._checkpoint
        if self._loaded is not None or cp is None:  # viewer mode / no checkpoint → nothing to pause
            self._set_status("nothing to pause")
            return
        (cp.path.parent / "PAUSE").write_text("paused by user\n", encoding="utf-8")
        self._set_status(f"pausing after the current cell — press r to resume (or --resume {cp.path.parent.name})")

    def action_resume(self) -> None:
        """After a pause (infra issue or user pause), retry from the checkpoint without leaving the TUI:
        re-runs the experiment, which replays already-done cells instantly and continues from where it
        stopped. If the same infra issue recurs it auto-pauses again with a 'still couldn't' message."""
        if self._loaded is not None or self._checkpoint is None:
            self._set_status("nothing to resume")
            return
        if not self._paused:
            self._set_status("not paused — nothing to resume")
            return
        cp = self._checkpoint
        if (cp.path.parent / "PAUSE").exists():  # clear a user-pause sentinel so it doesn't re-pause
            (cp.path.parent / "PAUSE").unlink()
        self._paused = False
        self._resumed_once = True
        self._tree_model.finished = False
        self.query_one("#pbar", ProgressBar).update(progress=0)  # replayed cells re-advance it cleanly
        self._set_status("resuming — replaying completed cells, then continuing…")
        self._run_experiment()  # new worker: reads the checkpoint (skips done), continues from the gap

    def action_expand_all(self) -> None:
        target = "#filetree" if self.focused and self.focused.id == "filetree" else "#tree"
        self.query_one(target, Tree).root.expand_all()

    def action_collapse_all(self) -> None:
        if self.focused and self.focused.id == "filetree":
            self.query_one("#filetree", Tree).root.collapse_all()
        else:
            for node in self._group_nodes.values():
                node.collapse()

    def action_toggle_wrap(self) -> None:
        editor = self.query_one("#editor", TextArea)
        editor.soft_wrap = not editor.soft_wrap

    # ---- clipboard ------------------------------------------------------
    # ctrl+c / cmd+c copy the editor selection (drag or shift+arrows to select), falling back to the
    # whole file when nothing is selected; y/p copy the whole file/prompt.
    def _clipboard_copy(self, text: str) -> str:
        """Copy to BOTH the terminal clipboard (OSC 52 — works over SSH) AND the OS clipboard via the
        native tool (pbcopy / wl-copy / xclip / xsel). Many macOS terminals silently drop OSC 52, so
        without the native write CMD+V stays empty (the reported bug). Returns the destination for the
        notification ('clipboard' on native success, 'terminal (OSC52)' when only the escape path ran)."""
        import shutil
        import subprocess
        import sys

        self.copy_to_clipboard(text)  # OSC 52: remote/SSH + terminals that permit clipboard writes
        argvs = ([["pbcopy"]] if sys.platform == "darwin" else
                 [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]])
        for argv in argvs:
            if shutil.which(argv[0]):
                try:
                    subprocess.run(argv, input=text.encode(), check=True, timeout=5)
                    return "clipboard"
                except (subprocess.SubprocessError, OSError):
                    continue
        return "terminal (OSC52)"

    def action_smart_copy(self) -> None:
        editor = self.query_one("#editor", TextArea)
        text = editor.selected_text
        source = "selection" if text else ""
        if not text:
            text = self._terminal_selection()
            source = "terminal selection" if text else ""
        if not text:  # no editor selection → any screen-level selection, else the whole file
            get_sel = getattr(self.screen, "get_selected_text", None)
            text = (get_sel() if callable(get_sel) else "") or self._editor_state[0]
            source = "selection" if text != self._editor_state[0] else "file"
        if text.strip():
            dest = self._clipboard_copy(text)
            self.notify(f"Copied {source} → {dest} — {len(text)} chars")
        else:
            self.notify("Nothing to copy", severity="warning")

    def _terminal_selection(self) -> str:
        try:
            focused_widget = self.focused
        except ScreenStackError:
            focused_widget = None
        focused = focused_widget if isinstance(focused_widget, RichLog) else None
        if _MAIN_STREAM not in self._terminal_logs:
            self._terminal_log(_MAIN_STREAM, "terminal")
        terminals = ([focused] if focused else []) + [
            terminal for terminal in self._terminal_logs.values() if terminal is not focused
        ]
        for terminal in terminals:
            selection = terminal.text_selection
            if selection is None:
                continue
            extracted = terminal.get_selection(selection)
            if extracted:
                return extracted[0]
        return ""

    def action_copy_file(self) -> None:
        content = self._editor_state[0]
        if content.strip():
            dest = self._clipboard_copy(content)
            self.notify(f"Copied file → {dest} — {len(content.splitlines())} lines")
        else:
            self.notify("Nothing to copy", severity="warning")

    def action_copy_prompt(self) -> None:
        cell = self._tree_model.cell(self._selected_key) if self._selected_key else None
        if cell and cell.prompt:
            dest = self._clipboard_copy(cell.prompt)
            self.notify(f"Copied prompt → {dest}")
        else:
            self.notify("No prompt for this selection", severity="warning")
