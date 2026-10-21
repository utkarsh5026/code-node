"""
The examples in examples/, end to end: each page as text against tests/snapshots/ (so a change to what a page says
shows as a readable diff), every entry point read to the end, and each page whole and self-contained.
"""

from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from code_node.cli import main
from code_node.project import entry_points, read_project

from support import EXAMPLES, SNAPSHOTS


SNAPSHOT = SNAPSHOTS / "orders-service.txt"


def test_the_example_page_matches_its_snapshot(monkeypatch) -> None:
    """
    The example's page as text, against tests/snapshots/orders-service.txt, so a change to what the page says shows
    as a readable diff. UPDATE_SNAPSHOTS=1 uv run pytest writes it anew.
    """
    from code_node.kit.render import _render_text
    from code_node.pages import PageOptions, map_entry
    from code_node.report.build import page_blocks

    root = EXAMPLES / "orders-service"
    entry = entry_points(read_project(root))[0]
    cmap, project = map_entry(root, entry, PageOptions(git=False))
    text = (
        _render_text(page_blocks(cmap, project=root.name, max_functions=24, max_depth=5, sources=project.files), 100)
        + "\n"
    )
    if os.environ.get("UPDATE_SNAPSHOTS"):
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(text)
    # code is shown as ast.unparse writes it, whose quotes differ between Pythons (f'{a['b']}' from 3.12 only)
    assert text.replace("'", '"') == SNAPSHOT.read_text().replace("'", '"')


def _matches_snapshot(example: str) -> None:
    """
    An example's page as text, then its findings, against tests/snapshots/<example>.txt.
    UPDATE_SNAPSHOTS=1 uv run pytest writes it anew.
    """
    from code_node.analysis.findings import code_map_findings
    from code_node.kit.render import _render_text
    from code_node.pages import PageOptions, map_entry
    from code_node.report.build import page_blocks

    root = EXAMPLES / example
    snapshot = SNAPSHOTS / f"{example}.txt"
    entry = entry_points(read_project(root))[0]
    cmap, project = map_entry(root, entry, PageOptions(git=False))
    text = _render_text(page_blocks(cmap, project=root.name, max_functions=24, max_depth=5, sources=project.files), 100)
    text += "\n\n-- Findings --\n" + "\n".join(f"{level}: {message}" for level, message in code_map_findings(cmap))
    text += "\n"
    if os.environ.get("UPDATE_SNAPSHOTS"):
        snapshot.write_text(text)
    assert text.replace("'", '"') == snapshot.read_text().replace("'", '"')


def test_the_cart_example_matches_its_snapshot() -> None:
    """
    The cart example, which every kind of plugin reads: its SAM template, Redis, PostgreSQL, OpenAI and boto3 on
    Lambda.
    """
    _matches_snapshot("cart-service")


def test_the_books_example_matches_its_snapshot() -> None:
    """
    The books example, a FastAPI app on the web platform: its routes' parameters are the request, followed into
    PostgreSQL, a shell command, S3 and an async route that blocks.
    """
    _matches_snapshot("books-api")


_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Tags(HTMLParser):
    """
    Each tag the page opens, closed in order: what a browser would otherwise guess at.
    """

    def __init__(self) -> None:
        super().__init__()
        self.open: list[str] = []
        self.wrong: list[tuple[str, tuple[int, int]]] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag not in _VOID:
            self.open.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        if self.open and self.open[-1] == tag:
            self.open.pop()
        else:
            self.wrong.append((tag, self.getpos()))


EXAMPLE_NAMES = sorted(p.name for p in EXAMPLES.iterdir() if p.is_dir())


@pytest.mark.parametrize("example", EXAMPLE_NAMES)
def test_every_entry_point_of_each_example_is_read_to_the_end(example: str) -> None:
    from code_node.pages import PageOptions, map_entry

    root = EXAMPLES / example
    found = entry_points(read_project(root))
    assert found
    for entry in found:
        cmap, _ = map_entry(root, entry, PageOptions(git=False))
        assert not cmap.limited and not cmap.note, (entry.name, cmap.limited, cmap.note)
        assert cmap.functions


@pytest.mark.parametrize("example", EXAMPLE_NAMES)
def test_each_example_s_page_is_whole_and_self_contained(example: str) -> None:
    from code_node.pages import PageOptions, make_page

    root = EXAMPLES / example
    page, _ = make_page(root, entry_points(read_project(root))[0], PageOptions(git=False))
    tags = _Tags()
    tags.feed(page)
    tags.close()
    assert tags.open == [] and tags.wrong == []
    # one file, opened anywhere: no script, style or image fetched from elsewhere
    assert not re.search(r'<(script|img|iframe)[^>]* src=|<link[^>]* rel="stylesheet"', page)
    assert page.count("<script>") == 1  # the graph's; the page works without it
    assert "EventSource" not in page  # the live script is only for --serve


SMOKE = {
    "orders-service": "orders.handler.lambda_handler",
    "cart-service": "Deployed as CheckoutFunction in template.yaml",
    "books-api": "books.main.app",
}


@pytest.mark.parametrize(("example", "said"), sorted(SMOKE.items()))
def test_the_command_on_each_example(example: str, said: str, tmp_path: Path, capsys) -> None:
    out = tmp_path / "page.html"
    assert main([str(EXAMPLES / example), "--no-open", "--no-git", "-o", str(out)]) == 0
    assert said in capsys.readouterr().out and out.stat().st_size > 10_000
    assert main([str(EXAMPLES / example), "--mermaid", "--no-git"]) == 0
    assert capsys.readouterr().out.startswith("flowchart LR")


def test_every_example_has_a_smoke_test() -> None:
    assert sorted(SMOKE) == EXAMPLE_NAMES
