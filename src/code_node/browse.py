"""
The interactive picker, drawn with rich: walk the folder with the arrow keys, type to search every file in it, and pick
the function to start from. `code-node -i` opens it on the files; wherever else the command asks which entry point,
it opens on the ones found, with the files a Tab away. Nothing in it runs the code: it reads the trees `Project` has.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from rich import box
from rich.console import Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from .project import EntryPoint, Project, entries_in_file, entry_points
from .terminal import console, keys

FILES, ENTRIES, FUNCTIONS = "files", "entries", "functions"  # what the picker lists: a folder, the entry points found,
# or the functions to start from in one file (or that match what was typed with -e)

_RESULTS = 300  # search results listed at most

_CHROME = 8  # lines that aren't the list: the frame, the tabs, where it is, the search, two rules and the keys

_PREVIEW_WIDTH = 110  # a terminal this wide shows what's under the cursor beside the list

_QUIT = EntryPoint("", "", "", 0)  # what pressing Esc or Ctrl-C picks: nothing

_HIT = "bold yellow underline"  # the characters of a name that match what's typed

_FUNCTION = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass
class _Row:
    """
    One line of the list: a folder, a file or a function to start from.
    """

    kind: str  # 'up', 'folder', 'file' or 'entry'
    key: str  # the folder or file, from the project's root; an entry point's name
    label: Text
    note: Text = field(default_factory=Text)
    entry: EntryPoint | None = None


def _match(query: str, text: str) -> tuple[int, list[int]] | None:
    """
    How well text matches what's typed, lower being better, and which of its characters do: the file's own name
    first, then anywhere in its path, then its letters in order ('ordhan' finds orders/handler.py). None when it
    doesn't match at all.
    """
    needle, hay = query.lower().replace(" ", ""), text.lower()
    if not needle:
        return 0, []
    name = hay.rstrip("/").rfind("/") + 1
    found = hay.find(needle, name)
    if found >= 0:
        return (0 if found == name else 1), list(range(found, found + len(needle)))
    found = hay.find(needle)
    if found >= 0:
        return 2, list(range(found, found + len(needle)))
    at, spots = 0, []
    for char in needle:
        at = hay.find(char, at)
        if at < 0:
            return None
        spots.append(at)
        at += 1
    return 3, spots


def _lit(text: str, spots: list[int], style: str = "") -> Text:
    """
    The text, with the characters at spots lit.
    """
    out = Text(text, style=style)
    for spot in spots:
        out.stylize(_HIT, spot, spot + 1)
    return out


class _Tree:
    """
    The folders that hold the project's Python files: each one's folders and files, and how many files are under it.
    """

    def __init__(self, files: list[str]) -> None:
        self.folders: dict[str, list[str]] = {"": []}
        self.files: dict[str, list[str]] = {"": []}
        self.counts: dict[str, int] = {"": 0}
        for rel in sorted(files):
            folder = ""
            self.counts[""] += 1
            for part in rel.split("/")[:-1]:
                child = f"{folder}/{part}" if folder else part
                if child not in self.folders:
                    self.folders[child], self.files[child], self.counts[child] = [], [], 0
                    self.folders[folder].append(child)
                self.counts[child] += 1
                folder = child
            self.files[folder].append(rel)
        for children in self.folders.values():
            children.sort(key=str.lower)
        for names in self.files.values():
            names.sort(key=lambda rel: rel.lower())


def _parent(folder: str) -> str:
    return folder.rsplit("/", 1)[0] if "/" in folder else ""


def _name(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1]


class _Picker:
    """
    What the picker shows and where its cursor is; `press` moves it, and gives back the entry point picked.
    """

    def __init__(
        self,
        project: Project,
        found: list[EntryPoint],
        *,
        mode: str,
        folder: str = "",
        file: str = "",
        choices: list[EntryPoint] | None = None,
        title: str = "",
    ) -> None:
        self.project = project
        self.found = found
        self.starts = {entry.name for entry in found}
        self.by_file: dict[str, list[EntryPoint]] = {}
        for entry in found:
            self.by_file.setdefault(entry.file, []).append(entry)
        self.tree = _Tree(list(project.files))
        self.under = {  # entry points found in each folder, however deep
            folder: sum(len(entries) for rel, entries in self.by_file.items() if rel.startswith(f"{folder}/"))
            for folder in self.tree.folders
        }
        self.mode, self.file, self.title = mode, file, title
        self.folder = folder if folder in self.tree.folders else ""
        self.choices = choices or []
        self.query = ""
        self.cursor = self.top = 0
        self.room = 10  # rows the list has room for, as last drawn
        self.said = ""  # a line for the key bar, until the next key

    # what's listed

    def rows(self) -> list[_Row]:
        if self.mode == ENTRIES:
            return self._entry_rows(self.found, where=True)
        if self.mode == FUNCTIONS:
            return self._entry_rows(self.choices, where=not self.file)
        return self._search_rows() if self.query else self._folder_rows()

    def _folder_rows(self) -> list[_Row]:
        rows = []
        if self.folder:
            rows.append(_Row("up", _parent(self.folder), Text("..", style="bold blue"), Text("up a folder", "dim")))
        for child in self.tree.folders[self.folder]:
            rows.append(_Row("folder", child, Text(f"{_name(child)}/", style="bold blue"), self._folder_note(child)))
        for rel in self.tree.files[self.folder]:
            rows.append(
                _Row("file", rel, Text(_name(rel), style="bold" if rel in self.by_file else ""), self._note(rel))
            )
        return rows

    def _search_rows(self) -> list[_Row]:
        scored = []
        for folder in self.tree.folders:
            matched = _match(self.query, f"{folder}/") if folder else None
            if matched is not None:
                scored.append((matched[0], 1, len(folder), folder, "folder", matched[1]))
        for rel in self.project.files:
            matched = _match(self.query, rel)
            if matched is not None:
                scored.append((matched[0], 0 if rel in self.by_file else 1, len(rel), rel, "file", matched[1]))
        rows = []
        for _, _, _, path, kind, spots in sorted(scored)[:_RESULTS]:
            if kind == "folder":
                rows.append(_Row(kind, path, _lit(f"{path}/", spots, "bold blue"), self._folder_note(path)))
            else:
                rows.append(
                    _Row(kind, path, _lit(path, spots, "bold" if path in self.by_file else ""), self._note(path))
                )
        return rows

    def _entry_rows(self, entries: list[EntryPoint], *, where: bool) -> list[_Row]:
        scored = []
        for order, entry in enumerate(entries):
            matched = _match(self.query, entry.name) or (
                (4, []) if _match(self.query, f"{entry.file} {entry.why}") else None
            )
            if matched is not None:
                scored.append((matched[0] if self.query else 0, order, entry, matched[1]))
        rows = []
        for _, _, entry, spots in sorted(scored, key=lambda item: item[:2]):
            name = _lit(entry.name, spots)
            module = self.project.modules.get(entry.file, "")
            if module and entry.name.startswith(f"{module}."):
                name.stylize("dim", 0, len(module) + 1)
            star = Text("★ " if entry.name in self.starts else "  ", style="yellow")
            place = f"{entry.file}:{entry.line}" if where else f":{entry.line}"
            note = Text.assemble((entry.why, "dim"), "  ", (place if entry.line else entry.file, "cyan"))
            rows.append(_Row("entry", entry.name, Text.assemble(star, name), note, entry))
        return rows

    def _note(self, rel: str) -> Text:
        entries = self.by_file.get(rel, [])
        if not entries:
            return Text()
        said = entries[0].why if len(entries) == 1 else f"{len(entries)} entry points"
        return Text.assemble(("★ ", "yellow"), (said, "yellow"))

    def _folder_note(self, folder: str) -> Text:
        count = self.tree.counts[folder]
        note = Text(f"{count} file{'s' if count != 1 else ''}", style="dim")
        if self.under[folder]:
            note.append(f"  ★ {self.under[folder]}", style="yellow")
        return note

    # keys

    def press(self, key: str) -> EntryPoint | None:
        """
        Does what the key does: the entry point picked, _QUIT, or None to keep going.
        """
        self.said = ""
        rows = self.rows()
        row = rows[min(self.cursor, len(rows) - 1)] if rows else None
        last = max(len(rows) - 1, 0)
        if key == "ctrl-c":
            return _QUIT
        if key == "up":
            self.cursor = self.cursor - 1 if self.cursor > 0 else last
        elif key == "down":
            self.cursor = self.cursor + 1 if self.cursor < last else 0
        elif key == "pageup":
            self.cursor = max(self.cursor - self.room, 0)
        elif key == "pagedown":
            self.cursor = min(self.cursor + self.room, last)
        elif key == "home":
            self.cursor = 0
        elif key == "end":
            self.cursor = last
        elif key in ("enter", "right"):
            return self._open(row) if row is not None else None
        elif key == "left":
            self._back()
        elif key == "backspace":
            if self.query:
                self._search(self.query[:-1])
            else:
                self._back()
        elif key == "esc":
            if self.query:
                self._search("")
            elif self.mode == FUNCTIONS:
                self._back()
            else:
                return _QUIT
        elif key in ("tab", "shift-tab"):
            self._switch(FILES if self.mode == ENTRIES else ENTRIES)
        elif len(key) == 1 and key.isprintable():
            self._search(self.query + key)
        return None

    def _search(self, query: str) -> None:
        self.query, self.cursor, self.top = query, 0, 0

    def _open(self, row: _Row) -> EntryPoint | None:
        if row.kind == "entry":
            return row.entry
        if row.kind in ("up", "folder"):
            self._go(row.key, self.folder if row.kind == "up" else "")
            return None
        choices = entries_in_file(self.project, row.key)
        if not choices:
            self.said = f"{_name(row.key)} has no functions to start from"
            return None
        if len(choices) == 1:
            return choices[0]
        self.mode, self.file, self.choices, self.title = FUNCTIONS, row.key, choices, ""
        self._search("")
        return None

    def _back(self) -> None:
        if self.mode == FUNCTIONS:
            self.mode = FILES
            self._go(_parent(self.file) if self.file else self.folder, self.file)
        elif self.mode == FILES and not self.query and self.folder:
            self._go(_parent(self.folder), self.folder)

    def _go(self, folder: str, select: str = "") -> None:
        """
        Lists a folder, the cursor on select (the folder just left, going up) when it's there.
        """
        self.folder = folder
        self._search("")
        rows = self.rows()
        first = 1 if folder and len(rows) > 1 else 0  # past '..'
        self.cursor = next((i for i, row in enumerate(rows) if select and row.key == select), first)

    def _switch(self, mode: str) -> None:
        self.mode = mode
        self._search("")

    # drawing

    def draw(self, width: int, height: int) -> RenderableType:
        rows = self.rows()
        self.room = max(height - _CHROME, 3)
        self.cursor = min(self.cursor, max(len(rows) - 1, 0))
        if self.cursor < self.top:
            self.top = self.cursor
        if self.cursor >= self.top + self.room:
            self.top = self.cursor - self.room + 1
        self.top = max(0, min(self.top, max(len(rows) - self.room, 0)))
        beside = width >= _PREVIEW_WIDTH
        listed = self._list(rows, width * 3 // 5 if beside else width)
        if beside:
            row = rows[self.cursor] if rows else None
            beside = Table.grid(expand=True, padding=(0, 1))
            beside.add_column(ratio=3)
            beside.add_column(ratio=2)
            beside.add_row(listed, self._preview(row, self.room))
            listed = beside
        parts = [self._tabs(), self._where(), self._search_line(len(rows)), Rule(style="dim"), listed]
        parts += [Rule(style="dim"), self._keys()]
        return Panel(
            Group(*parts),
            title=Text(" code-node ", style="bold"),
            title_align="left",
            subtitle=Text(f" {self.project.root} ", style="dim"),
            subtitle_align="right",
            box=box.ROUNDED,
            border_style="cyan",
            height=height,
        )

    def _list(self, rows: list[_Row], width: int) -> RenderableType:
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(width=1, no_wrap=True)
        table.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
        table.add_column(justify="right", no_wrap=True, overflow="ellipsis", max_width=max(width // 2, 20))
        shown = rows[self.top : self.top + self.room]
        for at, row in enumerate(shown, self.top):
            here = at == self.cursor
            table.add_row(
                Text("›" if here else " ", style="bold cyan"), row.label, row.note, style="reverse" if here else ""
            )
        if not rows:
            table.add_row("", Text(self._nothing(), style="dim italic"), "")
        for _ in range(self.room - max(len(shown), 1)):
            table.add_row("", "", "")
        return table

    def _nothing(self) -> str:
        if self.query:
            return f"Nothing matches {self.query!r}: Backspace or Esc to clear it"
        if self.mode == ENTRIES:
            return "No entry points found here: press Tab to pick a file"
        return "Nothing here"

    def _tabs(self) -> Text:
        tabs = Text()
        for mode, label in ((FILES, "Files"), (ENTRIES, f"Entry points {len(self.found)}")):
            on = self.mode == mode or (mode == FILES and self.mode == FUNCTIONS)
            tabs.append(f" {label} ", style="bold reverse cyan" if on else "dim")
            tabs.append("  ")
        return tabs

    def _where(self) -> Text:
        where = Text(self.project.root.name, style="bold")
        if self.mode == ENTRIES:
            return where.append("  where the code starts, best first", style="dim")
        if self.mode == FUNCTIONS and not self.file:
            return where.append(f"  {self.title}", style="dim")
        path = self.file if self.mode == FUNCTIONS else self.folder
        for part in path.split("/") if path else []:
            where.append(" / ", style="dim").append(part, style="bold blue" if not part.endswith(".py") else "bold")
        if self.mode == FUNCTIONS:
            where.append("  pick a function to start from", style="dim")
        return where

    def _search_line(self, count: int) -> Table:
        line = Table.grid(expand=True)
        line.add_column(ratio=1, no_wrap=True)
        line.add_column(justify="right", no_wrap=True)
        typed = Text("Search ", style="bold cyan")
        if self.query:
            typed.append(self.query).append("▏", style="blink cyan")
        else:
            hint = "type to search every file" if self.mode == FILES else "type to filter"
            typed.append("▏", style="blink cyan").append(hint, style="dim")
        place = f"{self.cursor + 1} of {count}" if count else "0"
        line.add_row(typed, Text(place, style="dim"))
        return line

    def _keys(self) -> Text:
        if self.said:
            return Text(self.said, style="yellow")
        pairs = {
            FILES: [("↑↓", "move"), ("→ Enter", "open"), ("←", "up"), ("Tab", "entry points"), ("Esc", "quit")],
            ENTRIES: [("↑↓", "move"), ("Enter", "start here"), ("Tab", "files"), ("Esc", "quit")],
            FUNCTIONS: [("↑↓", "move"), ("Enter", "start here"), ("← Esc", "back"), ("Tab", "entry points")],
        }[self.mode]
        bar = Text()
        for key, does in pairs:
            bar.append(key, style="bold").append(f" {does}   ", style="dim")
        return bar

    def _preview(self, row: _Row | None, height: int) -> RenderableType:
        title, body = "", Text("Pick a folder, a file or a function", style="dim")
        if row is not None and row.kind == "entry" and row.entry is not None:
            title, body = self._code(row.entry, height - 2)
        elif row is not None and row.kind == "file":
            title, body = row.key, self._outline(row.key)
        elif row is not None and row.kind in ("folder", "up"):
            title, body = (row.key or self.project.root.name) + "/", self._inside(row.key)
        return Panel(
            body,
            title=Text(title, style="bold"),
            title_align="left",
            height=height,
            border_style="dim",
            box=box.ROUNDED,
        )

    def _code(self, entry: EntryPoint, lines: int) -> tuple[str, RenderableType]:
        source = self.project.files.get(entry.file)
        if source is None:
            return entry.name, Text(entry.why, style="dim")
        start = max(entry.line, 1)
        code = "\n".join(source.splitlines()[start - 1 : start - 1 + lines])
        syntax = Syntax(
            code, "python", line_numbers=True, start_line=start, theme="ansi_dark", background_color="default"
        )
        return f"{entry.file}:{start}", syntax

    def _outline(self, rel: str) -> RenderableType:
        tree = self.project.trees.get(rel)
        if tree is None:
            return Text("This file doesn't parse, so it can't be read", style="yellow")
        module = self.project.modules.get(rel, "")
        table = Table.grid(padding=(0, 1))
        table.add_column(width=1)
        table.add_column(no_wrap=True, overflow="ellipsis")
        table.add_column(justify="right", style="dim")
        table.add_row("", Text(module, style="dim"), "")
        for node in tree.body:
            if isinstance(node, _FUNCTION):
                self._outline_row(table, f"{module}.{node.name}", f"{node.name}()", node.lineno)
            elif isinstance(node, ast.ClassDef):
                table.add_row("", Text(f"class {node.name}", style="bold magenta"), str(node.lineno))
                for method in (m for m in node.body if isinstance(m, _FUNCTION)):
                    self._outline_row(table, f"{module}.{node.name}.{method.name}", f"  {method.name}()", method.lineno)
        if table.row_count == 1:
            table.add_row("", Text("No functions: code-node starts from one", style="dim"), "")
        return table

    def _outline_row(self, table: Table, name: str, label: str, line: int) -> None:
        start = name in self.starts
        table.add_row(Text("★" if start else "", style="yellow"), Text(label, style="bold" if start else ""), str(line))

    def _inside(self, folder: str) -> RenderableType:
        count = self.tree.counts[folder]
        lines = [Text(f"{count} Python file{'s' if count != 1 else ''}", style="dim")]
        starts = [e for e in self.found if not folder or e.file.startswith(f"{folder}/")]
        if starts:
            lines.append(Text(f"{len(starts)} entry point{'s' if len(starts) != 1 else ''}:", style="dim"))
            for entry in starts:
                line = Text.assemble(("★ ", "yellow"), entry.name, (f"  {entry.why}", "dim"))
                line.no_wrap, line.overflow = True, "ellipsis"
                lines.append(line)
        return Group(*lines)

    def run(self) -> EntryPoint | None:
        """
        Draws the picker full screen until something is picked (or Esc / Ctrl-C picks nothing).
        """
        with keys() as read, Live(console=console, screen=True, auto_refresh=False, transient=True) as live:
            while True:
                live.update(self.draw(*console.size), refresh=True)
                try:
                    picked = self.press(read())
                except KeyboardInterrupt:
                    picked = _QUIT
                if picked is not None:
                    return None if picked is _QUIT else picked


def browse(
    project: Project,
    *,
    mode: str = FILES,
    found: list[EntryPoint] | None = None,
    folder: str = "",
    file: str = "",
    choices: list[EntryPoint] | None = None,
    title: str = "",
) -> EntryPoint | None:
    """
    The entry point picked in the picker, or None when nothing was. It opens on mode: FILES in folder, ENTRIES (the
    entry points found), or FUNCTIONS (the choices, in file or under title).
    """
    if found is None:
        with console.status("Looking for entry points…"):
            found = entry_points(project)
    picked = _Picker(project, found, mode=mode, folder=folder, file=file, choices=choices, title=title).run()
    if picked is None:
        console.print("Nothing picked.", style="dim")
    return picked
