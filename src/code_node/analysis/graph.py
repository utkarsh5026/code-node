"""
The code map as a CodeGraph: its inputs, the entry point and its functions, and what it
reaches, with .mermaid().
"""

from __future__ import annotations

import heapq
import re
from collections import defaultdict
from dataclasses import dataclass, field, replace

from ..kit.fmt import _plural
from ..kit.text import _clip

from .syntax import _a
from .aws_model import _service_name
from .model import AwsCall, CodeFunction, CodeMap, CodeSpot, CodeStep, History, LibraryCall
from .findings import _listed, _short_name
from ..platforms import get_platform


@dataclass
class CodeSpan:
    """
    Lines of the code a box in how_it_works()'s graph is about, for a front end to show beside it: a function whole,
    or a few lines around each place it's called with, read or reached from.
    """

    file: str
    start: int
    end: int
    lit: list[int] = field(default_factory=list)  # the lines in it worth pointing at: where it calls, reads or sends


@dataclass
class GraphNode:
    """
    A box in how_it_works()'s graph: what calls the code (the event), what it's configured with (its environment),
    one of its own functions, or what it reaches (an AWS service, the web).
    """

    id: str  # 'event', 'env', 'start', 'f0' (a function), 'aws-s3', 'http', 'lib-redis-redis'
    kind: str  # 'event', 'env', 'start', 'handler', 'function', 'aws', 'http', 'service' (one a library reaches)
    label: str  # 'handler()', 'S3', 'an SQS batch'
    sub: str = ""  # under the label: 'etl.py line 13', 'reads · writes'
    lines: list[str] = field(default_factory=list)  # what the box lists: its operations, fields or variables
    tone: str = ""  # 'warn' when a warning in the report is about it
    tip: str = ""  # said on hover
    column: int = 0  # left to right: 0 what comes in, 1 the handler, then its functions by depth, last what it reaches
    flags: dict[str, str] = field(default_factory=dict)  # a listed line a warning is about -> a word or two:
    # {'TEAM_TOPIC': 'not set'}, {'Query': 'first page only'}, {'GET https://...': 'no timeout'}
    code: list[CodeSpan] = field(default_factory=list)  # the lines of code it's about
    more: list[str] = field(default_factory=list)  # its own functions it calls that the graph leaves out: 'save()'
    when: str = ""  # a function called only under an if, everywhere it's called: 'check(order)'
    icon: str = ""  # a service's icon, when its plugin names one: 'database', 'queue', 'spark'; or the entry
    # point's logo, when its platform names one: 'fastapi-icon'
    name: str = ""  # a function's box: the function, as module.name ('orders.repo.save')
    history: History | None = None  # a function's box: what git says about its lines


@dataclass
class GraphEdge:
    """
    An arrow in how_it_works()'s graph: a call, an AWS call, an HTTP request, or the event and variables coming in.
    """

    source: str  # a GraphNode id
    target: str
    kind: str  # 'call', 'event', 'env', 'http', 'client' (a client made at start-up), or an AWS call's access:
    # 'reads', 'writes', 'sends', 'runs', 'signs'
    label: str = ""  # what goes along it: 'GetObject, PutItem', 'DB_HOST', 'line 19'
    tone: str = ""  # 'warn' when a warning in the report is about it
    loop: bool = False  # made inside a loop: once per item
    guessed: bool = False  # AWS calls known only by their method's name: their client couldn't be followed
    indirect: bool = False  # made in functions the graph leaves out, below the box it starts from
    when: str = ""  # a call made only under an if: its test, 'args.command == "init"'


