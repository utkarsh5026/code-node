"""
One page, made from scratch: read the folder, follow the code from the entry point, draw it. The command saves it
once, and the server makes it again on every change.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .analysis.graph import code_graph
from .analysis.mapping import map_code
from .analysis.model import CodeMap
from .project import EntryPoint, read_project
from .report.build import page_blocks
from .report.style import render_page

GRAPH_FUNCTIONS = 24  # functions the graph draws by default, the nearest first

GRAPH_DEPTH = 5  # ...and how many calls deep

_ALL = 10_000  # --all: no limit that a real codebase reaches

_ALL_READ_DEPTH = 40  # --all: calls followed from the entry point


@dataclass
class PageOptions:
    """
    How much of the code the page draws, and which platform's checks it runs.
    """

    draw_all: bool = False
    functions: int = GRAPH_FUNCTIONS
    depth: int = GRAPH_DEPTH
    platform: str = ""  # --platform: its checks run whatever the entry point is ('' leaves it to the entry point)

    @property
    def limits(self) -> tuple[int, int]:
        """
        (functions, depth) the graph draws.
        """
        return (_ALL, _ALL) if self.draw_all else (self.functions, self.depth)


def map_entry(root: Path, entry: EntryPoint, options: PageOptions) -> tuple[CodeMap, str]:
    """
    The folder read as it is now, and the code followed from the entry point: the CodeMap, and the folder's name.
    """
    project = read_project(root)
    cmap = map_code(project.files, entry.name, libraries=project.libraries(), file=entry.file or None,
                    max_depth=_ALL_READ_DEPTH if options.draw_all else None,
                    platform=options.platform or entry.platform)
    return cmap, project.root.name


def make_page(root: Path, entry: EntryPoint, options: PageOptions) -> tuple[str, CodeMap]:
    """
    The whole HTML page for an entry point, and the CodeMap it was drawn from.
    """
    cmap, name = map_entry(root, entry, options)
    max_functions, max_depth = options.limits
    blocks = page_blocks(cmap, project=name, max_functions=max_functions, max_depth=max_depth)
    return render_page(blocks, f"How {entry.name} works"), cmap


def make_mermaid(root: Path, entry: EntryPoint, options: PageOptions) -> str:
    """
    The graph as Mermaid.
    """
    cmap, _ = map_entry(root, entry, options)
    max_functions, max_depth = options.limits
    return code_graph(cmap, max_functions=max_functions, max_depth=max_depth).mermaid()
