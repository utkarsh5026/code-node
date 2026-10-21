"""
The picker the command asks with: folders, search and keys.
"""

from __future__ import annotations

import io
from pathlib import Path

from code_node.cli import main
from code_node.project import entry_points, read_project

from support import PACKAGE, write


def test_the_picker_walks_folders_and_searches_files(tmp_path: Path) -> None:
    from rich.console import Console

    from code_node.browse import FILES, _match, _Picker

    project = read_project(write(tmp_path / "repo", PACKAGE))
    picker = _Picker(project, entry_points(project), mode=FILES)

    def keys(*pressed: str):
        picked = None
        for key in pressed:
            picked = picker.press(key)
        return picked

    def listed() -> list[str]:
        return [row.key for row in picker.rows()]

    assert listed() == ["src", "tests"] and keys("enter") is None and picker.folder == "src"
    assert listed() == ["", "src/tool"] and picker.cursor == 1  # past '..'
    assert keys("right") is None and listed()[1:] == ["src/tool/__init__.py", "src/tool/cli.py", "src/tool/store.py"]
    assert "★" in str(picker.rows()[2].note)  # cli.py holds the console script
    assert (
        keys("left") is None and picker.folder == "src" and listed()[picker.cursor] == "src/tool"
    )  # back where it was
    keys("s", "t", "o")  # typing searches every file
    assert listed()[0] == "src/tool/store.py" and keys("enter") is None and picker.mode == "functions"
    assert [row.key for row in picker.rows()] == ["tool.store.Store.save", "tool.store.Store._write"]
    assert keys("down", "enter").name == "tool.store.Store._write"
    assert keys("esc") is None and picker.mode == FILES and listed()[picker.cursor] == "src/tool/store.py"
    keys("backspace", "backspace", "tab")
    assert picker.mode == "entries" and keys("enter").name == "tool.cli.main"
    assert keys("tab", "c", "l", "i", "enter").name == "tool.cli.main"  # a file with one function picks it
    assert keys("esc", "esc").name == ""  # Esc clears what's typed, then quits
    assert _match("hdlr", "orders/handler.py") == (3, [7, 10, 11, 13]) and _match("zz", "a.py") is None
    assert _match("orders", "orders/orders.py")[0] == 0 and _match("ders", "orders/x.py")[0] == 2
    screen = Console(width=120, height=30, file=io.StringIO())
    with screen.capture() as seen:
        screen.print(picker.draw(120, 30))
    assert all(text in seen.get() for text in ("Search", "Entry points 1", "src/", "★ tool.cli.main", "3 Python files"))
    assert "repo /" not in seen.get()
    assert main([str(tmp_path / "repo"), "-i", "--no-open"]) == 2  # no terminal to pick in