@dataclass
class CodeGraph:
    """
    How the code fits together, as boxes and arrows: what comes in, its own functions and who calls whom, and what
    they reach outside. code_graph() makes it from a CodeMap; mermaid() writes it for a Markdown file.
    """

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    hidden: int = 0  # functions left out to keep the graph readable (too deep, or too many)
    too_deep: int = 0  # ...of them, the ones deeper than it draws

    def node(self, node_id: str) -> GraphNode | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def mermaid(self) -> str:
        """
        The graph in Mermaid's language, for a Markdown file, a wiki or a pull request that renders it.
        """
        shapes = {
            "event": ("([", "])"),
            "env": ("[/", "/]"),
            "aws": ("[(", ")]"),
            "service": ("[(", ")]"),
            "http": ("{{", "}}"),
            "start": ("[[", "]]"),
        }
        out = ["flowchart LR"]
        for n in self.nodes:
            left, right = shapes.get(n.kind, ("[", "]"))
            text = n.label + (f"<br/><small>{n.sub}</small>" if n.sub else "")
            out.append(f'  {_mermaid_id(n.id)}{left}"{_mermaid_text(text)}"{right}')
        arrows = {"call": "-->", "event": "==>", "env": "-.->"}
        for e in self.edges:
            arrow = arrows.get(e.kind, "-->")
            label = e.label if e.kind != "call" or not e.label.startswith("line ") else ""
            label = " · ".join(filter(None, [label, f"when {e.when}" if e.when else ""]))
            text = f'|"{_mermaid_text(_clip(label, 60))}"|' if label else ""
            out.append(f"  {_mermaid_id(e.source)} {arrow}{text} {_mermaid_id(e.target)}")
        warned = [n.id for n in self.nodes if n.tone == "warn"]
        if warned:
            out.append("  classDef warn stroke:#f59e0b,stroke-width:2px")
            out.append(f"  class {','.join(_mermaid_id(i) for i in warned)} warn")
        return "\n".join(out)


def _mermaid_id(node_id: str) -> str:
    return re.sub(r"\W", "_", node_id)


def _mermaid_text(text: str) -> str:
    """
    Text for a Mermaid label: its quotes and brackets as entities, so a label can hold any code.
    """
    return (
        text.replace("#", "#35;")
        .replace("&", "#amp;")
        .replace('"', "#quot;")
        .replace("<br/>", "\0")
        .replace("<small>", "\1")
        .replace("</small>", "\2")
        .replace("<", "#lt;")
        .replace(">", "#gt;")
        .replace("\0", "<br/>")
        .replace("\1", "<small>")
        .replace("\2", "</small>")
    )


def _service_node(library: str, service: str) -> str:
    """
    The box id of a service a library reaches: 'lib-sql-postgresql'. Letters, digits and hyphens only, as for AWS.
    """
    return "lib-" + (re.sub(r"[^a-z0-9]+", "-", f"{library} {service}".lower()).strip("-") or "service")


def _aws_node(service: str) -> str:
    """
    An AWS service's box id: 'aws-s3'. The service is a literal from the code, so only letters, digits and hyphens
    stay: the id goes into class names and the CSS rules that light up what a box is joined to.
    """
    return "aws-" + (re.sub(r"[^a-z0-9]+", "-", service.lower()).strip("-") or "service")


_GRAPH_FUNCTIONS = 24  # functions code_graph() draws, at most (the ones that lead to the most code first)

_REACH_WEIGHT = 30  # lines of code an AWS call, HTTP request or environment variable counts as, picking boxes

_GRAPH_DEPTH = 5  # ...and how deep below the handler

_GRAPH_LINES = 5  # lines a box lists before "+3 more"


_SPAN_BEFORE, _SPAN_AFTER = 2, 3  # lines shown around each place a box is about


def _around(places: list[tuple[str, int, str]], functions: dict[str, CodeFunction]) -> list[CodeSpan]:
    """
    A few lines around each place (file, line, the function it's in), kept within that function when it's one of
    `functions`, the places lit, in the order their files first come; places close together share their lines.
    """
    files = list(dict.fromkeys(file for file, _, _ in places))
    spans: list[CodeSpan] = []
    for file, line, function in sorted(set(places), key=lambda place: (files.index(place[0]), place[1])):
        if line < 1:
            continue
        start, end = max(1, line - _SPAN_BEFORE), line + _SPAN_AFTER
        f = functions.get(function)
        if f is not None and f.file == file and f.line <= line < f.line + f.lines:
            start, end = max(start, f.line), min(end, f.line + f.lines - 1)
        if spans and spans[-1].file == file and start <= spans[-1].end + 1:
            spans[-1].end = max(spans[-1].end, end)
            spans[-1].lit.append(line)
        else:
            spans.append(CodeSpan(file, start, end, [line]))
    return spans


def _start_places(steps: list[CodeStep]) -> list[tuple[str, int, str]]:
    """
    The lines that run when the code is imported, its modules' own (a function they call has its own box).
    """
    places = []
    for step in steps:
        if step.kind == "module":
            places += _start_places(step.steps)
        elif step.kind != "def":
            places.append((step.file, step.line, ""))
            places += _start_places(step.steps)
    return places


def _listed_lines(items: list[str], most: int = _GRAPH_LINES) -> list[str]:
    return items[:most] if len(items) <= most else items[: most - 1] + [f"+{len(items) - most + 1} more"]


