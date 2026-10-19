"""
Writes the animated graphs on the docs site's home page (docs/snippets/graph-*.svg): the graph code-node draws for
examples/orders-service, redrawn as inline SVG the site's CSS can animate. Edges draw themselves in, pulses run along
them from what comes in to what it reaches, and pointing at a box dims what it isn't joined to, like the real page.

    python scripts/site_graph.py

The hero copy has pulses; the trace copy (the "follow a path" section) has none, and docs/javascripts/graph.js lights
its edges up one code line at a time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "snippets"

ICONS = {  # 16 x 16 line drawings, the same as code-node's graph (src/code_node/report/graph.py)
    "function": "M3.6 2.6h2.1l6 10.8h1.7M8.4 7.4 4.2 13.4",
    "handler": "M5.2 3.4v9.2l7.4-4.6z",
    "event": "M9.2 1.8 3.6 9h4.2l-1 5.2L12.4 7H8.2z",
    "env": "M2.5 4.5h1.6M7.1 4.5h6.4M2.5 8h6.4M11.9 8h1.6M2.5 11.5h3M8.5 11.5h5M5.6 3v3M10.4 6.5v3M7 10v3",
    "http": "M8 2a6 6 0 1 0 0 12A6 6 0 1 0 8 2zM2.2 8h11.6M8 2c-2.1 2.2-2.1 9.8 0 12M8 2c2.1 2.2 2.1 9.8 0 12",
    "database": "M3 4c0-1.1 2.2-2 5-2s5 .9 5 2-2.2 2-5 2-5-.9-5-2zM3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4"
                "M3 8c0 1.1 2.2 2 5 2s5-.9 5-2",
    "bucket": "M2.4 4.2c0 1 2.5 1.8 5.6 1.8s5.6-.8 5.6-1.8S11.1 2.4 8 2.4 2.4 3.2 2.4 4.2zM2.4 4.2l1.5 8.5"
              "c.2 1 1.9 1.6 4.1 1.6s3.9-.6 4.1-1.6l1.5-8.5",
    "send": "M13.8 2.2 6.9 9.1M13.8 2.2 9.6 13.8 6.9 9.1 2.2 6.4z",
}

COLUMNS = [(20, "COMES IN"), (226, "ENTRY"), (432, "CALLS"), (638, "REACHES")]
WIDTH, HEIGHT = 810, 418
BOX_W = 152
CYCLE = 3.2  # seconds a pulse takes to come round again
STEP = 0.5  # seconds between one column's pulses and the next's
DRAW_START = 0.35  # seconds before the first edge starts drawing in


@dataclass
class Node:
    id: str
    kind: str  # event, env, handler, function, aws, http
    label: str
    sub: str
    column: int
    y: int
    icon: str
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
    depth: int  # which wave of pulses it's in: 0 from the event, 1 from the handler, ...


NODES = [
    Node("event", "event", "An S3 event", "Records[] · key", 0, 70, "event"),
    Node("env", "env", "Environment", "2 variables", 0, 262, "env"),
    Node("handler", "handler", "lambda_handler()", "handler.py line 30", 1, 166, "handler", h=62),
    Node("read", "function", "read_orders()", "handler.py line 19", 2, 32, "function"),
    Node("save", "function", "Store.save()", "store.py line 16", 2, 126, "function"),
    Node("announce", "function", "announce()", "notify.py line 14", 2, 220, "function"),
    Node("chat", "function", "post_to_chat()", "notify.py line 20", 2, 326, "function", "warn"),
    Node("s3", "aws", "S3", "reads · writes", 3, 32, "bucket"),
    Node("ddb", "aws", "DynamoDB", "writes", 3, 126, "database"),
    Node("sns", "aws", "SNS", "sends", 3, 220, "send"),
    Node("web", "http", "The web", "POST · no timeout", 3, 326, "http", "warn"),
]

EDGES = [
    Edge("event", "handler", "event", 0),
    Edge("env", "save", "env", 1),
    Edge("env", "chat", "env", 1),
    Edge("handler", "read", "call", 1),
    Edge("handler", "save", "call", 1),
    Edge("handler", "announce", "call", 1),
    Edge("announce", "chat", "call", 2),
    Edge("read", "s3", "reads", 2),
    Edge("save", "ddb", "writes", 2),
    Edge("save", "s3", "writes", 2),
    Edge("announce", "sns", "sends", 2),
    Edge("chat", "web", "http", 3),
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


def _curve(edge: Edge) -> tuple[str, float, tuple[float, float], tuple[int, int]]:
    """
    The edge's path, its length, where it ends and which way it points there.
    """
    (x1, y1), (x2, y2), down = _anchors(edge)
    if down:
        c1, c2 = (x1, y1 + (y2 - y1) / 2), (x2, y1 + (y2 - y1) / 2)
    else:
        bend = (x2 - x1) * 0.5
        c1, c2 = (x1 + bend, y1), (x2 - bend, y2)
    points = []
    for i in range(41):
        t = i / 40
        x = (1 - t) ** 3 * x1 + 3 * (1 - t) ** 2 * t * c1[0] + 3 * (1 - t) * t ** 2 * c2[0] + t ** 3 * x2
        y = (1 - t) ** 3 * y1 + 3 * (1 - t) ** 2 * t * c1[1] + 3 * (1 - t) * t ** 2 * c2[1] + t ** 3 * y2
        points.append((x, y))
    length = sum(math.dist(p, q) for p, q in zip(points, points[1:]))
    d = f"M{x1:.1f},{y1:.1f}C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {x2:.1f},{y2:.1f}"
    return d, length, (x2, y2), (0, 1) if down else (1, 0)


def _head(end: tuple[float, float], direction: tuple[int, int]) -> str:
    x, y = end
    if direction == (0, 1):
        return f"M{x - 4.5:.1f},{y - 7:.1f}L{x:.1f},{y - 1:.1f}L{x + 4.5:.1f},{y - 7:.1f}"
    return f"M{x - 7:.1f},{y - 4.5:.1f}L{x - 1:.1f},{y:.1f}L{x - 7:.1f},{y + 4.5:.1f}"


def _node_svg(node: Node) -> str:
    x, y = node.x, node.y
    mono = node.kind in ("handler", "function")
    joined = [e for e in EDGES if node.id in (e.source, e.target)]
    neighbours = " ".join(f"a-{e.target if e.source == node.id else e.source}" for e in joined)
    delay = DRAW_START + node.column * 0.28
    return (f'<g class="n k-{node.kind} n-{node.id} {neighbours}{" warn" if node.tone else ""}" '
            f'data-node="{node.id}" style="--d:{delay:.2f}s">'
            f'<rect class="bg" x="{x}" y="{y}" width="{BOX_W}" height="{node.h}" rx="12"/>'
            f'<rect class="bd" x="{x + 10}" y="{y + 10}" width="26" height="26" rx="8"/>'
            f'<path class="ic" transform="translate({x + 15},{y + 15})" d="{ICONS[node.icon]}"/>'
            f'<text class="lb{" mono" if mono else ""}" x="{x + 44}" y="{y + 24}">{node.label}</text>'
            f'<text class="sb" x="{x + 44}" y="{y + 41}">{node.sub}</text>'
            + ('<circle class="wd" cx="{:.0f}" cy="{:.0f}" r="7"/><path class="wm" d="M{:.0f},{:.0f}v4.6M{:.0f},{:.0f}v.4"/>'
               .format(x + BOX_W - 2, y + 2, x + BOX_W - 2, y - 1.4, x + BOX_W - 2, y + 5.4)
               if node.tone else "")
            + "</g>")


def _edge_svg(edge: Edge, index: int, prefix: str, pulses: bool) -> str:
    d, length, end, direction = _curve(edge)
    delay = DRAW_START + 0.2 + edge.depth * 0.32
    path_id = f"{prefix}-e{index}"
    body = (f'<g class="e k-{edge.kind} s-{edge.source} t-{edge.target}" data-edge="{edge.source}>{edge.target}" '
            f'style="--len:{length:.0f};--d:{delay:.2f}s">'
            f'<path class="ln" id="{path_id}" d="{d}"/><path class="ah" d="{_head(end, direction)}"/>')
    if pulses:
        begin = 1.6 + edge.depth * STEP
        travel = 0.62  # share of the cycle a pulse spends travelling; it's hidden for the rest
        body += (f'<circle class="pl" r="3.2"><animateMotion dur="{CYCLE}s" begin="{begin:.2f}s" '
                 f'repeatCount="indefinite" keyPoints="0;1;1" keyTimes="0;{travel};1" calcMode="linear">'
                 f'<mpath href="#{path_id}"/></animateMotion>'
                 f'<animate attributeName="opacity" values="0;1;1;0;0" keyTimes="0;.08;{travel - 0.04:.2f};{travel};1" '
                 f'dur="{CYCLE}s" begin="{begin:.2f}s" repeatCount="indefinite"/></circle>')
    return body + "</g>"


def graph_svg(prefix: str, *, pulses: bool, label: str) -> str:
    """
    The whole graph as one line of inline SVG (a blank line would end the Markdown HTML block it sits in).
    """
    rules = []
    for node in NODES:
        rules.append(f".cn-graph:has(.n-{node.id}:hover) .e:not(.s-{node.id}):not(.t-{node.id}){{opacity:.08}}")
        rules.append(f".cn-graph:has(.n-{node.id}:hover) .n:not(.n-{node.id}):not(.a-{node.id}){{opacity:.3}}")
    captions = "".join(f'<text class="cap" x="{x + 2}" y="14">{text}</text>' for x, text in COLUMNS)
    edges = "".join(_edge_svg(edge, i, prefix, pulses) for i, edge in enumerate(EDGES))
    nodes = "".join(_node_svg(node) for node in NODES)
    return (f'<svg class="cn-graph" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{label}">'
            f'<style>{"".join(rules)}</style>{captions}{edges}{nodes}</svg>')


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    hero = graph_svg("hero", pulses=True, label=(
        "A code graph: an S3 event comes in, lambda_handler calls read_orders, Store.save and announce, and they reach "
        "S3, DynamoDB, SNS and the web"))
    trace = graph_svg("trace", pulses=False, label="The same graph, lit up one line of code at a time")
    (OUT / "graph-hero.svg").write_text(hero + "\n", "utf-8")
    (OUT / "graph-trace.svg").write_text(trace + "\n", "utf-8")
    print(f"wrote {OUT / 'graph-hero.svg'} and graph-trace.svg")


if __name__ == "__main__":
    main()
