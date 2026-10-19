"""
The page code-node draws for one entry point: what it is in a few numbers, the findings, the graph,
and the walk through its steps (in tabs), and the tables of what it reaches.
"""

from __future__ import annotations

import json
from typing import Any

from ..kit.blocks import _Cards, _Findings, _Note, _Table, _Text, _Title, _Tone
from ..kit.fmt import _plural

from ..analysis.aws_model import _service_name
from ..analysis.findings import _short_name, _where, code_map_findings
from ..analysis.graph import CodeGraph, code_graph
from ..analysis.model import AwsCall, CodeMap, ImportUse
from ..platforms import get_platform
from .graph import _Graph
from .tabs import _Tabs
from .walk import _Walk, walk_stops

_IMPORT_ORDER = ("missing", "removed", "layer", "package", "runtime", "stdlib")

_IMPORT_WORDS = {"package": "an installed library", "runtime": "an installed library (AWS SDK)",
                 "stdlib": "Python's standard library"}


def _called_text(where: str) -> str:
    """
    'app.store.Orders.save line 16' -> 'Orders.save() line 16'.
    """
    key, _, line = where.rpartition(" line ")
    return f"{_short_name(key)}() line {line}" if key else where


def _import_rows(cmap: CodeMap) -> list[list[Any]]:
    """
    What it imports (its own modules left out), the ones that can't be found first.
    """
    found: dict[str, ImportUse] = {}
    for use in cmap.imports:
        if use.source == "own":
            continue
        known = found.get(use.top)
        if known is None or _IMPORT_ORDER.index(use.source) < _IMPORT_ORDER.index(known.source):
            found[use.top] = use
    rows = []
    for use in sorted(found.values(), key=lambda u: (_IMPORT_ORDER.index(u.source), u.top.lower())):
        if use.source in ("missing", "layer"):
            where: Any = _Tone("not found", "bad")
        elif use.source == "removed":
            where = _Tone("removed from newer Pythons", "warn")
        else:
            where = _IMPORT_WORDS[use.source]
        rows.append([use.top, where, "import time" if use.startup else "inside a function"])
    return rows


def _aws_blocks(cmap: CodeMap) -> list[Any]:
    """
    Its AWS calls, a row per operation, and the IAM policy they need.
    """
    grouped: dict[tuple[str, str, str], list[AwsCall]] = {}
    for call in cmap.aws:
        grouped.setdefault((call.service, call.operation, call.access), []).append(call)
    rows = []
    for (service, op, access), calls in grouped.items():
        where = [f"{c.file} line {c.line}" + (", at import" if c.startup else f" in {_short_name(c.function)}()")
                 + (", in a loop" if c.loop else "") + (", first page only" if c.pages == "one" else "")
                 + (", guessed from its name" if c.guessed else "") for c in calls]
        shown = "\n".join(where[:3]) + (f"\n+{len(where) - 3} more" if len(where) > 3 else "")
        rows.append([_service_name(service), op, access, shown, calls[0].permission or "(none needed)"])
    blocks: list[Any] = [_Table(["Service", "Call", "Does", "Where", "IAM permission"], rows,
                                title="The AWS calls it makes", code_cols=(4,), max_rows=0)]
    actions = sorted({c.permission for c in cmap.aws if c.permission})
    if actions:
        policy = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": actions, "Resource": "*"}]}
        blocks.append(_Text(json.dumps(policy, indent=2), code=True, collapsed=True, title=(
            "The permissions those calls need, as an IAM policy (narrow Resource to its own tables, buckets and "
            "queues)")))
    return blocks


def _env_rows(cmap: CodeMap) -> list[list[Any]]:
    rows = []
    for name in dict.fromkeys(e.name for e in cmap.env):
        reads = [e for e in cmap.env if e.name == name]
        needed = any(e.required for e in reads)
        default = next((e.default for e in reads if e.default), "")
        how: Any = (_Tone("os.environ[...]: needed", "warn") if needed else f"a default: {default}" if default
                    else "optional: None when it isn't set")
        where = f"{reads[0].file} line {reads[0].line}" + (f" (+{len(reads) - 1} more)" if len(reads) > 1 else "")
        rows.append([name, how, where])
    return rows


def _cards(cmap: CodeMap) -> _Cards:
    entry = _short_name(cmap.entry) if cmap.entry else None
    names = list(dict.fromkeys(e.name for e in cmap.env))
    ops = list(dict.fromkeys((c.service, c.operation) for c in cmap.aws))
    services = cmap.services
    files = len({f.file for f in cmap.functions})
    http = [s for s in cmap.spots if s.kind == "http"]
    return _Cards([
        ("Starts at", f"{entry}() in {cmap.handler_file}" if entry else f"nothing in {cmap.handler_file}",
         "" if entry else "warn"),
        ("Functions run", f"{len(cmap.functions):,}" + (f" in {files:,} files" if files > 1 else "")),
        ("AWS calls", f"{len(ops)} · {', '.join(services[:3])}{', …' if len(services) > 3 else ''}" if ops
         else "none it can see"),
        ("HTTP requests", f"{len(http):,}" if http else "none"),
        ("Environment", f"{_plural(len(names), 'variable')} read" if names else "none read"),
    ])


