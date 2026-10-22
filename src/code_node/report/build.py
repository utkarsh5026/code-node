"""
The page code-node draws for one entry point: tabs for the graph, the decisions it makes and the walk through its
steps.
"""

from __future__ import annotations

from typing import Any

from ..kit.blocks import _Note, _Text
from ..kit.fmt import _plural

from ..analysis.findings import _listed, _short_name
from ..analysis.graph import CodeGraph, code_graph, everything_graph, graph_views
from ..analysis.model import CodeMap
from .flow import _Flow, flow_entries
from .graph import _Graph
from .tabs import _Tabs
from .walk import _Walk, walk_stops


def _closing_note(cmap: CodeMap, graph: CodeGraph) -> str:
    said = [
        "It reads the code with Python's ast module and runs none of it. It follows calls into the folder's own "
        "functions and the boto3 clients it makes; calls through a value handed in from elsewhere, or made inside "
        "a library, aren't followed, so there may be more than it lists."
    ]
    fn = cmap.function
    if fn is not None and getattr(fn, "source", ""):
        said.append(
            f"Where it runs comes from {fn.name} in {fn.source}: its environment variables, timeout and "
            "what its role allows are checked against the code."
        )
    services = list(dict.fromkeys(call.service for call in cmap.library_calls))
    if services:
        said.append(f"Calls to {_listed(services, 4)} are read by code-node's library plugins.")
    if graph.hidden:
        said.append(
            f"The graph leaves out {_plural(graph.hidden, 'function')} to stay readable: a box's line of calls not "
            "drawn opens them, and --all draws every one."
        )
    if cmap.other_files:
        said.append(
            f"{_plural(cmap.other_files, 'other Python file')} in the folder "
            f"{'is' if cmap.other_files == 1 else 'are'}n't imported from here, so they're left out."
        )
    if cmap.unreached:
        said.append(
            f"{_plural(cmap.unreached, 'function')} in the files it read never "
            f"run{'s' if cmap.unreached == 1 else ''} from {_short_name(cmap.entry or '')}()."
        )
    if cmap.limited:
        said.append(f"To keep it short, it {cmap.limited}.")
    return " ".join(said)


def page_blocks(
    cmap: CodeMap,
    *,
    project: str,
    max_functions: int,
    max_depth: int,
    sources: dict[str, str] | None = None,
    editor: str = "",
) -> list[Any]:
    """
    The whole page for one entry point, as report blocks: tabs for the graph, its decisions and the walk through its steps, with the
    entry point and the folder beside them. sources is the code read, {file: its text}: with it, a box of the graph
    clicked shows its code. editor is a link from editor_link(), to open the code at a line in an editor.
    """
    if cmap.note:
        return [_Note(cmap.note)]
    blocks: list[Any] = []
    if cmap.entry is None and cmap.handlers:
        blocks.append(
            _Note(
                f"{cmap.handler} isn't a function in {cmap.handler_file}. Its functions that look like "
                f"entry points: {', '.join(cmap.handlers)}."
            )
        )
    graph = code_graph(cmap, max_functions=max_functions, max_depth=max_depth)
    entry = _short_name(cmap.entry) if cmap.entry else None
    walk = _Walk(
        cmap.startup,
        cmap.steps,
        f"What each call does, step by step from {entry}()" if entry else "What each call does",
        calls_title=f"Each call, from {entry}()" if entry else "Each call",
        functions=cmap.functions,
        sources=sources or {},
        editor=editor,
    )
    tabs: list[tuple[str, str, list[Any]]] = []
    if graph.nodes:
        tabs.append(
            (
                "Graph",
                f"{len(graph.nodes)} box{'' if len(graph.nodes) == 1 else 'es'}",
                [
                    _Graph(
                        graph,
                        "How it fits together: what comes in, who calls whom, and what it reaches",
                        sources=sources or {},
                        editor=editor,
                        views=graph_views(cmap, graph, max_functions=max_functions, max_depth=max_depth),
                        everything=everything_graph(cmap, graph),
                    ),
                    _Text(
                        graph.mermaid(),
                        code=True,
                        collapsed=True,
                        title=("The same graph in Mermaid, to paste in a Markdown file, a wiki or a pull request"),
                    ),
                ],
            )
        )
    event = next((n for n in graph.nodes if n.kind == "event"), None)
    routes = any(route for _, route in flow_entries(cmap.steps))  # a web app: a flow for each route
    flow = _Flow(
        cmap.steps,
        f"How {'each route' if routes else f'{entry}()'} decides what to do: each question it asks, and where each "
        "answer goes"
        if entry
        else "",
        comes_in=(event.label, event.sub) if event else ("", ""),
    )
    decisions = sum(
        1 for top in cmap.steps for s in top.walk() if s.kind in ("if", "try") and not s.code.startswith("case ")
    )
    tabs.append(("Decisions", _plural(decisions, "decision"), [flow]))
    tabs.append(("Step by step", _plural(len(walk_stops(walk)), "step"), [walk]))
    read = f"{_plural(cmap.files, 'file')}, {cmap.lines:,} lines, nothing run" if cmap.files else ""
    blocks.append(
        _Tabs(
            tabs, caption=cmap.handler, about=" · ".join(filter(None, [project, read])), foot=_closing_note(cmap, graph)
        )
    )
    return blocks