def _when(f: CodeFunction, places: list[str]) -> str:
    """
    The condition a function is called under from these places ('check(order)'), when every one of them has one:
    each place's nearest test, joined with 'or'. '' when one of them always calls it.
    """
    if not places or any(not f.when.get(where) for where in places):
        return ""
    return " or ".join(dict.fromkeys(f.when[where] for where in places))


def _weights(cmap: CodeMap, children: dict[str, list[tuple[str, str]]]) -> dict[str, int]:
    """
    How much each function leads to: the lines of code in it and in every function it calls, however deep (each
    counted once), and _REACH_WEIGHT more for each AWS call, HTTP request and environment variable among them.
    """
    lines = {f.name: f.lines for f in cmap.functions}
    for function in (
        [c.function for c in cmap.aws]
        + [c.function for c in cmap.library_calls]
        + [e.function for e in cmap.env]
        + [s.function for s in cmap.spots if s.kind == "http"]
    ):
        if function in lines:
            lines[function] += _REACH_WEIGHT
    weight: dict[str, int] = {}
    for name in lines:
        seen, todo = {name}, [name]
        while todo:
            for child, _ in children.get(todo.pop(), []):
                if child not in seen:
                    seen.add(child)
                    todo.append(child)
        weight[name] = sum(lines.get(k, 0) for k in seen)
    return weight


def _pick(
    cmap: CodeMap,
    entry: str,
    start_key: str,
    children: dict[str, list[tuple[str, str]]],
    level: dict[str, int],
    weight: dict[str, int],
    order: dict[str, int],
    room: int,
    max_depth: int,
    first: bool = False,
) -> list[str]:
    """
    The functions the graph draws besides the entry point, at most `room` of them and max_depth calls deep: grown out
    from the entry point (and what runs at import), each time taking the one the drawn boxes call that leads to the
    most code, so the boxes are the ones that do the work and each is joined to one above it. first takes every
    function the entry point calls before the rest.
    """

    def depth(name: str) -> int:
        return level.get(name, by_name[name].depth + 1)

    by_name = {f.name: f for f in cmap.functions}
    allowed = [f.name for f in cmap.functions if f.name != entry and depth(f.name) <= max_depth]
    if len(allowed) <= room:
        return allowed
    queue: list[tuple[int, int, int, str]] = []

    def offer(name: str) -> None:
        if name in by_name and name != entry and depth(name) <= max_depth:
            heapq.heappush(queue, (-weight.get(name, 0), depth(name), order[name], name))

    for root in (entry, start_key):
        for child, _ in children.get(root, []):
            offer(child)
    for name in allowed:  # nothing the drawn code is known to call it: offered from the start, as before
        if name not in level:
            offer(name)
    picked: list[str] = []
    if first:
        for child, _ in children.get(entry, []):
            if child in by_name and child != entry and child not in picked and depth(child) <= max_depth:
                picked.append(child)
        for name in list(picked):
            for child, _ in children.get(name, []):
                if child not in picked:
                    offer(child)
    while queue and len(picked) < room:
        name = heapq.heappop(queue)[3]
        if name in picked:
            continue
        picked.append(name)
        for child, _ in children.get(name, []):
            if child not in picked:
                offer(child)
    return picked


def _focused(cmap: CodeMap, focus: str) -> CodeMap:
    """
    The map cut down to one of its functions and what it calls, however deep, as if the code started there: its
    calls in from elsewhere, what runs at import and the entry point's input left out.
    """
    children: dict[str, list[str]] = defaultdict(list)
    for f in cmap.functions:
        for where in f.called_from:
            children[where.rpartition(" line ")[0]].append(f.name)
    scope, todo = {focus}, [focus]
    while todo:
        for child in children.get(todo.pop(), []):
            if child not in scope:
                scope.add(child)
                todo.append(child)
    root = next(f for f in cmap.functions if f.name == focus)
    functions = []
    for f in cmap.functions:
        if f.name in scope:
            kept = [] if f.name == focus else [w for w in f.called_from if w.rpartition(" line ")[0] in scope]
            functions.append(replace(f, called_from=kept, when={w: t for w, t in f.when.items() if w in kept}))
    return replace(
        cmap,
        entry=focus,
        handler_file=root.file,
        entry_line=root.line,
        startup=[],
        event=[],
        functions=functions,
        aws=[c for c in cmap.aws if c.function in scope],
        library_calls=[c for c in cmap.library_calls if c.function in scope],
        env=[e for e in cmap.env if e.function in scope],
        spots=[s for s in cmap.spots if s.function in scope and not s.startup],
        routes=[r for r in cmap.routes if r[2] in scope],
    )


