"""
Writes the graph on the docs site's home page (docs/snippets/graph-trace.svg): the graph code-node draws for
examples/orders-service, redrawn as inline SVG the site's CSS can style. Pointing at a box dims what it isn't joined
to, like the real page, and docs/javascripts/graph.js lights up the path each line of lambda_handler takes.

    python scripts/site_graph.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from code_node.report.brands import fills, logo_for  # noqa: E402  the same logos as code-node's graph

OUT = Path(__file__).resolve().parent.parent / "docs" / "snippets"

ICONS = {  # 16 x 16 line drawings, the same as code-node's graph (src/code_node/report/graph.py)
    "function": "M3.6 2.6h2.1l6 10.8h1.7M8.4 7.4 4.2 13.4",
    "handler": "M5.2 3.4v9.2l7.4-4.6z",
    "event": "M9.2 1.8 3.6 9h4.2l-1 5.2L12.4 7H8.2z",
    "env": "M2.5 4.5h1.6M7.1 4.5h6.4M2.5 8h6.4M11.9 8h1.6M2.5 11.5h3M8.5 11.5h5M5.6 3v3M10.4 6.5v3M7 10v3",
    "http": "M8 2a6 6 0 1 0 0 12A6 6 0 1 0 8 2zM2.2 8h11.6M8 2c-2.1 2.2-2.1 9.8 0 12M8 2c2.1 2.2 2.1 9.8 0 12",
}

COLUMNS = [(20, "COMES IN"), (226, "ENTRY"), (432, "CALLS"), (638, "REACHES")]
WIDTH, HEIGHT = 810, 418
BOX_W = 152


@dataclass
class Node:
    id: str
    kind: str  # event, env, handler, function, aws, http
    label: str
    sub: str
    column: int
    y: int
    icon: str  # a line drawing in ICONS, or a logo's name ('aws-s3')
    tone: str = ""
    h: int = 58

    @property
    def x(self) -> int:
        return COLUMNS[self.column][0]


@dataclass
class Edge:
    source: str
    target: str
    kind: str  # call, event, env, reads, writes, sends, http


NODES = [
    Node("event", "event", "An S3 event", "Records[] · key", 0, 70, "event"),
    Node("env", "env", "Environment", "4 variables", 0, 262, "env"),
    Node("handler", "handler", "lambda_handler()", "handler.py line 30", 1, 166, "handler", h=62),
    Node("read", "function", "read_orders()", "handler.py line 19", 2, 32, "function"),
    Node("save", "function", "OrderStore.save()", "store.py line 16", 2, 126, "function"),
    Node("announce", "function", "announce()", "notify.py line 14", 2, 220, "function"),
    Node("chat", "function", "post_to_chat()", "notify.py line 20", 2, 326, "function", "warn"),
    Node("s3", "aws", "S3", "reads · writes", 3, 32, "aws-s3"),
    Node("ddb", "aws", "DynamoDB", "writes", 3, 126, "aws-dynamodb"),
    Node("sns", "aws", "SNS", "sends", 3, 220, "aws-sns"),
    Node("web", "http", "The web", "POST · no timeout", 3, 326, "http", "warn"),
]

EDGES = [
    Edge("event", "handler", "event"),
    Edge("env", "save", "env"),
    Edge("env", "announce", "env"),
    Edge("env", "chat", "env"),
    Edge("handler", "read", "call"),
    Edge("handler", "save", "call"),
    Edge("handler", "announce", "call"),
    Edge("announce", "chat", "call"),
    Edge("read", "s3", "reads"),
    Edge("save", "ddb", "writes"),
    Edge("save", "s3", "writes"),
    Edge("announce", "sns", "sends"),
    Edge("chat", "web", "http"),
]

BY_ID = {node.id: node for node in NODES}


def _anchors(edge: Edge) -> tuple[tuple[float, float], tuple[float, float], bool]:
    """
    Where an edge leaves and lands: right side to left side, or bottom to top within a column.
    """
    a, b = BY_ID[edge.source], BY_ID[edge.target]
    if a.column == b.column:
        x = a.x + BOX_W / 2
        return (x, a.y + a.h), (x, b.y), True
    spread = {"save": {"ddb": -6, "s3": 6}, "env": {"save": -8, "chat": 8}}.get(edge.source, {}).get(edge.target, 0)
    start = (a.x + BOX_W, a.y + a.h / 2 + spread)
    end = (b.x, b.y + b.h / 2 + (-8 if edge.source == "save" and edge.target == "s3" else 0))
    return start, end, False


def _curve(edge: Edge) -> tuple[str, tuple[float, float], tuple[int, int]]:
    """
    The edge's path, where it ends and which way it points there.
    """
    (x1, y1), (x2, y2), down = _anchors(edge)
    if down:
        c1, c2 = (x1, y1 + (y2 - y1) / 2), (x2, y1 + (y2 - y1) / 2)
    else:
        bend = (x2 - x1) * 0.5
        c1, c2 = (x1 + bend, y1), (x2 - bend, y2)
    d = f"M{x1:.1f},{y1:.1f}C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {x2:.1f},{y2:.1f}"
    return d, (x2, y2), (0, 1) if down else (1, 0)


def _head(end: tuple[float, float], direction: tuple[int, int]) -> str:
    x, y = end
    if direction == (0, 1):
        return f"M{x - 4.5:.1f},{y - 7:.1f}L{x:.1f},{y - 1:.1f}L{x + 4.5:.1f},{y - 7:.1f}"
    return f"M{x - 7:.1f},{y - 4.5:.1f}L{x - 1:.1f},{y:.1f}L{x - 7:.1f},{y + 4.5:.1f}"


def _badge(node: Node) -> str:
    """
    A box's badge: its service's logo on a plain tile, else a line drawing in the box's colour.
    """
    x, y = node.x, node.y
    found = logo_for(node.icon, 26)  # its small mark: the figure is drawn smaller than the page's graph
    if found is None:
        return (
            f'<rect class="bd" x="{x + 10}" y="{y + 10}" width="26" height="26" rx="8"/>'
            f'<path class="ic" transform="translate({x + 15},{y + 15})" d="{ICONS[node.icon]}"/>'
        )
    width, height, body = found
    if fills(found):  # AWS's icons fill the badge, its corners rounded
        return (
            f'<clipPath id="cn-badge-{node.id}"><rect x="{x + 10}" y="{y + 10}" width="26" height="26" rx="7"/>'
            f'</clipPath><g clip-path="url(#cn-badge-{node.id})"><svg class="logo" x="{x + 10}" y="{y + 10}" '
            f'width="26" height="26" viewBox="0 0 {width} {height}">{body}</svg></g>'
        )
    return (
        f'<rect class="bd lg" x="{x + 10}" y="{y + 10}" width="26" height="26" rx="8"/>'
        f'<svg class="logo" x="{x + 13}" y="{y + 13}" width="20" height="20" viewBox="0 0 {width} {height}" '
        f'fill="currentColor">{body}</svg>'
    )


def _node_svg(node: Node) -> str:
    x, y = node.x, node.y
    mono = node.kind in ("handler", "function")
    joined = [e for e in EDGES if node.id in (e.source, e.target)]
    neighbours = " ".join(f"a-{e.target if e.source == node.id else e.source}" for e in joined)
    return (
        f'<g class="n k-{node.kind} n-{node.id} {neighbours}{" warn" if node.tone else ""}" '
        f'data-node="{node.id}">'
        f'<rect class="bg" x="{x}" y="{y}" width="{BOX_W}" height="{node.h}" rx="12"/>'
        + _badge(node)
        + f'<text class="lb{" mono" if mono else ""}" x="{x + 44}" y="{y + 24}">{node.label}</text>'
        f'<text class="sb" x="{x + 44}" y="{y + 41}">{node.sub}</text>'
        + (
            '<circle class="wd" cx="{:.0f}" cy="{:.0f}" r="7"/><path class="wm" d="M{:.0f},{:.0f}v4.6M{:.0f},{:.0f}v.4"/>'.format(
                x + BOX_W - 2, y + 2, x + BOX_W - 2, y - 1.4, x + BOX_W - 2, y + 5.4
            )
            if node.tone
            else ""
        )
        + "</g>"
    )


def _edge_svg(edge: Edge) -> str:
    d, end, direction = _curve(edge)
    return (
        f'<g class="e k-{edge.kind} s-{edge.source} t-{edge.target}" data-edge="{edge.source}>{edge.target}">'
        f'<path class="ln" d="{d}"/><path class="ah" d="{_head(end, direction)}"/></g>'
    )


def graph_svg(label: str) -> str:
    """
    The whole graph as one line of inline SVG (a blank line would end the Markdown HTML block it sits in).
    """
    rules = []
    for node in NODES:
        rules.append(f".cn-graph:has(.n-{node.id}:hover) .e:not(.s-{node.id}):not(.t-{node.id}){{opacity:.08}}")
        rules.append(f".cn-graph:has(.n-{node.id}:hover) .n:not(.n-{node.id}):not(.a-{node.id}){{opacity:.3}}")
    captions = "".join(f'<text class="cap" x="{x + 2}" y="14">{text}</text>' for x, text in COLUMNS)
    edges = "".join(_edge_svg(edge) for edge in EDGES)
    nodes = "".join(_node_svg(node) for node in NODES)
    return (
        f'<svg class="cn-graph" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{label}">'
        f"<style>{''.join(rules)}</style>{captions}{edges}{nodes}</svg>"
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    graph = graph_svg(
        "A code graph: an S3 event comes in, lambda_handler calls read_orders, OrderStore.save and announce, and they "
        "reach S3, DynamoDB, SNS and the web"
    )
    (OUT / "graph-trace.svg").write_text(graph + "\n", "utf-8")
    print(f"wrote {OUT / 'graph-trace.svg'}")


if __name__ == "__main__":
    main()
