"""Rich renderables for the IDE chrome (header, metric chips, summaries) — UI-framework-light."""

from __future__ import annotations

from rich.console import Group as RGroup
from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

from .events import CellStatus
from .model import Cell, ExperimentTree

# file extension → TextArea (tree-sitter) language; TS/JSX fall back to javascript; unknowns → None
_LANG = {
    ".py": "python", ".pyi": "python", ".json": "json", ".md": "markdown", ".txt": "markdown",
    ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".js": "javascript", ".jsx": "javascript",
    ".ts": "javascript", ".tsx": "javascript", ".html": "html", ".css": "css", ".sh": "bash",
    ".sql": "sql", ".rs": "rust", ".go": "go", ".java": "java",
}


def language_for(path: str) -> str | None:
    for ext, lang in _LANG.items():
        if path.endswith(ext):
            return lang
    return None


def status_label(status: CellStatus, text: str) -> Text:
    """A glyph + text coloured by status (used in the tree and lists)."""

    return Text.assemble((f"{status.glyph} ", status.color), (text, status.color if status.terminal else "default"))


def cell_header(cell: Cell) -> RenderableType:
    """Styled two-line header for the selected cell: status chip + identity, then metric chips."""

    line = Text()
    line.append(f" {cell.status.glyph} ", style=f"bold white on {cell.status.color}")
    line.append(f"  {cell.ref.name}", style="bold")
    line.append(f"   {cell.harness_label}", style="cyan")
    if cell.started_at:  # wall-clock start (→ end), so a long-running / paused cell is legible
        stamp = cell.started_at + (f"→{cell.finished_at}" if cell.finished_at else " …")
        line.append(f"   {stamp}", style="grey50")
    if cell.duration_ms:
        line.append(f"   {cell.duration_ms} ms", style="grey50")
    chips = Text()
    for key, value in cell.detail.items():
        chips.append(f" {key} ", style="grey70 on grey23")
        chips.append(f" {value}  ", style="bold")
    return RGroup(line, chips) if cell.detail else line


def group_header(name: str, status: CellStatus, n: int) -> RenderableType:
    line = Text()
    line.append(f" {status.glyph} ", style=f"bold white on {status.color}")
    line.append(f"  {name}", style="bold")
    line.append(f"   {n} harnesses", style="grey50")
    return line


def summary_table(tree: ExperimentTree) -> RenderableType:
    """The right-pane per-harness roll-up of pass/fail/error/skip."""

    table = Table.grid(padding=(0, 1))
    table.add_column(style="bold")
    for color in ("green", "red", "dark_orange", "grey50"):
        table.add_column(justify="right", style=color)
    table.add_row(Text("harness", style="grey62"), "✓", "✗", "⚠", "–")
    for hid, label in tree.harnesses:
        cells = [c for g in tree.groups for c in g.cells if c.ref.harness_id == hid]

        def n(status: CellStatus, cells=cells) -> str:
            count = sum(1 for c in cells if c.status is status)
            return str(count) if count else "·"

        table.add_row(
            Text(label),
            n(CellStatus.PASS), n(CellStatus.FAIL), n(CellStatus.ERROR), n(CellStatus.SKIP),
        )
    return table