def code_graph(
    cmap: CodeMap, *, max_functions: int = _GRAPH_FUNCTIONS, max_depth: int = _GRAPH_DEPTH, focus: str = ""
) -> CodeGraph:
    """
    How the code fits together, as boxes and arrows, from a CodeMap: on the left what comes in (the event, with the
    fields it reads, and the environment variables), then the handler, what runs at start-up, and its own functions
    by how many calls they are from those (an arrow for each call), and on the right the AWS services and the web it
    reaches, each arrow by what it does (reads, writes, sends, runs). A box or an arrow a warning is about is marked,
    and says which on hover. At most max_functions functions, max_depth calls deep; `hidden` counts the rest, and what
    they do is drawn from the nearest box above them that is.
    The functions drawn are grown out from the entry point, each time the one that leads to the most code (and to AWS,
    the web and the environment), so the boxes are the ones that do the work, not the nearest helpers.
    focus draws the graph from one of its functions instead (module.name): it and what it calls, every call it makes
    drawn even past max_functions, and nothing from what comes in or what runs at import.
    """
    graph = CodeGraph()
    if cmap.note or cmap.entry is None:
        return graph
    if focus:
        if not any(f.name == focus for f in cmap.functions):
            return graph
        cmap = _focused(cmap, focus)
    platform = get_platform(cmap.platform)
    entry = cmap.entry
    by_name = {f.name: f for f in cmap.functions}
    entry_is_function = entry in by_name
    start_key = "<start>"  # a module's top level: what runs when Python imports the code

    # who calls whom; a caller that isn't one of its functions is a module's top level, which runs at start-up
    parents: dict[str, list[tuple[str, str]]] = defaultdict(list)
    children: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for f in cmap.functions:
        for where in f.called_from:
            key, _, line = where.rpartition(" line ")
            caller = key if key in by_name or key == entry else start_key
            if (caller, line) not in parents[f.name]:
                parents[f.name].append((caller, line))
                children[caller].append((f.name, line))
    routes: dict[str, list[str]] = defaultdict(list)  # a function -> the routes it answers ('GET /items')
    for method, path, key in cmap.routes:
        routes[key].append(f"{method} {path}")
    if not entry_is_function:  # a handler that's an object (a web app's adapter) calls each route
        for key in routes:
            if key in by_name and (entry, "") not in parents[key]:
                parents[key].append((entry, ""))
                children[entry].append((key, ""))
    level: dict[str, int] = {entry: 0, start_key: 0}
    todo = [entry, start_key]
    while todo:
        key = todo.pop(0)
        for child, _ in children.get(key, []):
            if child not in level:
                level[child] = level[key] + 1
                todo.append(child)
    order = {f.name: i for i, f in enumerate(cmap.functions)}
    weight = _weights(cmap, children)
    room = max_functions - entry_is_function
    if focus:  # a function opened on its own shows every call it makes
        room = max(room, len({child for child, _ in children.get(entry, [])}))
    picked = _pick(cmap, entry, start_key, children, level, weight, order, room, max_depth, first=bool(focus))
    shown = ([by_name[entry]] if entry_is_function else []) + sorted(
        (by_name[name] for name in picked), key=lambda f: (level.get(f.name, f.depth + 1), order[f.name])
    )
    graph.hidden = len(cmap.functions) - len(shown)
    graph.too_deep = sum(1 for f in cmap.functions if level.get(f.name, f.depth + 1) > max_depth)
    ids = {f.name: f"f{i}" for i, f in enumerate(shown)}
    drawn_level = {entry: 0, start_key: 0}  # calls from the entry point through the boxes drawn: each box's column
    todo = [entry, start_key]
    while todo:
        key = todo.pop(0)
        for child, _ in children.get(key, []):
            if child in ids and child not in drawn_level:
                drawn_level[child] = drawn_level[key] + 1
                todo.append(child)
    if not entry_is_function:
        ids[entry] = "f-entry"

    def owner(key: str) -> tuple[str | None, bool]:
        """
        The box what a function (or a module's top level) does is drawn from, and whether that's a box above it
        because the graph leaves the function out.
        """
        if key in ids:
            return ids[key], False
        if key not in by_name:
            return "start", False
        seen, queue = {key}, [key]
        while queue:
            for parent, _ in parents.get(queue.pop(0), []):
                if parent in ids:
                    return ids[parent], True
                if parent == start_key:
                    return "start", True
                if parent not in seen:
                    seen.add(parent)
                    queue.append(parent)
        return None, False

    # why a box or arrow is amber: the warnings about it, said on hover
    reasons: dict[str, list[str]] = defaultdict(list)
    for spot in cmap.spots:
        line = f" (line {spot.line})"
        why = (
            "an HTTP request without a timeout"
            if spot.kind == "http" and not spot.ok
            else "drops every error"
            if spot.kind == "swallow"
            else ""
        )
        if why:
            reasons[spot.function].append(why + line)
    for call in cmap.aws:
        if call.pages == "one" and call.operation.startswith(("List", "Scan", "Query")) and not call.guessed:
            reasons[call.function].append(f"{call.label} reads only its first page (line {call.line})")
    for spot in cmap.spots:
        if spot.kind == "command" and not spot.ok:
            reasons[spot.function].append(f"runs a shell command built from {spot.detail} (line {spot.line})")
    for lib_call in cmap.library_calls:
        if lib_call.flag:
            reasons[lib_call.function].append(f"{lib_call.label}: {lib_call.flag} (line {lib_call.line})")
    denied = platform.denied(cmap)
    for call in cmap.aws:
        if call.permission in denied:
            reasons[call.function].append(f"{call.label} isn't allowed: {denied[call.permission]} (line {call.line})")
    for function, why in platform.marks(cmap).items():
        reasons[function] += why
    handler_reasons = (
        [] if focus else [m.split(":")[0] for level_, m in platform.entry_findings(cmap) if level_ == "warn"]
    )
    unset = platform.unset_env(cmap)

    # the lines in each function worth pointing at: where it calls, reads or sends what the graph draws
    lit: dict[str, set[int]] = defaultdict(set)
    for caller, called in children.items():
        lit[caller] |= {int(line) for _, line in called if line.isdigit()}
    for function, line in (
        [(c.function, c.line) for c in cmap.aws]
        + [(c.function, c.line) for c in cmap.library_calls]
        + [(e.function, e.line) for e in cmap.env]
        + [(s.function, s.line) for s in cmap.spots if s.kind == "http"]
    ):
        lit[function].add(line)

    def warned_tip(tip: str, why: list[str]) -> str:
        return tip + ("\nA warning is about it: " + "; ".join(why) if why else "")

    edges: list[GraphEdge] = []
    uses_start = bool(children.get(start_key))

    # calls between its functions, and from start-up
    entry_id = ids[entry]
    seen_calls: set[tuple[str, str]] = set()
    for f in shown:
        for caller, line in parents.get(f.name, []):
            source = "start" if caller == start_key else ids.get(caller)
            if source is None or (source, ids[f.name]) in seen_calls:
                continue
            seen_calls.add((source, ids[f.name]))
            lines = [ln for c, ln in parents[f.name] if c == caller and ln]
            label = (
                "; ".join(routes[f.name])
                if caller == entry and f.name in routes
                else "line " + ", ".join(lines[:3]) + (" …" if len(lines) > 3 else "")
                if lines
                else ""
            )
            edges.append(
                GraphEdge(
                    source,
                    ids[f.name],
                    "call",
                    label,
                    when=_when(f, [where for where in f.called_from if where.rpartition(" line ")[0] == caller]),
                )
            )
    has_input = not focus and (bool(cmap.event) or platform.draws_input)
    if has_input:
        edges.insert(0, GraphEdge("event", entry_id, "event", "its input"))

    # the environment
    names = list(dict.fromkeys(e.name for e in cmap.env))
    reads: dict[str, list[str]] = {}
    for e in cmap.env:
        source, _ = owner(e.function)
        if source is not None and e.name not in reads.setdefault(source, []):
            reads[source].append(e.name)
    for target, read in reads.items():
        uses_start |= target == "start"
        edges.append(
            GraphEdge("env", target, "env", ", ".join(read), "warn" if any(name in unset for name in read) else "")
        )

    # what it reaches: AWS
    services: dict[str, list[AwsCall]] = {}
    for call in cmap.aws:
        services.setdefault(call.service, []).append(call)
    reach: list[GraphNode] = []
    for service, calls in services.items():
        node_id = _aws_node(service)
        why = [
            f"{c.operation} reads only its first page ({c.file} line {c.line})"
            for c in calls
            if c.pages == "one" and c.operation.startswith(("List", "Scan", "Query")) and not c.guessed
        ]
        why += list(
            dict.fromkeys(
                f"{c.operation} isn't allowed: {denied[c.permission]}" for c in calls if c.permission in denied
            )
        )
        ops = list(dict.fromkeys(c.operation for c in calls))
        does = list(dict.fromkeys(c.access for c in calls))
        tip = f"{_service_name(service)}: " + ", ".join(
            f"{c.operation} ({c.permission or 'no permission needed'})"
            for c in {c.operation: c for c in calls}.values()
        )
        tip += "".join(
            f"\n{c.operation} line {c.line}: " + ", ".join(f"{arg} ← {source}" for arg, source in c.args)
            for c in calls
            if c.args
        )
        if all(c.guessed for c in calls):
            tip += "\nKnown only by the methods' names: their client couldn't be followed"
        reach.append(
            GraphNode(
                node_id,
                "aws",
                _service_name(service),
                " · ".join(does),
                _listed_lines(ops),
                "warn" if why else "",
                warned_tip(tip, why),
                flags={
                    **{
                        c.operation: "first page only"
                        for c in calls
                        if c.pages == "one" and not c.guessed and c.operation.startswith(("List", "Scan", "Query"))
                    },
                    **{c.operation: "not allowed" for c in calls if c.permission in denied},
                },
                code=_around([(c.file, c.line, c.function) for c in calls], by_name),
            )
        )
        grouped: dict[tuple[str, str, bool], list[AwsCall]] = {}
        for call in calls:
            source, indirect = owner(call.function)
            if source is not None:
                grouped.setdefault((source, call.access, indirect), []).append(call)
        for (source, access, indirect), group in grouped.items():
            uses_start |= source == "start"
            edges.append(
                GraphEdge(
                    source,
                    node_id,
                    access,
                    ", ".join(dict.fromkeys(c.operation for c in group)),
                    "warn"
                    if any(
                        (c.pages == "one" and c.operation.startswith(("List", "Scan", "Query")) and not c.guessed)
                        or c.permission in denied
                        for c in group
                    )
                    else "",
                    any(c.loop for c in group),
                    all(c.guessed for c in group),
                    indirect,
                )
            )

    # ...the services the libraries plugins know reach (Redis, a SQL database, OpenAI)
    by_service: dict[tuple[str, str], list[LibraryCall]] = {}
    for lib_call in cmap.library_calls:
        by_service.setdefault((lib_call.library, lib_call.service), []).append(lib_call)
    slow_clients = {s.detail: s for s in cmap.spots if s.kind == "connect" and s.waits}
    for (library, service), lib_calls in by_service.items():
        node_id = _service_node(library, service)
        rows = list(dict.fromkeys(c.row for c in lib_calls))
        flags = {c.row: c.flag for c in lib_calls if c.flag}
        why = list(dict.fromkeys(f"{c.row}: {c.flag} ({c.file} line {c.line})" for c in lib_calls if c.flag))
        if service in slow_clients:
            spot = slow_clients[service]
            why.append(f"its client has no timeout ({spot.file} line {spot.line}): a call waits {spot.waits}")
        tip = f"{service}: " + ", ".join(rows[:8]) + (", …" if len(rows) > 8 else "")
        reach.append(
            GraphNode(
                node_id,
                "service",
                service,
                " · ".join(dict.fromkeys(c.access for c in lib_calls)),
                _listed_lines(rows),
                "warn" if why else "",
                warned_tip(tip, why),
                flags=flags,
                code=_around([(c.file, c.line, c.function) for c in lib_calls], by_name),
                icon=lib_calls[0].icon,
            )
        )
        lib_grouped: dict[tuple[str, str, bool], list[LibraryCall]] = {}
        for lib_call in lib_calls:
            source, indirect = owner(lib_call.function)
            if source is not None:
                lib_grouped.setdefault((source, lib_call.access, indirect), []).append(lib_call)
        for (source, access, indirect), group in lib_grouped.items():
            uses_start |= source == "start"
            edges.append(
                GraphEdge(
                    source,
                    node_id,
                    access,
                    ", ".join(dict.fromkeys(c.row for c in group)),
                    "warn" if any(c.flag for c in group) else "",
                    any(c.loop for c in group),
                    indirect=indirect,
                )
            )

    # ...the clients start-up (or a function it runs) makes, for the services they're for
    clients = [s for s in cmap.spots if s.kind == "client" and s.startup]
    made = []
    for spot in clients:
        source, _ = owner(spot.function)
        target = _aws_node(spot.detail)
        if source is None or not any(n.id == target for n in reach):
            continue
        if source == "start" and spot.detail != "?":
            made.append(_service_name(spot.detail))
        if not any(e.source == source and e.target == target and e.kind == "client" for e in edges):
            uses_start |= source == "start"
            edges.append(GraphEdge(source, target, "client", f"makes its {_service_name(spot.detail)} client"))
    for spot in [s for s in cmap.spots if s.kind == "connect"]:  # a library's, wherever it's made: connect() opens one
        source, _ = owner(spot.function)
        target = next((n.id for n in reach if n.kind == "service" and n.label == spot.detail), None)
        if source is None or target is None:
            continue
        if source == "start":
            made.append(spot.detail)
        if not any(e.source == source and e.target == target and e.kind == "client" for e in edges):
            uses_start |= source == "start"
            edges.append(GraphEdge(source, target, "client", f"makes its {spot.detail} client", loop=bool(spot.loop)))

    # ...and the web
    http = [s for s in cmap.spots if s.kind == "http"]
    if http:
        slow = [s for s in http if not s.ok]
        reach.append(
            GraphNode(
                "http",
                "http",
                "The web",
                "HTTP requests",
                _listed_lines(list(dict.fromkeys(s.detail for s in http))),
                "warn" if slow else "",
                warned_tip(
                    "HTTP requests it sends", [f"{s.detail} has no timeout ({s.file} line {s.line})" for s in slow]
                ),
                flags={s.detail: "no timeout" for s in slow},
                code=_around([(s.file, s.line, s.function) for s in http], by_name),
            )
        )
        by_source: dict[tuple[str, bool], list[CodeSpot]] = {}
        for spot in http:
            source, indirect = owner(spot.function)
            if source is not None:
                by_source.setdefault((source, indirect), []).append(spot)
        for (source, indirect), group in by_source.items():
            uses_start |= source == "start"
            edges.append(
                GraphEdge(
                    source,
                    "http",
                    "http",
                    ", ".join(dict.fromkeys(s.detail for s in group)),
                    "warn" if any(not s.ok for s in group) else "",
                    any(s.loop for s in group),
                    indirect=indirect,
                )
            )

    # the boxes, left to right
    labels = [f.label for f in cmap.event]
    leaves = [
        label
        for label in labels
        if not any(other.startswith((label + "[", label + ".", label + " (")) for other in labels)
    ]
    kind = platform.input_kind(cmap.event) or (platform.input_name if platform.name else "its input")
    if has_input:
        graph.nodes.append(
            GraphNode(
                "event",
                "event",
                kind[0].upper() + kind[1:],
                "what it's called with",
                _listed_lines(leaves) or ["(no fields read)"],
                tip=f"What the entry point is called with: {platform.input_name}"
                + (f": the code reads {', '.join(leaves)}" if leaves else ""),
                code=_around([(f.file, f.line, "") for f in cmap.event], by_name),
            )
        )
    if names:
        graph.nodes.append(
            GraphNode(
                "env",
                "env",
                "Environment",
                "variables it reads",
                _listed_lines(names),
                "warn" if unset else "",
                warned_tip(
                    "Environment variables it reads (names only)",
                    [f"{name} isn't set where it runs" for name in names if name in unset],
                ),
                flags={name: "not set" for name in names if name in unset},
                code=_around([(e.file, e.line, e.function) for e in cmap.env], by_name),
            )
        )
    if uses_start:
        services_made = list(dict.fromkeys(made))
        graph.nodes.append(
            GraphNode(
                "start",
                "start",
                "At import",
                "once, when it loads",
                [
                    f"makes {_a(services_made[0])} {services_made[0]} client"
                    if len(services_made) == 1
                    else f"makes {_listed(services_made)} clients"
                ]
                if services_made
                else [],
                tip="What runs when Python imports the code, before the first call",
                column=1,
                code=_around(_start_places(cmap.startup), by_name),
            )
        )
    entry_file = cmap.handler_file or ""
    if not entry_is_function:
        graph.nodes.append(
            GraphNode(
                "f-entry",
                "handler",
                entry.rsplit(".", 1)[-1],
                f"{entry_file} line {cmap.entry_line}",
                ["an object, not a function"],
                tip=f"{entry} is called with its input",
                column=1,
                code=_around([(entry_file, cmap.entry_line, "")], by_name),
                icon=platform.entry_icon(cmap),
            )
        )
    for f in shown:
        is_entry = f.name == entry
        why = reasons.get(f.name, []) + (handler_reasons if is_entry else [])
        more = list(
            dict.fromkeys(
                f"{_short_name(child)}()"
                for child, _ in children.get(f.name, [])
                if child in by_name and child not in ids
            )
        )
        graph.nodes.append(
            GraphNode(
                ids[f.name],
                "handler" if is_entry else "function",
                f"{_short_name(f.name)}()",
                f"{f.file} line {f.line}",
                [f.doc] if f.doc else [],
                "warn" if why else "",
                warned_tip(
                    f"{f.name}({f.args}) in {f.file}, {_plural(f.lines, 'line')}"
                    + (f": {f.doc}" if f.doc else "")
                    + (
                        f"\nIt calls {_plural(len(more), 'function')} the graph leaves out: {', '.join(more)}"
                        if more
                        else ""
                    ),
                    why,
                ),
                column=1 + drawn_level.get(f.name, level.get(f.name, f.depth)),
                code=[
                    CodeSpan(
                        f.file,
                        f.line,
                        f.line + f.lines - 1,
                        sorted(n for n in lit[f.name] if f.line <= n < f.line + f.lines),
                    )
                ],
                more=more,
                when=_when(f, f.called_from),
                icon=platform.entry_icon(cmap) if is_entry and not focus else "",
                name=f.name,
                history=f.history,
            )
        )
    out_column = 1 + max([n.column for n in graph.nodes if n.kind in ("handler", "function", "start")] + [1])
    for node in reach:
        node.column = out_column
    graph.nodes += reach
    graph.edges = edges
    return graph


