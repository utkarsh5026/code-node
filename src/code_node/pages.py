"""
One page, made from scratch: read the folder, follow the code from the entry point, draw it. The command saves it
once, and the server makes it again on every change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .analysis.graph import code_graph
from .analysis.mapping import entry_file, map_code
from .analysis.model import CodeMap
from .deploys import find_deployment
from .project import EntryPoint, Project, read_project
from .report.build import page_blocks
from .report.editor import editor_link
from .report.style import render_page

GRAPH_FUNCTIONS = 24  # functions the graph draws by default, the ones that lead to the most code first

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
    editor: str = "vscode"  # --editor: the editor its line links open ('vscode', 'cursor'; 'none' for no links)

    @property
    def limits(self) -> tuple[int, int]:
        """
        (functions, depth) the graph draws.
        """
        return (_ALL, _ALL) if self.draw_all else (self.functions, self.depth)


def map_entry(root: Path, entry: EntryPoint, options: PageOptions) -> tuple[CodeMap, Project]:
    """
    The folder read as it is now, and the code followed from the entry point: the CodeMap, and the folder.
    """
    project = read_project(root)
    file = entry.file or (entry_file(entry.name, project.files) or ("",))[0]
    deployment = find_deployment(project.deploy_files, project.files, file, entry.name.rsplit(".", 1)[-1])
    cmap = map_code(project.files, entry.name, libraries=project.libraries(), file=entry.file or None,
                    max_depth=_ALL_READ_DEPTH if options.draw_all else None,
                    platform=options.platform or entry.platform, deployment=deployment)
    return cmap, project


def make_page(root: Path, entry: EntryPoint, options: PageOptions) -> tuple[str, CodeMap]:
    """
    The whole HTML page for an entry point, and the CodeMap it was drawn from.
    """
    cmap, project = map_entry(root, entry, options)
    max_functions, max_depth = options.limits
    blocks = page_blocks(cmap, project=project.root.name, max_functions=max_functions, max_depth=max_depth,
                         sources=project.files, editor=editor_link(options.editor, str(project.root),
                                                                   os.environ.get("WSL_DISTRO_NAME", "")))
    return render_page(blocks, f"How {entry.name} works"), cmap


def make_mermaid(root: Path, entry: EntryPoint, options: PageOptions) -> str:
    """
    The graph as Mermaid.
    """
    cmap, _ = map_entry(root, entry, options)
    max_functions, max_depth = options.limits
    return code_graph(cmap, max_functions=max_functions, max_depth=max_depth).mermaid()