def _closing_note(cmap: CodeMap, graph: CodeGraph) -> _Note:
    said = ["It reads the code with Python's ast module and runs none of it. It follows calls into the folder's own "
            "functions and the boto3 clients it makes; calls through a value handed in from elsewhere, or made inside "
            "a library, aren't followed, so there may be more than it lists."]
    if graph.hidden:
        said.append(f"The graph leaves out {_plural(graph.hidden, 'function')} to stay readable: run with --all to "
                    "draw every one.")
    if cmap.other_files:
        said.append(f"{_plural(cmap.other_files, 'other Python file')} in the folder "
                    f"{'is' if cmap.other_files == 1 else 'are'}n't imported from here, so they're left out.")
    if cmap.unreached:
        said.append(f"{_plural(cmap.unreached, 'function')} in the files it read never "
                    f"run{'s' if cmap.unreached == 1 else ''} from {_short_name(cmap.entry or '')}().")
    if cmap.limited:
        said.append(f"To keep it short, it {cmap.limited}.")
    return _Note(" ".join(said))


def page_blocks(cmap: CodeMap, *, project: str, max_functions: int, max_depth: int,
                sources: dict[str, str] | None = None) -> list[Any]:
    """
    The whole page for one entry point, as report blocks. sources is the code read, {file: its text}: with it, a box
    of the graph clicked shows its code.
    """
    read = (f"{_plural(cmap.files, 'Python file')} ({cmap.lines:,} lines) read with ast, nothing run"
            if cmap.files else "")
    blocks: list[Any] = [_Title(f"How {cmap.handler} works", " · ".join(filter(None, [project, read])))]
    if cmap.note:
        return blocks + [_Note(cmap.note)]
    if cmap.entry is None and cmap.handlers:
        blocks.append(_Note(f"{cmap.handler} isn't a function in {cmap.handler_file}. Its functions that look like "
                            f"entry points: {', '.join(cmap.handlers)}."))
    blocks.append(_cards(cmap))
    blocks.append(_Findings(code_map_findings(cmap), empty=(
        "Nothing in the code stands out: what it imports is there, and its HTTP and list calls look complete.")))
    graph = code_graph(cmap, max_functions=max_functions, max_depth=max_depth)
    entry = _short_name(cmap.entry) if cmap.entry else None
    walk = _Walk(cmap.startup, cmap.steps, f"What each call does, step by step from {entry}()" if entry
                 else "What each call does", calls_title=f"Each call, from {entry}()" if entry else "Each call",
                 functions=cmap.functions, sources=sources or {})
    stops = len(walk_stops(walk))
    if graph.nodes:
        drawn = [_Graph(graph, "How it fits together: what comes in, who calls whom, and what it reaches",
                        sources=sources or {}),
                 _Text(graph.mermaid(), code=True, collapsed=True, title=(
                     "The same graph in Mermaid, to paste in a Markdown file, a wiki or a pull request"))]
        blocks.append(_Tabs([("Graph", f"{len(graph.nodes)} box{'' if len(graph.nodes) == 1 else 'es'}", drawn),
                             ("Step by step", _plural(stops, "step"), [walk])]))
    else:
        blocks.append(walk)
    if cmap.aws:
        blocks += _aws_blocks(cmap)
    if cmap.env:
        blocks.append(_Table(["Variable", "Read with", "Where"], _env_rows(cmap), max_rows=0,
                             title="The environment variables it reads (their names: values are never read)"))
    if cmap.event:
        platform = get_platform(cmap.platform)
        kind = platform.input_kind(cmap.event)
        blocks.append(_Table(["Field", "Read with", "Where"],
                             [[f.label, "needed" if f.required else ".get(...)", f"{f.file} line {f.line}"]
                              for f in cmap.event],
                             title=f"What it reads from {platform.input_name}"
                             + (f", which looks like {kind}" if kind else "")))
    if cmap.functions:
        rows = [[f"{_short_name(f.name)}()", f"{f.file} line {f.line}", f"{f.lines:,}",
                 "\n".join(_called_text(c) for c in f.called_from[:3]) + (
                     f"\n+{len(f.called_from) - 3} more" if len(f.called_from) > 3 else "") or "the entry point",
                 f.doc or "-"] for f in cmap.functions]
        blocks.append(_Table(["Function", "Where", "Lines", "Called from", "What its docstring says"], rows,
                             title="Its own functions that run"))
    libraries = _import_rows(cmap)
    if libraries:
        blocks.append(_Table(["Module", "Comes from", "Imported at"], libraries, title="What it imports"))
    http = [s for s in cmap.spots if s.kind == "http"]
    if http:
        blocks.append(_Table(["Request", "Where", "Timeout"], [
            [s.detail, _where(s.file, s.line, s.function), "set" if s.ok else _Tone("none", "warn")] for s in http],
            title="The HTTP requests it sends", max_rows=0))
    blocks.append(_closing_note(cmap, graph))
    return blocks