_GRAPH_VIEWS = 120  # functions opened on their own, at most: past that a box's calls left out stay in the steps

_GRAPH_EVERYTHING = 150  # functions, at most, for a graph of all of them besides the one drawn


@dataclass
class GraphView:
    """
    The graph from one of the functions a graph leaves calls out of: the function and what it calls (`graph`), and the
    calls from the entry point down to it (`path`, module.name each, the entry point first and the function last).
    """

    name: str
    graph: CodeGraph
    path: list[str] = field(default_factory=list)


def _call_path(cmap: CodeMap, name: str) -> list[str]:
    """
    The fewest calls from the entry point to a function: [entry, ..., name]. [name] when the entry point isn't above it.
    """
    known = {f.name for f in cmap.functions} | {cmap.entry or ""}
    parents: dict[str, list[str]] = defaultdict(list)
    for f in cmap.functions:
        for where in f.called_from:
            caller = where.rpartition(" line ")[0]
            if caller in known:
                parents[f.name].append(caller)
    came: dict[str, str] = {name: ""}
    todo = [name]
    while todo:
        key = todo.pop(0)
        if key == cmap.entry:
            path = [key]
            while came[path[-1]]:
                path.append(came[path[-1]])
            return path
        for parent in parents.get(key, []):
            if parent not in came:
                came[parent] = key
                todo.append(parent)
    return [name]


def graph_views(
    cmap: CodeMap,
    graph: CodeGraph,
    *,
    max_functions: int = _GRAPH_FUNCTIONS,
    max_depth: int = _GRAPH_DEPTH,
    most: int = _GRAPH_VIEWS,
) -> list[GraphView]:
    """
    A graph from each function whose calls `graph` leaves out, and from each such function in those, so that from any
    box with calls not drawn, its own graph has them: at most `most`, nearest the entry point first.
    """
    views: dict[str, GraphView] = {}
    todo = [graph]
    while todo and len(views) < most:
        for n in todo.pop(0).nodes:
            if not (n.more and n.name) or n.name in views or len(views) >= most:
                continue
            opened = code_graph(cmap, max_functions=max_functions, max_depth=max_depth, focus=n.name)
            views[n.name] = GraphView(n.name, opened, _call_path(cmap, n.name))
            todo.append(opened)
    return list(views.values())


def everything_graph(cmap: CodeMap, graph: CodeGraph, most: int = _GRAPH_EVERYTHING) -> CodeGraph | None:
    """
    Every function in one graph, when `graph` leaves some out and there are at most `most` of them; else None.
    """
    if not graph.hidden or len(cmap.functions) > most:
        return None
    return code_graph(cmap, max_functions=len(cmap.functions) + 1, max_depth=len(cmap.functions) + 1)
