"""
_Graph: a CodeGraph drawn as an SVG of cards in columns, with arrows routed between them.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from ..kit.blocks import _Report, _draws
from ..kit.fmt import _plural
from ..kit.highlight import _python_html, _python_lines
from ..kit.render import _CALL_RE, _prose
from ..kit.text import _esc

from ..analysis.findings import _short_name
from ..analysis.graph import CodeGraph, GraphEdge, GraphNode, GraphStep, GraphView
from .changes import blame_keys, blame_mark, blame_row, history_html
from .brands import AWS_LOGOS, SERVICE_LOGOS, fills, logo, small_logo
from .editor import editor_name, open_at
from .style import _ROOT


@dataclass
class _Graph:
    """
    how_it_works()'s graph: a CodeGraph drawn as boxes in columns joined by arrows. In HTML an SVG, where pointing
    at a box leaves only what it's joined to in sight, and clicking one opens its code in a panel on the right (from
    `sources`, {file: its text}; without them the boxes aren't links); in text each box with the arrows that leave it.
    """

    graph: CodeGraph
    title: str = ""
    empty: str = "(nothing to draw)"
    sources: dict[str, str] = field(default_factory=dict)
    editor: str = ""  # a link to open a line in an editor, from editor_link(): each place in a panel links to it
    views: list[GraphView] = field(default_factory=list)  # with JavaScript, a box's line of calls not drawn opens the
    # graph from that function, from these (graph_views())
    everything: CodeGraph | None = None  # ...and a button in the bar draws every function, this graph


_EDGE_WORDS = {
    "call": "calls",
    "event": "passes its input to",
    "env": "configures",
    "client": "makes the client for",
    "http": "sends HTTP requests to",
    "reads": "reads from",
    "writes": "writes to",
    "sends": "sends to",
    "runs": "calls",
    "signs": "signs links for",
}


# how_it_works()'s graph, drawn: cards with an icon badge per kind on a quiet dotted canvas, column captions, arrows that
# land on the operation (or leave from the variable) they're about, and a legend of pills. The _g names are its helpers.
_GRAPH_PAD_X = 28  # left and right of the drawing

_GRAPH_BAND = 52  # the captions' band at the top

_GRAPH_PAD_B = 32

_GRAPH_GAP, _GRAPH_GAP_EACH, _GRAPH_GAP_MAX = 84, 3, 150  # between columns: room for the arrows, wider for each arrow
# that crosses the gap, so a busy gap's curves stay gentle

_GRAPH_ROW_GAP = 34  # between boxes in a column

_GRAPH_HOP_GAP = 16  # between an arrow passing through a column and what's beside it

_GRAPH_MIN_W, _GRAPH_MAX_W, _GRAPH_MAX_IN, _GRAPH_MAX_HANDLER = 184, 284, 268, 304  # a column's width, from its boxes

_GRAPH_MAX_FLAGGED = 320  # ...or a column whose box has a line a warning is about ('ListObjectsV2  first page only')

_GRAPH_LABEL_LINE = 17  # a name too long for one line takes two

_GRAPH_HEAD, _GRAPH_HEAD_BARE = 56, 50  # a card's header (badge, name, what's under it), and without a line under it

_GRAPH_ROW = 19  # a listed line: a field, a variable, an operation

_GRAPH_PROSE = 17  # a line of prose: a docstring, what start-up does

_GRAPH_ROUTE = 28  # a web route's pill

_GRAPH_DENSE = 10  # function boxes past which a graph's boxes are compact: a line of their docstring, no when pill,
# and their calls not drawn counted, not named (all of it is in the box's card on hover)

_GRAPH_SWEEPS = 16  # passes that reorder each column by where its neighbours are, so fewer arrows cross; the order
# with the fewest crossings is kept

_GRAPH_COUNTED = 4000  # arrow segments, at most, whose crossings are counted to pick the best order (past that, the
# last pass's order, after _GRAPH_SWEEPS_BIG passes)

_GRAPH_SWEEPS_BIG = 6

_GRAPH_TALL, _GRAPH_LANES = 1800, 4  # a column taller than this is split into lanes side by side, at most this many

_GRAPH_ZOOMS = (  # the graph's zoom buttons: (key, word, said on hover); auto is checked to start
    ("auto", "Auto", "As big as it is, shrunk a little to fit the page; past that it scrolls"),
    ("fit", "Fit", "All of it in sight"),
    ("100", "100%", "As big as it is"),
    ("150", "150%", "Bigger"),
)

_GRAPH_LISTS = ("event", "env", "aws", "service", "http")  # boxes whose lines are names: fields, variables,
# operations, requests

# Arial / Helvetica advance widths (per 1000 em), what the system sans stack draws on most machines; mono is 0.6 em
_G_SANS = dict(
    zip(
        " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
        [
            278,
            278,
            355,
            556,
            556,
            889,
            667,
            191,
            333,
            333,
            389,
            584,
            278,
            333,
            278,
            278,
            *[556] * 10,
            278,
            278,
            584,
            584,
            584,
            556,
            1015,
            667,
            667,
            722,
            722,
            667,
            611,
            778,
            722,
            278,
            500,
            667,
            556,
            833,
            722,
            778,
            667,
            778,
            722,
            667,
            611,
            722,
            667,
            944,
            667,
            667,
            611,
            278,
            278,
            278,
            469,
            556,
            333,
            556,
            556,
            500,
            556,
            556,
            278,
            556,
            556,
            222,
            222,
            500,
            222,
            833,
            556,
            556,
            556,
            556,
            333,
            500,
            278,
            556,
            500,
            722,
            500,
            500,
            500,
            334,
            260,
            334,
            584,
        ],
    )
)

_G_LAMBDA = "M3.6 2.6h2.1l6 10.8h1.7M8.4 7.4 4.2 13.4"

_G_ICONS = {  # 16 x 16 line drawings, stroked in the badge's colour
    "function": _G_LAMBDA,
    "handler": "M5.2 3.4v9.2l7.4-4.6z",
    "event": "M9.2 1.8 3.6 9h4.2l-1 5.2L12.4 7H8.2z",
    "env": "M2.5 4.5h1.6M7.1 4.5h6.4M2.5 8h6.4M11.9 8h1.6M2.5 11.5h3M8.5 11.5h5M5.6 3v3M10.4 6.5v3M7 10v3",
    "start": "M8 2.2v5.2M4.9 4.4a5 5 0 1 0 6.2 0",
    "http": "M8 2a6 6 0 1 0 0 12A6 6 0 1 0 8 2zM2.2 8h11.6M8 2c-2.1 2.2-2.1 9.8 0 12M8 2c2.1 2.2 2.1 9.8 0 12",
    "cloud": "M4.6 12.6h6.9a2.8 2.8 0 0 0 .5-5.55A4 4 0 0 0 4.3 6.4a3.1 3.1 0 0 0 .3 6.2z",
    "database": "M3 4c0-1.1 2.2-2 5-2s5 .9 5 2-2.2 2-5 2-5-.9-5-2zM3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4"
    "M3 8c0 1.1 2.2 2 5 2s5-.9 5-2",
    "bucket": "M2.4 4.2c0 1 2.5 1.8 5.6 1.8s5.6-.8 5.6-1.8S11.1 2.4 8 2.4 2.4 3.2 2.4 4.2zM2.4 4.2l1.5 8.5"
    "c.2 1 1.9 1.6 4.1 1.6s3.9-.6 4.1-1.6l1.5-8.5",
    "queue": "M2 5.2h3.2v5.6H2zM6.4 5.2h3.2v5.6H6.4zM10.8 5.2H14v5.6h-3.2z",
    "send": "M13.8 2.2 6.9 9.1M13.8 2.2 9.6 13.8 6.9 9.1 2.2 6.4z",
    "key": "M10.4 2.6a3 3 0 1 1-2.2 5.1L3 12.9v1.5h1.9v-1.5h1.5v-1.5l1.8-1.8M10.9 5.1h.01",
    "spark": "M8 1.8l1.5 3.9 3.9 1.5-3.9 1.5L8 12.6 6.5 8.7 2.6 7.2l3.9-1.5zM12.6 11.2l.6 1.5 1.5.6-1.5.6-.6 1.5"
    "-.6-1.5-1.5-.6 1.5-.6z",
    "flow": "M4 2.8a1.6 1.6 0 1 0 0 3.2 1.6 1.6 0 1 0 0-3.2zM12 10a1.6 1.6 0 1 0 0 3.2 1.6 1.6 0 1 0 0-3.2z"
    "M4 6v2.4c0 1.3 1 2.3 2.3 2.3h4.1",
}

_G_SERVICE_ICONS = (  # an AWS service's box id, by what it starts with -> its icon
    (
        (
            "aws-dynamodb",
            "aws-rds",
            "aws-redshift",
            "aws-timestream",
            "aws-docdb",
            "aws-neptune",
            "aws-elasticache",
            "aws-keyspaces",
            "aws-athena",
        ),
        "database",
    ),
    (("aws-s3",), "bucket"),
    (("aws-sqs", "aws-kinesis", "aws-firehose", "aws-mq"), "queue"),
    (("aws-sns", "aws-events", "aws-ses", "aws-pinpoint", "aws-iot"), "send"),
    (("aws-secretsmanager", "aws-ssm", "aws-kms", "aws-sts", "aws-cognito", "aws-iam", "aws-acm"), "key"),
    (
        (
            "aws-bedrock",
            "aws-sagemaker",
            "aws-comprehend",
            "aws-textract",
            "aws-rekognition",
            "aws-translate",
            "aws-polly",
            "aws-transcribe",
        ),
        "spark",
    ),
    (("aws-stepfunctions", "aws-states", "aws-glue", "aws-batch", "aws-ecs", "aws-codebuild"), "flow"),
    (("aws-lambda",), "function"),
)

_G_LOOP = "M12.4 9.3A4.6 4.6 0 1 1 11.3 4.7M12.1 2.3v2.8H9.3"

_G_LOOP_MARK = "\u21bb"  # a row in a loop

_G_ACCESS = ("reads", "writes", "sends", "runs", "signs")

_G_LEGEND = (
    ("call", "calls"),
    ("reads", "reads"),
    ("writes", "writes"),
    ("sends", "sends"),
    ("runs", "runs"),
    ("http", "HTTP request"),
    ("signs", "signs links"),
    ("env", "configures"),
    ("client", "makes a client"),
)


def _g_sans(text: str, size: float, bold: bool = False) -> float:
    """
    About how wide `text` is in the sans stack, a little generous (Segoe UI, Roboto and Inter run wider).
    """
    return (
        sum(_G_SANS.get(ch) or (1000 if ch == "…" or _g_wide(ch) else 600) for ch in text)
        / 1000
        * size
        * (1.1 if bold else 1.05)
    )


def _g_mono(text: str, size: float) -> float:
    return (len(text) + sum(map(_g_wide, text))) * 0.61 * size


def _g_wide(ch: str) -> bool:
    """
    A character drawn twice as wide: Chinese, Japanese, Korean.
    """
    return unicodedata.east_asian_width(ch) in "WF"


def _g_fit(text: str, room: float, measure: Callable[[str], float]) -> str:
    """
    text, cut with … to fit `room` pixels.
    """
    if measure(text) <= room:
        return text
    while text and measure(text + "…") > room:
        text = text[:-1]
    return text.rstrip() + "…"


def _g_wrap(text: str, room: float, measure: Callable[[str], float], most: int = 2) -> list[str]:
    """
    Words in lines that fit `room`, at most `most`, the last cut with … when there's more.
    """
    words, lines, line = text.split(), [], ""
    for i, word in enumerate(words):
        trial = f"{line} {word}".strip()
        if measure(trial) <= room or not line:
            line = trial
            continue
        lines.append(line)
        line = word
        if len(lines) == most:
            line = ""
            lines[-1] = _g_fit(lines[-1] + " " + " ".join(words[i:]), room, measure)
            break
    if line:
        lines.append(line)
    return [_g_fit(x, room, measure) for x in lines[:most]]


def _g_logo_name(n: GraphNode) -> str | None:
    """
    The name of the real logo a box shows, when it has one: the one its plugin names as its icon, else its AWS
    service's ('aws-s3'), else its service's by name (Redis, PostgreSQL, OpenAI). None for a box drawn with a line
    icon.
    """
    if n.icon and logo(n.icon) is not None:
        return n.icon
    if n.kind == "aws":
        name = AWS_LOGOS.get(n.id.removeprefix("aws-"))
    elif n.kind == "service":
        name = SERVICE_LOGOS.get(n.label.lower())
    else:
        return None
    return name if name and logo(name) is not None else None


def _g_logo(n: GraphNode) -> tuple[int, int, str] | None:
    """
    The full art of the logo a box shows, or None.
    """
    name = _g_logo_name(n)
    return logo(name) if name else None


def _g_logo_svg(found: tuple[int, int, str], x: float, y: float, size: float, css: str) -> str:
    width, height, body = found
    return (
        f'<svg class="logo{" " + css if css else ""}" x="{x:g}" y="{y:g}" width="{size:g}" height="{size:g}" '
        f'viewBox="0 0 {width} {height}" fill="currentColor" aria-hidden="true">{body}</svg>'
    )


_G_BADGE = 32  # a box's badge, square: a logo needs the pixels, or its fine lines blur together on a 1x screen


def _g_badge(n: GraphNode, badge_y: float) -> str:
    """
    A box's badge: an AWS service's icon filling it, another service's logo on a white tile, else a line icon in the
    box's colour.
    """
    size = _G_BADGE
    found = _g_logo(n)
    if found is None:
        icon = 18  # the 16-unit drawings, a little larger
        return (
            f'<rect class="bdg" x="12" y="{badge_y}" width="{size}" height="{size}" rx="8"/>'
            f'<path class="ico" transform="translate({12 + (size - icon) / 2:g},{badge_y + (size - icon) / 2:g}) '
            f'scale({icon / 16:g})" d="{_G_ICONS[_g_icon(n)]}"/>'
        )
    small = small_logo(_g_logo_name(n) or "")
    if fills(found):  # AWS's: both sizes fill the badge, the small mark on a 1x screen and the full art on a 2x one
        clip = f"cn-badge-{n.id}"
        art = (
            _g_logo_svg(small, 12, badge_y, size, "lgs") + _g_logo_svg(found, 12, badge_y, size, "lgf")
            if small is not None
            else _g_logo_svg(found, 12, badge_y, size, "")
        )
        return (
            f'<clipPath id="{clip}"><rect x="12" y="{badge_y}" width="{size}" height="{size}" rx="8"/></clipPath>'
            f'<g clip-path="url(#{clip})">{art}</g>'
        )
    pad = 4
    return f'<rect class="bdg lg" x="12" y="{badge_y}" width="{size}" height="{size}" rx="8"/>' + _g_logo_svg(
        found, 12 + pad, badge_y + pad, size - 2 * pad, ""
    )


def _g_icon(n: GraphNode) -> str:
    if n.icon in _G_ICONS:
        return n.icon
    if n.kind == "aws":
        return next((icon for starts, icon in _G_SERVICE_ICONS if n.id.startswith(starts)), "cloud")
    return n.kind if n.kind in _G_ICONS else "cloud"


class _GCard:
    """
    A box of the graph being drawn: its node, its size, and what it shows in what order.
    """

    def __init__(self, node: GraphNode) -> None:
        self.node = node
        self.width = self.height = self.body = 0.0
        self.head = float(_GRAPH_HEAD)
        self.route = ""  # the web route that leads to it ('GET /orders')
        self.rows: list[str] = []  # its listed lines, in the order drawn
        self.prose: list[str] = []
        self.label: list[str] = []  # its name, in one line or two
        self.arrows = 0  # the most arrows on one of its sides: a box with many is tall enough to space them
        self.compact = False  # a function's box in a dense graph (_GRAPH_DENSE)
        self.steps: list[GraphStep] = []  # a function's box: what it does, in order, one row each (rows: their keys)
        self.opens = False  # its calls not drawn open a graph of its own (with JavaScript)

    @property
    def when(self) -> str:  # its when pill's test, if it has one
        return "" if self.compact else self.node.when

    def row_y(self, text: str) -> float | None:
        if text in self.rows:
            return self.body + 6 + _GRAPH_ROW * self.rows.index(text) + _GRAPH_ROW / 2
        return None


def _g_measure_label(n: GraphNode, text: str) -> float:
    if n.kind in ("handler", "function"):
        return _g_mono(text, 14 if n.kind == "handler" else 13.5) * 1.03
    return _g_sans(text, 14, bold=True)


def _g_need(card: _GCard) -> float:
    """
    How wide its card would like to be: its name, what's under it and its listed lines whole.
    """
    n = card.node
    need = 52 + _g_measure_label(n, n.label) + 16 + (26 if n.tone == "warn" else 0)
    if n.sub:
        whole = 52 + _g_sans(n.sub, 12.5) + 14
        if n.kind in ("handler", "function") and "/" in n.sub:  # past 190px its folder is shortened instead
            whole = min(whole, max(190.0, 52 + _g_sans(n.sub.rsplit("/", 1)[-1], 12.5) + 14))
        need = max(need, whole)
    if card.route:
        need = max(need, 16 + _g_mono(_g_route(card)[0] + _g_route(card)[2], 12.5) + 36)
    for step in card.steps:
        need = max(need, _g_step_x(step) + _g_step_width(step) + _g_tag_width(step) + 14)
    if n.kind in _GRAPH_LISTS:
        need = max(
            [need]
            + [
                28 + _g_mono(line, 12.5) + 16 + (_g_sans(n.flags[line], 12, True) + 12 if line in n.flags else 0)
                for line in n.lines
                if not line.startswith(("+", "("))
            ]
        )
    return need


def _g_route(card: _GCard) -> tuple[str, str, str]:
    """
    A route's pill: the first route the box answers, its method ('GET', or 'GET, POST') and ' +1' for the rest.
    """
    first, *rest = card.route.split("; ")
    return first, first.rpartition(" ")[0], f" +{len(rest)}" if rest else ""


def _g_cards(graph: CodeGraph) -> dict[str, _GCard]:
    cards = {n.id: _GCard(n) for n in graph.nodes}
    sides: dict[tuple[str, int], int] = defaultdict(int)
    for e in graph.edges:
        sides[(e.source, 0)] += 1
        sides[(e.target, 1)] += 1
    for (node_id, _), count in sides.items():
        if node_id in cards:
            cards[node_id].arrows = max(cards[node_id].arrows, count)
    for e in graph.edges:  # a web app's route goes on the function it leads to
        if e.kind == "call" and e.label and not e.label.startswith("line ") and not e.indirect and e.target in cards:
            cards[e.target].route = e.label
    dense = sum(n.kind in ("handler", "function") for n in graph.nodes) > _GRAPH_DENSE
    for card in cards.values():
        if card.node.kind in _GRAPH_LISTS:
            card.rows = list(card.node.lines)
        elif card.node.steps:
            card.steps = list(card.node.steps)
            card.rows = [f"\0{k}" for k in range(len(card.steps))]
        card.compact = dense and card.node.kind in ("handler", "function")
    return cards


def _g_code_lines(n: GraphNode, room: float) -> list[str]:
    """
    A function's name in one line, or in two after the dot before its own name when it's too long for one.
    """
    name = n.label
    dot = name.rfind(".", 0, name.find("(") if "(" in name else len(name))
    if dot < 1 or _g_measure_label(n, name) <= room:
        return [name]
    return [name[: dot + 1], name[dot + 1 :]]


def _g_size(cards: dict[str, _GCard], widths: dict[int, float], column_of: dict[str, int]) -> None:
    for card in cards.values():
        n = card.node
        card.width = widths[column_of[n.id]]
        room = card.width - 52 - 14 - (24 if n.tone == "warn" else 0)
        if n.kind in ("handler", "function"):  # code: broken only after its last dot ('Store.' 'save()'), else clipped
            card.label = [_g_fit(part, room, lambda t: _g_measure_label(n, t)) for part in _g_code_lines(n, room)]
        else:
            card.label = _g_wrap(n.label, room, lambda t: _g_measure_label(n, t))
        card.head = (_GRAPH_HEAD if n.sub else _GRAPH_HEAD_BARE) + _GRAPH_LABEL_LINE * (len(card.label) - 1)
        top = card.head + (_GRAPH_ROUTE if card.route else 0) + (_GRAPH_ROUTE if card.when else 0)
        card.body = top
        if n.kind in _GRAPH_LISTS and card.rows:
            card.height = top + 6 + _GRAPH_ROW * len(card.rows) + 8
        elif card.steps:  # what it does, in order, under a line or two of its docstring (none in a dense graph)
            wrapped = [part for line in n.lines for part in _g_wrap(line, card.width - 30, lambda t: _g_sans(t, 12.5))]
            card.prose = [] if card.compact else wrapped[:2]
            card.body = top + (_GRAPH_PROSE * len(card.prose) + 6 if card.prose else 0)
            card.height = card.body + 6 + _GRAPH_ROW * len(card.rows) + 6 + (_GRAPH_PROSE + 4 if card.opens else 0)
            card.height = max(card.height, 24 + 12 * card.arrows)
        elif card.compact:  # its docstring's first line, cut to fit
            card.prose = [_g_fit(n.lines[0], card.width - 30, lambda t: _g_sans(t, 12.5))] if n.lines else []
            card.height = top + (_GRAPH_PROSE * len(card.prose) + 10 if card.prose else 4)
            if n.more:
                card.height += _GRAPH_PROSE + (0 if card.prose else 8)
            card.height = max(card.height, 24 + 12 * card.arrows)
        else:
            card.prose = [
                part for line in n.lines for part in _g_wrap(line, card.width - 30, lambda t: _g_sans(t, 12.5))
            ][:3]
            card.height = top + (_GRAPH_PROSE * len(card.prose) + 10 if card.prose else 4)
            if n.more:
                card.height += _GRAPH_PROSE + (0 if card.prose else 8)
            card.height = max(card.height, 24 + 12 * card.arrows)


def _g_lanes(graph: CodeGraph, cards: dict[str, _GCard]) -> dict[str, int]:
    """
    Each box's column in the drawing, left to right from 0: its graph column, except that a column of functions (or
    of what the code reaches) taller than _GRAPH_TALL is dealt into lanes side by side, at most _GRAPH_LANES, so a wide
    codebase is drawn wide rather than as one long strip. The arrows into a far lane pass between the near lane's boxes.
    """
    _g_size(cards, {0: float(_GRAPH_MAX_W)}, {n.id: 0 for n in graph.nodes})  # about how tall each box will be
    by_column: dict[int, list[GraphNode]] = defaultdict(list)
    for n in graph.nodes:
        by_column[n.column].append(n)
    column_of, k = {}, 0
    for column in sorted(by_column):
        nodes = by_column[column]
        tall = sum(cards[n.id].height for n in nodes) + _GRAPH_ROW_GAP * (len(nodes) - 1)
        lanes = 1
        if all(n.kind in ("function", "aws", "service", "http") for n in nodes):
            lanes = max(1, min(_GRAPH_LANES, math.ceil(tall / _GRAPH_TALL), len(nodes) // 2))
        for j, n in enumerate(nodes):
            column_of[n.id] = k + j % lanes
        k += lanes
    return column_of


def _graph_layout(
    graph: CodeGraph, cards: dict[str, _GCard]
) -> tuple[
    dict[str, tuple[float, float, float, float]],
    dict[int, list[float]],
    float,
    float,
    dict[int, float],
    dict[int, float],
    dict[str, int],
]:
    """
    Where each box goes: (x, y, width, height) by its id; for each arrow that skips columns, the heights where it
    crosses the columns between (a waypoint in each, so it runs between their boxes, not behind them); the drawing's
    width and height; and each column's x and width, and each box's column. A column is as wide as its boxes want,
    within limits, and a gap as wide as the arrows through it need. Arrows that skip columns from one box (the
    environment's, start-up's), or into one, share their waypoints, so they run as one line and part near the end,
    instead of each finding its own way. A column too tall to take in is split into lanes side by side. Each column is put in the order of its neighbours' heights, a few passes
    left to right and back (the barycenter method), keeping the order where the fewest arrows cross; then each box is
    moved as near its neighbours as the boxes around it let it be.
    """
    column_of = _g_lanes(graph, cards)
    order = sorted(set(column_of.values()))
    widths = {k: 0.0 for k in range(len(order))}
    for card in cards.values():
        k = column_of[card.node.id]
        widths[k] = max(widths[k], _g_need(card))
    most = {k: float(_GRAPH_MAX_W) for k in widths}
    for n in graph.nodes:
        if n.kind in ("event", "env", "handler"):
            k = column_of[n.id]
            most[k] = max(most[k], _GRAPH_MAX_HANDLER if n.kind == "handler" else _GRAPH_MAX_IN)
        if n.kind in _GRAPH_LISTS and n.flags:  # the line a warning is about, whole beside its flag
            k = column_of[n.id]
            most[k] = max(most[k], min(_g_need(cards[n.id]), _GRAPH_MAX_FLAGGED))
    widths = {k: min(max(w, _GRAPH_MIN_W), most[k]) for k, w in widths.items()}
    _g_size(cards, widths, column_of)
    height = {n.id: cards[n.id].height for n in graph.nodes}
    columns: dict[int, list[str]] = defaultdict(list)
    for node in graph.nodes:
        columns[column_of[node.id]].append(node.id)
    skips = [(i, e) for i, e in enumerate(graph.edges) if abs(column_of[e.target] - column_of[e.source]) > 1]
    fan_out: dict[str, int] = defaultdict(int)
    fan_in: dict[str, int] = defaultdict(int)
    for _, e in skips:
        fan_out[e.source] += 1
        fan_in[e.target] += 1
    near: dict[str, list[str]] = defaultdict(list)
    hops: dict[int, list[str]] = {}
    below: dict[tuple[str, str], float] = {}  # (a function's box, what its arrow goes to first) -> how far below the
    # box's middle the arrow's row is: what a function calls is put in the order of its rows, the order its code runs
    share: dict[tuple[str, str], float] = {}  # ...and how far down the box, from 0 to 1, for counting crossings
    for i, e in enumerate(graph.edges):
        a, b = column_of[e.source], column_of[e.target]
        rows = [y for r in _g_rows(cards[e.source], e) if (y := cards[e.source].row_y(r)) is not None]
        chain = [e.source]
        if abs(b - a) > 1:  # a waypoint in each column it crosses, either way, shared with the arrows it bundles with
            step = 1 if b > a else -1
            if fan_out[e.source] > 1 and fan_out[e.source] >= fan_in[e.target]:
                key = f"~s{step}.{e.source}"
            elif fan_in[e.target] > 1:
                key = f"~t{step}.{e.target}"
            else:
                key = f"~{i}"
            hops[i] = [f"{key}.{k}" for k in range(a + step, b, step)]
            for k, hop in zip(range(a + step, b, step), hops[i]):
                if hop not in column_of:
                    columns[k].append(hop)
                    column_of[hop] = k
                    height[hop] = 4.0
            chain += hops[i]
        chain.append(e.target)
        if rows and cards[e.source].steps:
            below[(e.source, chain[1])] = sum(rows) / len(rows) - height[e.source] / 2
            share[(e.source, chain[1])] = (sum(rows) / len(rows)) / (height[e.source] + 1)
        for x, y in zip(chain, chain[1:]):
            if x != y:
                near[x].append(y)
                near[y].append(x)
    segments = {
        tuple(sorted((x, y), key=lambda item: column_of[item]))
        for x, ys in near.items()
        for y in ys
        if abs(column_of[x] - column_of[y]) == 1
    }
    by_gap: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for x, y in segments:
        by_gap[column_of[x]].append((x, y))
    center: dict[str, float] = {}
    for k in range(len(order)):
        top = 0.0
        for item in columns[k]:
            center[item] = top + height[item] / 2
            top += height[item] + _GRAPH_ROW_GAP

    def gap(x: str, y: str) -> float:
        return _GRAPH_ROW_GAP if not (x.startswith("~") or y.startswith("~")) else _GRAPH_HOP_GAP

    def settle(items: list[str], wanted: list[float]) -> None:
        """
        Each box at the height it wants, pushed down so none overlaps, then the column moved back up by how far
        it was pushed on average.
        """
        at = list(wanted)
        for j in range(1, len(items)):
            at[j] = max(
                at[j], at[j - 1] + height[items[j - 1]] / 2 + gap(items[j - 1], items[j]) + height[items[j]] / 2
            )
        shift = sum(w - a for w, a in zip(wanted, at)) / len(items)
        for item, a in zip(items, at):
            center[item] = a + shift

    def crossings() -> int:
        """
        How many pairs of arrows cross in the gaps, with the columns in their order now.
        """
        rank = {item: j for items in columns.values() for j, item in enumerate(items)}
        count = 0
        for pairs in by_gap.values():  # an arrow leaving a function's row crosses the ones from the rows below it
            ends = sorted((rank[x] + share.get((x, y), 0.0), rank[y] + share.get((y, x), 0.0)) for x, y in pairs)
            for j, (a1, b1) in enumerate(ends):
                count += sum(1 for a2, b2 in ends[j + 1 :] if a2 > a1 and b2 < b1)
        return count

    counted = len(segments) <= _GRAPH_COUNTED
    best = (crossings() if counted else 0, {k: list(v) for k, v in columns.items()}, dict(center))
    for sweep in range(_GRAPH_SWEEPS if counted else _GRAPH_SWEEPS_BIG):
        for k in range(len(order)) if sweep % 2 == 0 else range(len(order) - 1, -1, -1):
            items = columns[k]

            def pull(item: str) -> float:
                ys = [
                    center[m] + below.get((m, item), 0.0) - below.get((item, m), 0.0)
                    for m in near[item]
                    if column_of[m] != k
                ]
                return sum(ys) / len(ys) if ys else center[item]

            items.sort(key=pull)
            settle(items, [pull(item) for item in items])
        if counted and (crossed := crossings()) < best[0]:
            best = (crossed, {k: list(v) for k, v in columns.items()}, dict(center))
    if counted:
        columns.clear()
        columns.update(best[1])
        center = best[2]
    first_row: dict[str, tuple[str, float]] = {}  # a function's box -> the box that calls it first, and the row
    for e in graph.edges:
        if e.kind == "call" and cards[e.source].steps and e.target not in first_row:
            ys = [y for r in _g_rows(cards[e.source], e) if (y := cards[e.source].row_y(r)) is not None]
            if ys and column_of[e.source] < column_of[e.target]:
                first_row[e.target] = (e.source, min(ys))
    for k, items in columns.items():  # boxes one box calls, in the order of its rows: in the slots they're in
        by_caller: dict[str, list[int]] = defaultdict(list)
        for j, item in enumerate(items):
            if item in first_row:
                by_caller[first_row[item][0]].append(j)
        moved = False
        for slots in by_caller.values():
            ordered = sorted((items[j] for j in slots), key=lambda item: first_row[item][1])
            moved |= ordered != [items[j] for j in slots]
            for j, item in zip(slots, ordered):
                items[j] = item
        if moved:
            settle(items, sorted(center[item] for item in items))
    top = min(center[item] - height[item] / 2 for item in center)
    last = len(order) - 1  # a call within the last column curls round into the margin; the others, into a gap
    through: dict[int, int] = defaultdict(
        int
    )  # arrows that cross each gap (the gap after column k), counted once per line drawn
    for x, y in segments:
        through[column_of[x]] += 1
    for e in graph.edges:
        if column_of[e.source] == column_of[e.target] and column_of[e.source] < last:
            through[column_of[e.source]] += 1
    xs, x = {}, float(_GRAPH_PAD_X)
    for k in range(len(order)):
        xs[k] = x
        x += widths[k] + (min(_GRAPH_GAP + _GRAPH_GAP_EACH * through[k], _GRAPH_GAP_MAX) if k < last else 0)
    boxes = {
        n.id: (
            xs[column_of[n.id]],
            center[n.id] - height[n.id] / 2 - top + _GRAPH_BAND,
            widths[column_of[n.id]],
            height[n.id],
        )
        for n in graph.nodes
    }
    routes = {i: [center[hop] - top + _GRAPH_BAND for hop in chain] for i, chain in hops.items()}
    loops = 64 if any(column_of[e.source] == column_of[e.target] == last for e in graph.edges) else 0
    width = x + _GRAPH_PAD_X + loops
    tall = (
        max(max(y + h for _, y, _, h in boxes.values()), max((y for ys in routes.values() for y in ys), default=0))
        + _GRAPH_PAD_B
    )
    return boxes, routes, width, tall, xs, widths, column_of


def _g_names(e: GraphEdge) -> list[str]:
    return [part for part in e.label.split(", ") if part]


def _g_rows(card: _GCard, e: GraphEdge) -> list[str]:
    """
    The rows of its box an arrow leaves from or lands on: the variables it carries, the operations it calls (the
    '+3 more' row for one that isn't listed); none for the event as a whole or a client.
    """
    if card.steps:  # a function's: the rows of the calls it leaves from (through a function not drawn, that one's)
        if card.node.id != e.source or e.kind in ("event", "env", "client"):
            return []
        hit = [
            key
            for key, step in zip(card.rows, card.steps)
            if (step.target == e.target and step.kind == e.kind) or (e.indirect and e.target in step.leads)
        ]
        if not hit and e.indirect and card.steps[-1].kind == "more":
            hit = [card.rows[-1]]
        return hit
    if card.node.kind not in _GRAPH_LISTS or e.kind in ("event", "client"):
        return []
    if e.label in card.rows:
        return [e.label]
    hit = [r for r in card.rows if f", {r}, " in f", {e.label}, "]
    if not hit and any(r.startswith("+") for r in card.rows):
        hit = [r for r in card.rows if r.startswith("+")]
    return [r for r in hit if card.row_y(r) is not None]


def _g_anchors(
    graph: CodeGraph, cards: dict[str, _GCard], boxes: dict[str, tuple[float, float, float, float]]
) -> dict[int, tuple[list[float], list[float]]]:
    """
    Where each arrow leaves and arrives, as heights on the page: from the rows of the variables it carries, to the
    rows of the operations or requests it makes; otherwise spread down the box's side in the order of what's at the
    other end, outgoing arrows and incoming ones on separate parts of a side they share. Rows are first put in the
    order of what they're joined to, so arrows cross less.
    """

    def middle(node_id: str) -> float:
        return boxes[node_id][1] + boxes[node_id][3] / 2

    rows_for = _g_rows
    joined: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for e in graph.edges:
        for here, there in ((e.source, e.target), (e.target, e.source)):
            for row in rows_for(cards[here], e):
                joined[here][row].append(middle(there))
    for node_id, by_row in joined.items():
        if cards[node_id].steps:  # a function's rows are in the order its code runs: never moved
            continue
        rank = {row: sum(ys) / len(ys) for row, ys in by_row.items()}
        cards[node_id].rows.sort(key=lambda r: (r.startswith("+"), rank.get(r, 1e9)))

    ends: dict[int, list[list[float]]] = {}
    loose: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)  # (node, side of the box) -> (edge, end)
    for i, e in enumerate(graph.edges):
        pair: list[list[float]] = []
        for end, node_id in ((0, e.source), (1, e.target)):
            card = cards[node_id]
            ys = [boxes[node_id][1] + y for r in rows_for(card, e) if (y := card.row_y(r)) is not None]
            if not ys:  # which side of the box the arrow touches there: right, unless it arrives from the left
                forward = boxes[e.target][0] > boxes[e.source][0]
                side = (
                    "left"
                    if (end == 1 and forward) or (end == 0 and boxes[e.target][0] < boxes[e.source][0])
                    else "right"
                )
                loose[(node_id, side)].append((i, end))
            pair.append(ys)
        ends[i] = pair

    def other(i: int, end: int) -> float:
        far = ends[i][1 - end]
        e = graph.edges[i]
        return sum(far) / len(far) if far else middle(e.target if end == 0 else e.source)

    for (node_id, _), items in loose.items():
        card, (_, y, _, h) = cards[node_id], boxes[node_id]
        items.sort(key=lambda item: (item[1], other(*item)))  # arrivals above departures on a shared side
        if card.node.kind in _GRAPH_LISTS:  # at the name: the event as a whole, a client made for the service
            hub, room = y + 27, 22.0
        else:
            hub, room = y + h / 2, h - 22
        step = min(12.0, room / max(len(items), 1))
        for k, (i, end) in enumerate(items):
            ends[i][end] = [hub + (k - (len(items) - 1) / 2) * step]
    shared: dict[tuple[str, int, float], list[int]] = defaultdict(list)  # arrows that share a row's port
    for i, e in enumerate(graph.edges):
        for end, node_id in ((0, e.source), (1, e.target)):
            for y in ends[i][end]:
                shared[(node_id, end, round(y, 1))].append(i)
    for (node_id, end, y), edges in shared.items():
        edges = [i for i in edges if graph.edges[i].kind != "env"]  # the environment's leave as one line, then part
        if len(edges) > 1 and end == 0:  # leaving one row: side by side, within the row (arriving: one head)
            edges.sort(key=lambda i: other(i, end))
            step = min(5.0, (_GRAPH_ROW - 6) / (len(edges) - 1))
            for k, i in enumerate(edges):
                ends[i][end] = [v + (k - (len(edges) - 1) / 2) * step if round(v, 1) == y else v for v in ends[i][end]]
    return {i: (pair[0], pair[1]) for i, pair in ends.items()}


def _g_cubic(
    p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float], t: float
) -> tuple[float, float]:
    u = 1 - t
    x, y = (u**3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t**3 * d for a, b, c, d in zip(p0, p1, p2, p3))
    return x, y


def _g_spots(curve: tuple[tuple[float, float], ...]) -> list[tuple[float, float]]:
    return [_g_cubic(*curve, t) for t in (0.5, 0.3, 0.7, 0.18, 0.82)]  # type: ignore[arg-type]


def _g_strand(points: list[tuple[float, float]]) -> tuple[str, list[tuple[float, float]]]:
    """
    One line through `points`: (start, then a column's left and right for each column it skips, then the end).
    Curves in the gaps, straight across each column it skips; returns the path and where its marks can go, the best
    first: along its middle straight run, in the clear between a column's boxes, or else along its curve.
    """
    (x1, y1) = points[0]
    parts: list[str] = [f"M{x1:.1f},{y1:.1f}"]
    runs: list[tuple[float, float, float]] = []
    curve: tuple[tuple[float, float], ...] = ()
    for j in range(1, len(points)):
        (ax, ay), (bx, by) = points[j - 1], points[j]
        if j % 2 == 0 and j < len(points) - 1:
            parts.append(f"L{bx:.1f},{by:.1f}")
            runs.append((ax, bx, by))
            continue
        reach = max(18.0, abs(bx - ax) * 0.5) * (1 if bx >= ax else -1)
        parts.append(f"C{ax + reach:.1f},{ay:.1f} {bx - reach:.1f},{by:.1f} {bx:.1f},{by:.1f}")
        curve = curve or ((ax, ay), (ax + reach, ay), (bx - reach, by), (bx, by))
    if not runs:
        return " ".join(parts), _g_spots(curve)
    ax, bx, y = runs[(len(runs) - 1) // 2]
    middle, d = (ax + bx) / 2, (1 if bx >= ax else -1)
    return " ".join(parts), [(middle + k * 19 * d, y) for k in (0, 1, -1, 2, -2) if abs(k * 19) < abs(bx - ax) / 2 - 9]


def _g_head(x: float, y: float, d: int) -> str:
    """
    A slim arrowhead with a notched back, its tip at (x, y), pointing right (d=1) or left (d=-1).
    """
    return f"M{x:.1f},{y:.1f} L{x - 9 * d:.1f},{y - 4.4:.1f} Q{x - 6.2 * d:.1f},{y:.1f} {x - 9 * d:.1f},{y + 4.4:.1f} Z"


def _g_edge_tip(e: GraphEdge, graph: CodeGraph) -> str:
    """
    What an arrow says on hover, in a sentence.
    """
    source, target = graph.node(e.source), graph.node(e.target)
    src = source.label if source else e.source
    dst = target.label if target else e.target
    if e.kind == "event":
        said = f"{dst} is called with its input"
    elif e.kind == "env":
        said = f"{dst} reads {e.label} from its environment"
    elif e.kind == "call":
        said = f"{src} calls {dst}" + (f" ({e.label})" if e.label else "") + (f", only when {e.when}" if e.when else "")
    elif e.kind == "client":
        said = f"{src} makes the {dst} client"
    elif e.kind == "http":
        said = f"{src} sends {e.label}"
    else:
        said = f"{src} {_EDGE_WORDS.get(e.kind, e.kind)} {dst}: {e.label}"
    said += "; in a loop, once per item" if e.loop else ""
    said += "; known only by the methods' names (their client couldn't be followed)" if e.guessed else ""
    said += "; in functions further down that the graph leaves out" if e.indirect and e.kind != "call" else ""
    return said + ("; a warning is about it" if e.tone == "warn" else "")


def _edge_svg(
    e: GraphEdge,
    graph: CodeGraph,
    boxes: dict[str, tuple[float, float, float, float]],
    xs: dict[int, float],
    widths: dict[int, float],
    column_of: dict[str, int],
    ys_out: list[float],
    ys_in: list[float],
    hops: list[float] | None,
    mark_loop: bool = True,
    hot: set[tuple[int, int]] | None = None,
    taken: list[tuple[float, float]] | None = None,
    lane: int = 0,
    lit: list[str] | None = None,
) -> tuple[str, str]:
    """
    An arrow: its lines (one from each row it leaves to each row it reaches), its head, its loop mark; and, drawn
    over the boxes, the dots where it leaves them. A warned arrow's glow and ! go on the lines in `hot` (by the index
    of the row each leaves and reaches), or on all of them. Its marks go on its line, clear of the marks in `taken`
    (other arrows'), which they're added to; `lane` puts a call within a column outside the ones drawn before it.
    `lit` names the boxes that, pointed at, leave it in sight (from _g_lineage()).
    """
    sx, _, sw, _ = boxes[e.source]
    tx, _, tw, _ = boxes[e.target]
    lines: list[str] = []
    spots: list[tuple[float, float]] = []  # where its marks can go, along its first line (or the first one warned)
    start, end = column_of[e.source], column_of[e.target]
    if end > start:  # left to right: from the source's right side to the target's left side
        x1, tip, d = sx + sw, tx - 0.6, 1
        between = [(xs[start + 1 + k], xs[start + 1 + k] + widths[start + 1 + k], y) for k, y in enumerate(hops or [])]
    elif end < start:  # back to an earlier column: from the source's left side to the target's right side
        x1, tip, d = sx, tx + tw + 0.6, -1
        between = [(xs[start - 1 - k] + widths[start - 1 - k], xs[start - 1 - k], y) for k, y in enumerate(hops or [])]
    else:  # the same column: out of the right side, round, and back into the target's right side
        x1, tip, d = sx + sw, tx + tw + 0.6, -1
        between = []
    warned: list[str] = []
    for ia, a in enumerate(ys_out):
        for ib, b in enumerate(ys_in):
            if end == start:
                bulge = 34 + 16 * lane + 8 * len(lines)
                curve = ((x1, a), (x1 + bulge, a), (tip + 6.6 + bulge, b), (tip + 6.6, b))
                path = "M{:.1f},{:.1f} C{:.1f},{:.1f} {:.1f},{:.1f} {:.1f},{:.1f}".format(
                    *(v for p in curve for v in p)
                )
                at = _g_spots(curve)
            else:
                points = (
                    [(x1, a)] + [(p, y) for left, right, y in between for p in (left, right)] + [(tip - 6.6 * d, b)]
                )
                path, at = _g_strand(points)
            lines.append(path)
            spots = spots or at
            if e.tone == "warn" and (hot is None or (ia, ib) in hot):
                if not warned:  # the marks go on the first line the warning is about
                    spots = at
                warned.append(path)
    heads = [_g_head(tip, b, d) for b in dict.fromkeys(ys_in)]
    d_attr = " ".join(lines)
    classes = (
        f"ce ek-{_esc(e.kind)} s-{_esc(e.source)} t-{_esc(e.target)}"
        + (" warn" if e.tone == "warn" else "")
        + (" guess" if e.guessed else "")
        + (" via" if e.indirect else "")
        + "".join(f" l-{_esc(m)}" for m in lit or [e.source, e.target])
    )
    taken = [] if taken is None else taken

    def place() -> tuple[float, float]:  # the first spot clear of every mark drawn so far
        at = next((p for p in spots if all(math.dist(p, q) >= 17.5 for q in taken)), spots[0])
        taken.append(at)
        return at

    mark = ""
    if spots and e.tone == "warn":
        cx, cy = place()
        mark += (
            f'<g class="wm" transform="translate({cx:.1f},{cy:.1f})"><circle r="7.5"/>'
            '<path d="M0,-3.7V.5M0,3.4V3.5"/></g>'
        )
    if spots and e.loop and mark_loop:
        cx, cy = place()
        mark += (
            f'<g class="lpb" transform="translate({cx:.1f},{cy:.1f})"><circle r="8.5"/>'
            f'<path transform="scale(.66) translate(-8,-8)" d="{_G_LOOP}"/></g>'
        )
    halo = (
        f'<path class="halo" d="{" ".join(warned)}"/><path class="cs" d="{" ".join(warned)}"/>'  # amber, edged
        if warned
        else ""
    )
    body = (
        f'<g class="{classes}"><title>{_esc(_g_edge_tip(e, graph))}</title><path class="hit" d="{d_attr}"/>{halo}'
        f'<path class="ln" d="{d_attr}"/>' + "".join(f'<path class="ah" d="{h}"/>' for h in heads) + mark + "</g>"
    )
    dots = (
        f'<g class="{classes} pt">'
        + "".join(f'<circle cx="{x1:.1f}" cy="{y:.1f}" r="2.8"/>' for y in dict.fromkeys(ys_out))
        + "</g>"
    )
    return body, dots


def _g_sub_svg(n: GraphNode, room: float) -> str:
    if n.kind in ("handler", "function") and "/" in n.sub:  # the folder dimmed, shortened from the left
        folder, _, rest = n.sub.rpartition("/")
        folder += "/"
        if _g_sans(rest, 12.5) > room:
            return _esc(_g_fit(rest, room, lambda t: _g_sans(t, 12.5)))
        if _g_sans(folder + rest, 12.5) > room:  # whole folders dropped from the left: '…/orders.py line 10'
            parts = folder.rstrip("/").split("/")
            while parts and _g_sans("…/" + "/".join(parts) + "/" + rest, 12.5) > room:
                parts.pop(0)
            folder = "…/" + ("/".join(parts) + "/" if parts else "")
            if not parts and _g_sans(folder + rest, 12.5) > room:
                folder = ""
        return (f'<tspan class="dir">{_esc(folder)}</tspan>' if folder else "") + _esc(rest)
    if (
        n.kind in ("aws", "service") and n.sub
    ):  # 'reads · writes', each in its arrows' colour, cut with … when they don't fit
        words = n.sub.split(" · ")
        shown = list(words)
        while len(shown) > 1 and _g_sans(" · ".join(shown) + (" · …" if shown != words else ""), 12.5, True) > room:
            shown.pop()
        return '<tspan class="sep"> · </tspan>'.join(
            [f'<tspan class="ac ek-{_esc(w)}">{_esc(w)}</tspan>' for w in shown] + (["…"] if shown != words else [])
        )
    return _esc(_g_fit(n.sub, room, lambda t: _g_sans(t, 12.5)))


def _g_calls(count: int) -> str:
    return f"{count} call" if count == 1 else f"{count} calls"


def _g_prose_top(card: _GCard) -> float:
    """
    Where a box's prose starts: under its header, its route's pill and its when pill.
    """
    return card.head + (_GRAPH_ROUTE if card.route else 0) + (_GRAPH_ROUTE if card.when else 0)


def _g_more_y(card: _GCard) -> float:
    """
    The baseline of a box's line of calls not drawn.
    """
    if card.steps:
        return card.body + 6 + _GRAPH_ROW * len(card.rows) + 17
    return _g_prose_top(card) + 13 + _GRAPH_PROSE * len(card.prose)


def _g_step_x(step: GraphStep) -> float:
    """
    Where a row's text starts: past its number, indented for the loops and ifs around it, and past a dot for what it
    reaches.
    """
    return 34 + 12 * min(step.depth, 4) + (10 if step.kind not in ("call", "more") else 0)


def _g_step_width(step: GraphStep) -> float:
    return _g_mono(step.text, 12.5) if step.kind != "more" else _g_sans(step.text, 12.5)


def _g_tag(step: GraphStep) -> str:  # said at a row's right: in a loop, under an if
    return " ".join(([_G_LOOP_MARK] if step.loop else []) + (["if"] if step.when else []))


def _g_tag_width(step: GraphStep) -> float:
    tag = _g_tag(step)
    return _g_sans(tag, 11) + 10 if tag else 0


def _g_step_tip(step: GraphStep) -> str:
    """
    What a row says on hover: what it does and where, and why it may run more than once or not at all.
    """
    said = f"{step.text}, line {step.line}"
    if step.when:
        said += f", only when {step.when}"
    if step.loop:
        said += ", in a loop: once per item"
    if step.kind == "call" and not step.target:
        said += "; not drawn"
    return said


def _g_steps_svg(card: _GCard, w: float) -> list[str]:
    """
    A function's rows: what it does in the order its code does it, numbered, indented for the loops and ifs around
    each, a dot in its arrow's colour for what it reaches, ↻ for a loop and 'if' for a call made only sometimes. A
    call to a function not drawn is dimmed.
    """
    parts = [f'<path class="dv" d="M1,{card.body:.0f}H{w - 1:.0f}"/>']
    number = 0
    for key, step in zip(card.rows, card.steps):
        ry = card.row_y(key)
        if ry is None:
            continue
        if step.kind == "more":
            parts.append(f'<text class="rw mo" x="34" y="{ry + 4.3:.1f}">{_esc(step.text)}</text>')
            continue
        number += 1
        x = _g_step_x(step)
        tag = _g_tag(step)
        room = w - x - 14 - _g_tag_width(step)
        row = [
            f"<title>{_esc(_g_step_tip(step))}</title>",
            f'<text class="rn" x="14" y="{ry + 4.3:.1f}">{number}</text>',
        ]
        if step.kind != "call":
            row.append(f'<circle class="bu ac ek-{_esc(step.kind)}" cx="{x - 6:.1f}" cy="{ry:.1f}" r="2.6"/>')
        row.append(
            f'<text class="rw" x="{x:.1f}" y="{ry + 4.3:.1f}">{_esc(_g_fit(step.text, room, lambda t: _g_mono(t, 12.5)))}'
            "</text>"
        )
        if tag:
            row.append(f'<text class="tg" x="{w - 12:.0f}" y="{ry + 4:.1f}" text-anchor="end">{_esc(tag)}</text>')
        drawn = step.kind != "call" or bool(step.target)
        parts.append(f'<g class="sr{"" if drawn else " off"}">{"".join(row)}</g>')
    return parts


def _g_off_rows(card: _GCard) -> list[float]:
    """
    The baselines of a function's rows of calls to functions not drawn.
    """
    return [
        y + 4.3
        for key, step in zip(card.rows, card.steps)
        if step.kind == "call" and not step.target and (y := card.row_y(key)) is not None
    ]


def _node_svg(
    card: _GCard,
    box: tuple[float, float, float, float],
    neighbours: list[str],
    access: dict[str, str],
    panel: str = "",
    opens: bool = False,
) -> str:
    """
    A box: its badge and name, what's under it, a route's pill, its listed lines (an operation's dot in its arrows'
    colour, a line a warning is about with its flag) or its docstring, and a warning badge. panel is the id of its
    code's panel, and opens says its line of calls not drawn opens a graph of its own (a link drawn over it).
    """
    n = card.node
    x, y, w, h = box
    warn = n.tone == "warn"
    label_y = 27 if n.sub else 31
    parts = [
        f'<text class="lb" x="52" y="{label_y + _GRAPH_LABEL_LINE * k}">{_esc(line)}</text>'
        for k, line in enumerate(card.label)
    ]
    if n.sub:
        parts.append(
            f'<text class="sb" x="52" y="{45 + _GRAPH_LABEL_LINE * (len(card.label) - 1)}">'
            f"{_g_sub_svg(n, w - 52 - 12)}</text>"
        )
    badge_y = 11 if n.sub else 9
    parts.append(_g_badge(n, badge_y))
    top = card.head
    if card.route:
        first, method, more = _g_route(card)
        path = first[len(method) + 1 :]
        pill_w = min(_g_mono(first + more, 12.5) + 20, w - 28)
        shown = _g_fit(path, pill_w - 20 - _g_mono(method + " " + more, 12.5), lambda t: _g_mono(t, 12.5))
        parts.append(
            f'<g class="rt"><rect x="14" y="{top:.0f}" width="{pill_w:.0f}" height="21" rx="10.5"/>'
            f'<text x="24" y="{top + 14.8:.1f}"><tspan class="mt">{_esc(method)}</tspan> {_esc(shown)}'
            f"{_esc(more)}</text></g>"
        )
        top += _GRAPH_ROUTE
    if card.when:  # called only under an if: its test, in a pill like a route's
        test = _g_fit(n.when, w - 28 - 20 - _g_mono("when ", 12.5), lambda t: _g_mono(t, 12.5))
        pill_w = _g_mono("when " + test, 12.5) + 20
        parts.append(
            f'<g class="rt wh"><rect x="14" y="{top:.0f}" width="{pill_w:.0f}" height="21" rx="10.5"/>'
            f'<text x="24" y="{top + 14.8:.1f}"><tspan class="ww">when </tspan>{_esc(test)}</text></g>'
        )
        top += _GRAPH_ROUTE
    if n.kind in _GRAPH_LISTS and card.rows:
        parts.append(f'<path class="dv" d="M1,{card.body:.0f}H{w - 1:.0f}"/>')
        for row in card.rows:
            ry = card.row_y(row)
            if ry is None:
                continue
            if row.startswith("(") or (row.startswith("+") and row.endswith(" more")):
                parts.append(f'<text class="rw mo" x="16" y="{ry + 4.3:.1f}">{_esc(row)}</text>')
                continue
            tone = (" ac ek-" + _esc(access[row])) if n.kind in ("aws", "service") and row in access else ""
            flag = n.flags.get(row, "")
            room = w - 28 - 14 - (_g_sans(flag, 12, True) + 12 if flag else 0)
            parts.append(
                f'<circle class="bu{tone}{" flagged" if flag else ""}" cx="17" cy="{ry:.1f}" r="2.6"/>'
                f'<text class="rw" x="27" y="{ry + 4.3:.1f}">{_esc(_g_fit(row, room, lambda t: _g_mono(t, 12.5)))}'
                "</text>"
            )
            if flag:
                parts.append(
                    f'<text class="ns" x="{w - 14:.0f}" y="{ry + 4.3:.1f}" text-anchor="end">{_esc(flag)}</text>'
                )
    for k, line in enumerate(card.prose):
        parts.append(f'<text class="pr" x="14" y="{top + 13 + _GRAPH_PROSE * k:.1f}">{_esc(line)}</text>')
    if card.steps:
        parts += _g_steps_svg(card, w)
        if card.opens:  # with JavaScript, a link to the graph of every call it makes
            parts.append(f'<text class="pr mo md opn" x="14" y="{_g_more_y(card):.1f}">Open its calls \u203a</text>')
    elif n.more:
        said = f"+{_g_calls(len(n.more))} not drawn"
        for k in range(0 if card.compact else len(n.more), 0, -1):  # as many of their names as fit whole, the rest …
            names = ", ".join(n.more[:k]) + (", …" if k < len(n.more) else "")
            if _g_sans(f"{said}: {names}", 12.5) <= w - 28:
                said = f"{said}: {names}"
                break
        parts.append(f'<text class="pr mo md" x="14" y="{_g_more_y(card):.1f}">{_esc(said)}</text>')
    if warn:
        parts.append(
            f'<g class="wb" transform="translate({w - 21:.0f},{badge_y + _G_BADGE / 2:.0f})"><circle r="8.5"/>'
            '<path d="M0,-4.2V.6M0,3.9V4"/></g>'
        )
    classes = " ".join(
        ["cn", f"k-{n.kind}", f"n-{n.id}", *(f"a-{m}" for m in neighbours)]
        + ([f"p-{panel}"] if panel else [])
        + (["hd"] if opens else [])
        + (["warn"] if warn else [])
    )
    return (
        f'<g class="{_esc(classes)}" transform="translate({x:.1f},{y:.1f})">'
        f'<rect class="bg" width="{w:.0f}" height="{h:.0f}" rx="11"/>'
        f'<rect class="fg" x=".5" y=".5" width="{w - 1:.0f}" height="{h - 1:.0f}" rx="10.5"/>{"".join(parts)}</g>'
    )


_G_PANEL_LINES = 400  # lines of one function a box's panel shows, at most

_G_PANEL_SPANS = 12  # places a box's panel shows, at most

_G_PANEL_KINDS = {
    "event": "What comes in",
    "env": "Environment",
    "start": "At import",
    "handler": "Entry point",
    "function": "Function",
    "aws": "AWS service",
    "service": "Service",
    "http": "HTTP",
}


_G_GEAR = (  # the panel's settings
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/>'
    '<path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21'
    "a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 "
    "1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1"
    "a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1"
    'a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>'
    "</svg>"
)


def _g_panel_id(n: GraphNode) -> str:
    return f"cn-code-{n.id}"


def _g_filled(line: str) -> bool:
    """
    Whether a coloured line has anything on it.
    """
    return bool(re.sub(r"<[^>]*>", "", line).strip())


def _g_panel(n: GraphNode, lines_of: Callable[[str], list[str]], editor: str = "", panel: str = "") -> str:
    """
    A box's code, in a panel that slides in from the right when the box is clicked (its id, panel or the box's own, is
    the link's target, so it's CSS's :target that opens it): what the box is, then each place it's about with its
    lines numbered, the lines worth pointing at lit. A function's lines each say who changed them last and when, and
    its last row what git says about it, when the folder is in git. '' when none of its code is in the files read.
    """
    history = n.history if n.history and n.history.lines else None
    keys = blame_keys(history) if history else {}
    places = []  # (file, first line, last line, lines left out, the editor's link, its rows)
    for span in n.code[:_G_PANEL_SPANS]:
        lines = lines_of(span.file)
        start, end = max(1, span.start), min(len(lines), span.end)
        if n.kind in ("handler", "function"):  # its decorators, over its def
            while start > 1 and lines[start - 2].lstrip().startswith("@"):
                start -= 1
        while start < end and start not in span.lit and not _g_filled(lines[start - 1]):
            start += 1
        while end > start and end not in span.lit and not _g_filled(lines[end - 1]):
            end -= 1
        if start > end:
            continue
        more = end - start + 1 - _G_PANEL_LINES
        end = min(end, start + _G_PANEL_LINES - 1)
        rows, above = [], ""
        for k in range(start, end + 1):
            mark = ""
            if history:
                commit = history.lines.get(k)
                said = commit.sha if commit else "u" if k in history.lines else ""  # the commit, to say it once a run
                mark = blame_mark(history, k, keys, bool(said) and said == above)
                above = said
            rows.append(
                f'<span class="sl{" lit" if k in span.lit else ""}">{mark}<span class="sn">{k}</span>'
                f'<span class="sc">{lines[k - 1]}</span></span>'
            )
        places.append((span.file, start, end, more, open_at(editor, span.file, min(span.lit, default=start)), rows))
    if not places:
        return ""

    def opens(href: str) -> str:
        return f'<a class="ced" href="{_esc(href)}">Open in {_esc(editor_name(editor))}</a>' if href else ""

    shown = []
    for file, start, end, more, href, rows in places:
        if len(places) > 1:  # one place is in the panel's head
            where = f"line {start}" if start == end else f"lines {start}–{end}"
            shown.append(f'<div class="csw">{_esc(file)} <span>{where}</span>{opens(href)}</div>')
        shown.append(
            f'<pre class="csc{" blame" if history else ""}">{"".join(rows)}</pre>'
            + (f'<div class="csm">+{_plural(more, "more line")}</div>' if more > 0 else "")
        )
    rest = len(n.code) - _G_PANEL_SPANS
    if rest > 0:
        shown.append(f'<div class="csm">+{_plural(rest, "more place")}: the tables below list them all</div>')
    mono = n.kind in ("handler", "function")
    said = []
    for line in (n.tip or "").split("\n"):
        if not line or (n.more and line.startswith("It calls ") and "the graph leaves out" in line):
            continue  # not the calls this graph leaves out: a function's panel is the same in every graph it's in
        if mono and not said:  # 'name(args) in file, 3 lines: its doc': its def is the code's first line
            head = re.fullmatch(r".+? in .+?, \d+ lines?(?:: (.*))?", line)
            if head:
                line = head.group(1) or ""
        if line:
            said.append(f'<p class="csd">{_prose(line)}</p>')
    about = [_esc(_G_PANEL_KINDS.get(n.kind, n.kind))] + ([_esc(n.sub)] if n.sub else [])
    if len(places) == 1 and places[0][4]:
        about.append(opens(places[0][4]))
    key = panel or _g_panel_id(n)
    opens_bar = bar = gear = ""
    if history:  # its settings: a bar under its head that the gear opens, the checkbox before it so CSS can
        opens_bar = f'<input type="checkbox" class="cso" id="{_esc(key)}-set" aria-label="Settings">'
        gear = f'<label class="csx csgr" for="{_esc(key)}-set" title="Settings">{_G_GEAR}</label>'
        bar = (
            '<div class="csob"><label><input type="checkbox" class="csg" checked> '
            "Who changed each line, from git</label></div>"
        )
    return (
        f'<aside class="cside" id="{_esc(key)}" aria-label="{_esc("The code of " + n.label)}">{opens_bar}'
        f'<div class="csh"><div class="cst"><b class="csn{" mono" if mono else ""}">{_esc(n.label)}</b>'
        f'<span class="css">{" · ".join(about)}</span></div>{gear}'
        f'<a class="csx" href="#cn-closed" aria-label="Close" title="Close">×</a></div>{bar}'
        f"{''.join(said)}{''.join(shown)}{blame_row(history, keys) if history else ''}</aside>"
    )


_G_TIP_W = 420  # a box's hover card, wide

_G_TIP_SIGNATURE = 6  # lines of a def its hover card shows, at most

_G_TIP_WARNING = "A warning is about it: "

# a name in the card's sentences worth setting as code: a dotted or keyed path (Records[].s3.bucket.name,
# book:{book_id}, s3:GetObject, orders/handler.py) or a variable in capitals (DB_HOST)
_G_CODE_RE = re.compile(
    r"(?<![\w.\-/])([A-Za-z_][\w\-]*(?:[.:/]+[\w{}\-]+|\[\]|\{\w*\})+|[A-Z][A-Z0-9]*_[A-Z0-9_]*[A-Z0-9])(?![\w{])"
)


def _g_tip_text(text: str) -> str:
    """
    One of the card's sentences as HTML, its calls coloured as Python and its names set as code, every piece escaped.
    """
    out = []
    for i, piece in enumerate(_CALL_RE.split(text)):
        if i % 2:
            out.append(f'<code class="ctk">{_python_html(piece)}</code>')
            continue
        for k, part in enumerate(_G_CODE_RE.split(piece)):
            out.append(f'<code class="ctk ctn">{_esc(part)}</code>' if k % 2 else _esc(part))
    return "".join(out)


def _g_tip_item(item: str) -> str:
    """
    One thing a service box lists, for its card: 'PutItem (dynamodb:PutItem)' as the operation in code and what it
    needs beside it.
    """
    m = re.fullmatch(r"(.+?) \((.+)\)", item)
    if not m:
        return f'<li><code class="ctk ctn">{_esc(item)}</code></li>'
    return (
        f'<li><code class="ctk ctn">{_esc(m.group(1))}</code> <span class="ctm">{_g_tip_text(m.group(2))}</span></li>'
    )


def _g_tip_signature(n: GraphNode, lines_of: Callable[[str], list[str]]) -> list[str]:
    """
    A function's def as it's written, in colour: its decorators and the lines up to the colon that opens its body.
    [] when its file wasn't read.
    """
    if not n.code:
        return []
    span = n.code[0]
    lines = lines_of(span.file)
    if not lines or span.start > len(lines):
        return []
    start = span.start
    while start > 1 and lines[start - 2].lstrip().startswith("@"):
        start -= 1
    shown = []
    for k in range(start, min(len(lines), span.end, start + _G_TIP_SIGNATURE - 1) + 1):
        shown.append(lines[k - 1])
        if k >= span.start and re.sub(r"<[^>]*>", "", lines[k - 1]).rstrip().endswith(":"):
            break
    indent = min((len(line) - len(line.lstrip(" ")) for line in shown if line.strip()), default=0)
    return [line[indent:] for line in shown]


def _g_tip(n: GraphNode, lines_of: Callable[[str], list[str]], opens: bool) -> tuple[str, float]:
    """
    What a box says on hover, as a card: what kind of box it is and its name, a function's def in colour and its
    docstring, then the rest of its words with the code in them set as code, its warnings apart, and when it has a
    panel (opens), that a click shows its code. With how tall it is likely to be, to pick whether it goes under the
    box or over it.
    """
    said = [line for line in (n.tip or n.label).split("\n") if line]
    warnings = [w for line in said if line.startswith(_G_TIP_WARNING) for w in line[len(_G_TIP_WARNING) :].split("; ")]
    said = [line for line in said if not line.startswith(_G_TIP_WARNING)]
    mono = n.kind in ("handler", "function")
    body, tall, sub = [], 80.0 + (20 if n.sub else 0), n.sub
    if mono and said and _CALL_RE.match(said[0]) and " in " in said[0]:  # 'name(args) in file, 3 lines: its doc'
        head = said.pop(0)
        signature = _g_tip_signature(n, lines_of) or [_python_html(head.split(" in ", 1)[0])]
        body.append(f'<pre class="ctc">{chr(10).join(signature)}</pre>')
        tall += 21 * len(signature) + 34
        lines = re.search(r", (\d+ lines?)", head)
        sub = f"{n.sub} · {lines.group(1)}" if lines and n.sub else sub
        if n.lines and n.lines[0]:
            body.append(f'<p class="ctd">{_g_tip_text(n.lines[0])}</p>')
            tall += 23 * math.ceil(len(n.lines[0]) / 42) + 10
    for line in said:
        lead, _, rest = line.partition(": ")
        if rest and lead == n.label:  # 'S3: GetObject (s3:GetObject), PutObject (s3:PutObject)': a list
            items = rest.split(", ")
            body.append(f'<ul class="ctl">{"".join(_g_tip_item(item) for item in items)}</ul>')
            tall += 30 * len(items) + 8
        else:
            body.append(f'<p class="ctp">{_g_tip_text(line)}</p>')
            tall += 23 * math.ceil(len(line) / 42) + 10
    changed = history_html(n.history, short=True)
    if changed:
        body.append(changed)
        tall += 23 * math.ceil(len(re.sub(r"<[^>]*>", "", changed)) / 42) + 14
    if warnings:
        body.append(
            '<div class="ctw"><b>Warning</b><ul>'
            + "".join(f"<li>{_g_tip_text(w)}</li>" for w in warnings)
            + "</ul></div>"
        )
        tall += 50 + sum(23 * math.ceil(len(w) / 36) + 4 for w in warnings)
    kind = _G_PANEL_KINDS.get(n.kind, n.kind)
    name = _python_html(n.label) if mono else _esc(n.label)
    card = (
        f'<div class="ctt k-{_esc(n.kind)}{" warn" if warnings else ""}"><div class="cth">'
        f'<span class="ctkd">{_esc(kind)}</span><b class="ctn{" mono" if mono else ""}">{name}</b>'
        + (f'<span class="cts{" mono" if mono else ""}">{_esc(sub)}</span>' if sub else "")
        + f"</div>{''.join(body)}"
        + ('<div class="cto">Click it to read its code</div>' if opens else "")
        + "</div>"
    )
    return card, tall + (40 if opens else 0)


def _g_tip_svg(
    n: GraphNode,
    box: tuple[float, float, float, float],
    width: float,
    tall: float,
    lines_of: Callable[[str], list[str]],
    opens: bool,
) -> str:
    """
    A box's hover card, in the graph so it zooms with it: under the box when it fits there, else over it, else beside
    it, and inside the graph from left to right. Hidden until the box is pointed at.
    """
    card, high = _g_tip(n, lines_of, opens)
    x, y, w, h = box
    card_w = min(_G_TIP_W, max(width - 16, 220))
    left = max(8.0, min(x, width - card_w - 8))
    below, above = tall - (y + h + 10) - 8, y - 10 - 8
    if high <= below:
        top, room, side = y + h + 10, below, "dn"
    elif high <= above:
        top, room, side = 8.0, above, "up"
    else:  # beside the box, as high up as keeps all of it in the graph; over the box only when there's no room beside
        if width - (x + w + 12) - 8 >= card_w:
            left = x + w + 12
        elif x - 12 - 8 >= card_w:
            left = x - 12 - card_w
        top, room, side = max(8.0, min(y, tall - high - 8)), high, "dn"
    return (
        f'<foreignObject class="ctip tp-{_esc(n.id)} {side}" x="{left:.0f}" y="{top:.0f}" width="{card_w:.0f}" '
        f'height="{room:.0f}" aria-hidden="true"><div class="ctx">{card}</div></foreignObject>'
    )


def _g_captions(graph: CodeGraph, xs: dict[int, float], widths: dict[int, float], column_of: dict[str, int]) -> str:
    """
    The words over the columns: COMES IN, HANDLER, CALLS, REACHES, each over the columns it covers.
    """
    kinds: dict[int, set[str]] = defaultdict(set)
    for n in graph.nodes:
        kinds[column_of[n.id]].add(n.kind)

    def word(found: set[str]) -> str:
        return (
            "Reaches"
            if found & {"aws", "service", "http"}
            else "Entry"
            if "handler" in found
            else "Comes in"
            if found & {"event", "env"}
            else "Calls"
            if "function" in found
            else "Start-up"
        )

    groups: list[list[Any]] = []
    for k in sorted(kinds):
        said = word(kinds[k])
        if groups and groups[-1][0] == said:
            groups[-1][2] = k
        else:
            groups.append([said, k, k])
    out = []
    for said, first, last in groups:
        x, right = xs[first], xs[last] + widths[last]
        text = said.upper()
        end = x + _g_sans(text, 12, bold=True) + len(text) * 1.2 + 10
        out.append(f'<text class="cap" x="{x + 2:.0f}" y="25">{_esc(text)}</text>')
        if right - end > 12:
            out.append(f'<path class="capl" d="M{end:.0f},21H{right:.0f}"/>')
    return "".join(out)


def _g_swatch(kind: str) -> str:
    return (
        f'<svg class="sw ek-{kind}" width="26" height="10" viewBox="0 0 26 10" aria-hidden="true">'
        f'<path class="ln" d="M1.5,5H17"/><path class="ah" d="{_g_head(24.5, 5, 1)}"/></svg>'
    )


_G_SCRIPT = """<script>
(() => {
  // A graph's views: a box's line of calls not drawn, the path over a view and the bar's All button link to
  // #<group>-v<k> (or -all, or -main), and each is a <template> the graph's box, path and key are swapped from.
  // Any other address (a box's code open, or closed) leaves the view as it is.
  const parts = ["cgc", "cg", "cgk"];
  const show = (wrap) => {
    const group = wrap.dataset.group, id = decodeURIComponent(location.hash.slice(1));
    const named = id === group + "-main" || id === group + "-all" || id.startsWith(group + "-v");
    if (id && !named) return;
    const view = named && id !== group + "-main" ? id : "";
    if ((wrap.dataset.view || "") === view) return;
    const from = view ? document.getElementById(view)?.content : wrap.main;
    if (!from) return;
    for (const part of parts) {
      wrap.querySelector(".cgb ." + part).innerHTML = from.querySelector(".x-" + part).innerHTML;
    }
    wrap.dataset.view = view;
    wrap.querySelector(".cgb").scrollIntoView({block: "nearest"});
  };
  for (const wrap of document.querySelectorAll(".cgw[data-group]")) {
    const main = document.createElement("template");
    for (const part of parts) {
      const kept = document.createElement("div");
      kept.className = "x-" + part;
      kept.innerHTML = wrap.querySelector(".cgb ." + part).innerHTML;
      main.content.append(kept);
    }
    wrap.main = main.content;
    wrap.classList.add("js");
    show(wrap);
  }
  addEventListener("hashchange", () => document.querySelectorAll(".cgw.js").forEach(show));
  // A box's code: a click anywhere outside its panel closes it, as its × does, and so does Escape. A link (another
  // box, a view) and the graph's bar do what they do with the panel left to them.
  const close = () => { if (document.querySelector(".cside:target")) location.hash = "cn-closed"; };
  document.addEventListener("click", (e) => {
    const open = document.querySelector(".cside:target");
    if (open && !open.contains(e.target) && !e.target.closest("a[href], label, input, .cgt")) close();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  // A function's code: pointing at a line puts the commit it comes from in its panel's last row, in place of what git
  // says about all of it.
  // Its settings, one for every panel: turning git off in one turns it off in all, and the page remembers it.
  const blame = (on) => document.querySelectorAll(".csg").forEach((box) => { box.checked = on; });
  try { if (localStorage.getItem("code-node.blame") === "off") blame(false); } catch (e) {}
  document.addEventListener("change", (e) => {
    if (!e.target.matches(".csg")) return;
    blame(e.target.checked);
    try { localStorage.setItem("code-node.blame", e.target.checked ? "on" : "off"); } catch (e) {}
  });
  let blamed = "";
  document.addEventListener("mouseover", (e) => {
    const mark = e.target.closest(".cside .sl")?.querySelector(".sb[data-k]");
    const panel = mark && mark.closest(".cside"), key = mark ? mark.dataset.k : "";
    const row = (panel || document).querySelector(".csf");
    if (key + (panel && panel.id) === blamed) return;
    document.querySelectorAll(".csf p").forEach((p) => {
      p.hidden = p.closest(".csf") === row && key ? p.dataset.k !== key : p.hasAttribute("data-k");
    });
    blamed = key + (panel && panel.id);
  });
  // Moving about a graph as on a canvas: drag it to pan, Ctrl or ⌘ with the wheel (or a trackpad's pinch) to zoom
  // around the pointer, and + - 0 when it has focus. A zoom of its own unchecks the bar's buttons, so the plain rule
  // (the SVG's width times --z) draws it; picking a button again takes it back. Its box keeps one size, and Fit
  // (--fit) puts all of it in that box, both ways.
  for (const wrap of document.querySelectorAll(".cgw")) {
    const box = wrap.querySelector(".cgb .cg"), radios = wrap.querySelectorAll(":scope > .cgs[type=radio]");
    const said = wrap.querySelector(".cgtp"), svg = () => box.querySelector("svg");
    const scale = () => {
      const s = svg();
      return s && s.viewBox.baseVal.width ? s.getBoundingClientRect().width / s.viewBox.baseVal.width : 1;
    };
    const fit = () => {
      const s = svg(), w = s && s.viewBox.baseVal.width, h = s && s.viewBox.baseVal.height;
      if (w && h && box.clientWidth) {
        box.style.setProperty("--fit", Math.min((box.clientWidth - 24) / w, (box.clientHeight - 24) / h, 1.5));
      }
    };
    const tell = () => { fit(); if (said) said.textContent = Math.round(scale() * 100) + "%"; };
    const pan = (dx, dy) => {  // the graph's box first, then the page for what it can't scroll
      const top = box.scrollTop;
      box.scrollLeft += dx;
      box.scrollTop += dy;
      const left = dy - (box.scrollTop - top);
      if (Math.abs(left) > 0.5) scrollBy(0, left);
    };
    const zoom = (by, x, y) => {  // keeps the point at (x, y) where it is
      const s = svg();
      if (!s) return;
      const from = scale(), to = Math.min(4, Math.max(0.1, from * by)), was = s.getBoundingClientRect();
      const px = (x - was.left) / from, py = (y - was.top) / from;
      radios.forEach((r) => { r.checked = false; });
      box.style.setProperty("--z", to);
      const now = s.getBoundingClientRect();
      pan(now.left + px * to - x, now.top + py * to - y);
      tell();
    };
    const auto = () => {  // back to the Auto button
      const radio = wrap.querySelector(":scope > .cgz-auto");
      radio.checked = true;
      radio.dispatchEvent(new Event("change", {bubbles: true}));
    };
    const step = (by) => {  // around the middle of what's in sight
      const r = box.getBoundingClientRect();
      zoom(by, r.left + r.width / 2, (Math.max(r.top, 0) + Math.min(r.bottom, innerHeight)) / 2);
    };
    wrap.querySelector(".cgb .zi")?.addEventListener("click", () => step(1.25));
    wrap.querySelector(".cgb .zo")?.addEventListener("click", () => step(0.8));
    let drag = null, moved = false;
    box.addEventListener("pointerdown", (e) => {
      moved = false;
      if (e.button === 0 && e.pointerType !== "touch") drag = {x: e.clientX, y: e.clientY, id: e.pointerId};
    });
    box.addEventListener("pointermove", (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!moved && Math.hypot(dx, dy) < 4) return;  // a click on a box stays a click
      if (!moved) { moved = true; box.setPointerCapture(e.pointerId); box.classList.add("pan"); }
      pan(-dx, -dy);
      drag.x = e.clientX;
      drag.y = e.clientY;
    });
    const end = () => { drag = null; box.classList.remove("pan"); };
    box.addEventListener("pointerup", end);
    box.addEventListener("pointercancel", end);
    box.addEventListener("click", (e) => { if (moved) { e.preventDefault(); e.stopPropagation(); } }, true);
    box.addEventListener("dragstart", (e) => e.preventDefault());
    box.addEventListener("wheel", (e) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const d = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1);
      zoom(Math.exp(-Math.max(-100, Math.min(100, d)) * 0.0015), e.clientX, e.clientY);
    }, {passive: false});
    box.tabIndex = 0;
    box.addEventListener("keydown", (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "+" || e.key === "=") step(1.25);
      else if (e.key === "-" || e.key === "_") step(0.8);
      else if (e.key === "0") auto();
      else return;
      e.preventDefault();
    });
    wrap.addEventListener("change", (e) => {
      if (!e.target.matches(".cgs")) return;  // a zoom button, or full screen: its box's size changes
      if (e.target.type === "radio") box.style.removeProperty("--z");
      requestAnimationFrame(tell);
    });
    addEventListener("hashchange", () => requestAnimationFrame(tell));
    addEventListener("resize", tell);
    wrap.classList.add("pz");
    tell();
  }
})();
</script>"""


def _g_hidden(graph: CodeGraph, opens: bool) -> str:
    """
    The legend's pill for the functions a graph leaves out, and why: without JavaScript where to find them, with it
    (when opens) that a box's line of them opens them.
    """
    if not graph.hidden:
        return ""
    why = (
        "too deep"
        if graph.too_deep == graph.hidden
        else "too many to draw at once"
        if not graph.too_deep
        else "too deep or too many"
    )
    head = f"<b>+{graph.hidden}</b>{'more function' if graph.hidden == 1 else 'more functions'} not drawn ({why})"
    pill = f'<span class="kp kh{" nj" if opens else ""}">{head}: the Step by step tab has them all</span>'
    if opens:
        pill += f'<span class="kp kh oj">{head}: click a dimmed call in a box, or Open its calls, to draw them</span>'
    return pill


def _g_lineage(graph: CodeGraph) -> tuple[dict[str, set[str]], list[set[str]]]:
    """
    What stays in sight when a box is pointed at: the boxes joined to it, and every box on a path through it, from
    the entry point down to what it reaches; and for each arrow, the boxes it's on such a path of. Paths follow calls
    and what the code reaches, never the input or the environment: those light only the boxes they go into.
    """
    into: dict[str, set[str]] = defaultdict(set)
    out: dict[str, set[str]] = defaultdict(set)
    for e in graph.edges:
        if e.kind not in ("event", "env"):
            into[e.target].add(e.source)
            out[e.source].add(e.target)

    def closure(start: str, step: dict[str, set[str]]) -> set[str]:
        seen, todo = set(), [start]
        while todo:
            for other in step.get(todo.pop(), ()):
                if other not in seen:
                    seen.add(other)
                    todo.append(other)
        seen.discard(start)
        return seen

    up = {n.id: closure(n.id, into) for n in graph.nodes}
    down = {n.id: closure(n.id, out) for n in graph.nodes}
    boxes = {n.id: up[n.id] | down[n.id] for n in graph.nodes}
    for e in graph.edges:
        boxes[e.source].add(e.target)
        boxes[e.target].add(e.source)
    arrows = []
    for e in graph.edges:
        lit = {e.source, e.target}
        if e.kind not in ("event", "env"):
            for n in graph.nodes:
                below, above = up[n.id] | {n.id}, down[n.id] | {n.id}
                if (e.target in below and e.source in up[n.id]) or (e.source in above and e.target in down[n.id]):
                    lit.add(n.id)
        arrows.append(lit)
    return boxes, arrows


def _g_canvas(
    graph: CodeGraph,
    block: _Graph,
    report: _Report,
    lines_of: Callable[[str], list[str]],
    panels: dict[str, tuple[str, str]],
    opens: dict[str, str],
    prefix: str,
) -> tuple[str, str]:
    """
    One graph drawn: its SVG and its legend. Its boxes' panels go into panels ({a function, or a panel without its
    id: (its id, the panel)}, one for a function or the same code wherever it's drawn, the first graph's; a new one's
    id starts with prefix), and a box whose function is in opens ({module.name: a
    link}) has its line of calls not drawn made that link.
    """
    cards = _g_cards(graph)
    for n in graph.nodes:
        cards[n.id].opens = bool(n.more and n.name in opens)
    boxes, routes, width, tall, xs, widths, column_of = _graph_layout(graph, cards)
    ends = _g_anchors(graph, cards, boxes)
    near, lit = _g_lineage(graph)
    access: dict[str, dict[str, str]] = defaultdict(dict)  # an AWS box's operation -> what it does
    for e in graph.edges:
        if e.kind in _G_ACCESS:
            for name in _g_names(e):
                access[e.target].setdefault(name, e.kind)
    root = report.root or _ROOT
    panel_of: dict[str, str] = {}  # a box -> its panel's id
    if block.sources:
        for n in graph.nodes:
            same = "\0" + n.name if n.name else ""
            if same not in panels:
                html = _g_panel(n, lines_of, block.editor, "\0")
                if not html:
                    continue
                same = same or html
                if same not in panels:
                    key = prefix + _g_panel_id(n)
                    panels[same] = (key, html.replace('id="\0"', f'id="{key}"', 1))
            panel_of[n.id] = panels[same][0]
    for key in set(panel_of.values()):  # the box whose code is open, outlined
        report.rules.add(
            f".{root} .cgw:has(#{key}:target) .cg .p-{key} .fg"
            "{stroke:light-dark(#2563eb,#60a5fa);stroke-opacity:1;stroke-width:2}"
        )
    for n in graph.nodes:  # pointing at a box leaves only it and the paths through it in sight, its own arrows bold
        report.rules.add(f".{root} .cg:has(.n-{n.id}:hover) .ce:not(.l-{n.id}){{opacity:.06}}")
        report.rules.add(f".{root} .cg:has(.n-{n.id}:hover) .cn:not(.n-{n.id}):not(.a-{n.id}){{opacity:.28}}")
        if n.id in panel_of:  # ...and while its code is open, until another box is pointed at
            open_box = (
                f".{root} .cgw:has(#{panel_of[n.id]}:target) .cg:not(:has(.cn:hover)):has(.n-{n.id}.p-{panel_of[n.id]})"
            )
            report.rules.add(f"{open_box} .ce:not(.l-{n.id}){{opacity:.06}}")
            report.rules.add(f"{open_box} .cn:not(.n-{n.id}):not(.a-{n.id}){{opacity:.28}}")
        report.rules.add(f".{root} .cg:has(.n-{n.id}:hover) .tp-{n.id}{{display:inline}}")
        report.rules.add(
            f".{root} .cg:has(.n-{n.id}:hover) :is(.s-{n.id},.t-{n.id}) .ln{{stroke-width:2.4;stroke-opacity:1}}"
        )
    marked: set[tuple[str, str]] = set()  # one loop mark between two boxes, even for two arrows
    taken: list[tuple[float, float]] = []  # where marks are, so the next one goes clear of them
    lanes: dict[frozenset[str], int] = defaultdict(int)  # calls within a column between the same two boxes
    drawn = []
    for i, e in enumerate(graph.edges):
        hot = None
        if e.tone == "warn":  # the lines from or to the row the warning is about (TEAM_TOPIC, not set), else all
            out, into = _g_rows(cards[e.source], e), _g_rows(cards[e.target], e)
            hot = {
                (a, b)
                for a in range(len(ends[i][0]))
                for b in range(len(ends[i][1]))
                if (a < len(out) and out[a] in cards[e.source].node.flags)
                or (b < len(into) and into[b] in cards[e.target].node.flags)
            } or None
        lane = 0
        if column_of[e.source] == column_of[e.target]:
            lane = lanes[frozenset((e.source, e.target))]
            lanes[frozenset((e.source, e.target))] += 1
        drawn.append(
            _edge_svg(
                e,
                graph,
                boxes,
                xs,
                widths,
                column_of,
                *ends[i],
                routes.get(i),
                (e.source, e.target) not in marked,
                hot,
                taken,
                lane,
                sorted(lit[i]),
            )
        )
        if e.loop:
            marked.add((e.source, e.target))
    edges = "".join(body for body, _ in drawn)
    ports = "".join(dots for _, dots in drawn)
    opened = {n.id: opens[n.name] for n in graph.nodes if n.more and n.name in opens}
    nodes = "".join(
        (
            f'<a class="cl" href="#{_esc(panel_of[n.id])}" aria-label="{_esc("Show the code of " + n.label)}">{box}</a>'
            if n.id in panel_of
            else box
        )
        for n in graph.nodes
        for box in [
            _node_svg(
                cards[n.id],
                boxes[n.id],
                sorted(near[n.id]),
                access[n.id],
                panel_of.get(n.id, ""),
                n.id in opened,
            )
        ]
    )
    links = "".join(  # over each line of calls not drawn that opens a graph of its own, and over each row of a call
        # not drawn: drawn with JavaScript only
        f'<a class="dr" href="#{_esc(link)}" aria-label="{_esc(f"Open the calls {n.label} makes")}">'
        f'<rect x="{boxes[n.id][0] + 8:.1f}" y="{boxes[n.id][1] + y - 14:.1f}" '
        f'width="{boxes[n.id][2] - 16:.0f}" height="19" rx="5"/></a>'
        for n in graph.nodes
        if (link := opened.get(n.id))
        for y in [_g_more_y(cards[n.id]), *_g_off_rows(cards[n.id])]
    )
    tips = "".join(_g_tip_svg(n, boxes[n.id], width, tall, lines_of, n.id in panel_of) for n in graph.nodes)
    kinds = {e.kind for e in graph.edges}
    pills = [f'<span class="kp">{_g_swatch(k)}{_esc(word)}</span>' for k, word in _G_LEGEND if k in kinds]
    if any(e.guessed for e in graph.edges):
        pills.append(f'<span class="kp">{_g_swatch("guess")}guessed from a method\'s name</span>')
    if any(e.indirect for e in graph.edges):
        pills.append(f'<span class="kp">{_g_swatch("via")}through functions not drawn</span>')
    if any(e.tone == "warn" for e in graph.edges) or any(n.tone == "warn" for n in graph.nodes):
        pills.append(
            '<span class="kp"><svg class="sw kw" width="16" height="16" viewBox="-8 -8 16 16" '
            'aria-hidden="true"><circle r="7"/><path d="M0,-3.6V.5M0,3.4V3.5"/></svg>'
            "a warning is about it</span>"
        )
    if any(e.loop for e in graph.edges):
        pills.append(
            '<span class="kp"><svg class="sw kl" width="16" height="16" viewBox="-8 -8 16 16" '
            f'aria-hidden="true"><circle r="7"/><path transform="scale(.6) translate(-8,-8)" d="{_G_LOOP}"/>'
            "</svg>in a loop: once per item</span>"
        )
    hint = (
        '<span class="kt">Point at a box to see only the paths through it'
        + ("; click it to read its code" if panel_of else "")
        + '</span><span class="kt pzo">Drag to move about; Ctrl or ⌘ and scroll, or pinch, to zoom</span>'
    )
    svg = (
        f'<svg viewBox="0 0 {width:.0f} {tall:.0f}" width="{width:.0f}" height="{tall:.0f}" '
        f'style="--w:{width:.0f}px" role="img" aria-label="{_esc(block.title or "How the code fits together")}">'
        f"{_g_captions(graph, xs, widths, column_of)}{edges}{nodes}{links}{ports}{tips}</svg>"
    )
    return svg, "".join(pills) + _g_hidden(graph, bool(opened)) + hint


def _g_path(path: list[str], links: dict[str, str], main: str, last: str = "") -> str:
    """
    The calls from the entry point down to a view's function, over its graph: each one that has a view of its own a
    link to it, and a link back to the whole graph first. last, when given, is said after them in place of the last.
    """
    names = [_esc(_short_name(name)) + "()" for name in path]
    steps = [
        f'<a href="#{_esc(links[name])}"><code>{said}</code></a>' if name in links else f"<code>{said}</code>"
        for name, said in zip(path[:-1], names[:-1])
    ]
    steps.append(_esc(last) if last else f"<b><code>{names[-1]}</code></b>" if names else "")
    return f'<a class="cgcb" href="#{_esc(main)}">← The whole graph</a>' + "".join(
        f'<span class="cgcs">›</span>{step}' for step in steps
    )


@_draws(_Graph, "html")
def _graph_html(block: _Graph, report: _Report) -> str:
    title = f"<h4>{_prose(block.title)}</h4>" if block.title else ""
    graph = block.graph
    if not graph.nodes:
        return title + f'<div class="more">{_esc(block.empty)}</div>'
    highlighted: dict[str, list[str]] = {}

    def lines_of(file: str) -> list[str]:  # a file's lines in colour, each file coloured once
        if file not in highlighted:
            highlighted[file] = _python_lines(block.sources[file]) if file in block.sources else []
        return highlighted[file]

    made = report.shared("graphs", lambda: [0])  # graphs drawn so far, so each one's buttons have ids of their own
    group = f"cn-graph{made[0]}"
    made[0] += 1
    links = {view.name: f"{group}-v{k}" for k, view in enumerate(block.views, 1)}
    panels: dict[str, tuple[str, str]] = {}
    svg, legend = _g_canvas(graph, block, report, lines_of, panels, links, "")
    views = []
    for k, view in enumerate(block.views, 1):
        drawn, key = _g_canvas(view.graph, block, report, lines_of, panels, links, f"v{k}-")
        views.append(
            f'<template id="{group}-v{k}"><div class="x-cgc">{_g_path(view.path, links, group + "-main")}</div>'
            f'<div class="x-cg">{drawn}</div><div class="x-cgk">{key}</div></template>'
        )
    everything = ""
    if block.everything is not None and block.everything.nodes:
        count = sum(1 for n in block.everything.nodes if n.kind in ("handler", "function"))
        drawn, key = _g_canvas(block.everything, block, report, lines_of, panels, {}, "all-")
        views.append(
            f'<template id="{group}-all"><div class="x-cgc">'
            f"{_g_path([], links, group + '-main', f'Every function, all {count} of them')}</div>"
            f'<div class="x-cg">{drawn}</div><div class="x-cgk">{key}</div></template>'
        )
        everything = f'<a class="cgta oj" href="#{group}-all" title="Every function in one graph">All {count}</a>'
    # its zoom and full screen: inputs before the box they change, so CSS reaches it with ~ (no :has(), no script)
    switches = f'<input type="checkbox" class="cgs cgfs" id="{group}-full">' + "".join(
        f'<input type="radio" class="cgs cgz-{key}" name="{group}-zoom" id="{group}-{key}"'
        f"{' checked' if key == 'auto' else ''}>"
        for key, _, _ in _GRAPH_ZOOMS
    )
    bar = (
        f'<div class="cgt">{everything}<span class="cgtz" role="group" aria-label="Zoom">'
        + "".join(
            f'<label class="zl-{key}" for="{group}-{key}" title="{_esc(tip)}">{_esc(word)}</label>'
            for key, word, tip in _GRAPH_ZOOMS
        )
        + f'</span><label class="cgtf" for="{group}-full"><span class="on">Full screen</span>'
        '<span class="off">Close full screen</span></label></div>'
    )
    zoom = (  # over the graph's corner, as a canvas has it: with JavaScript only
        '<span class="cgtm pzo" role="group" aria-label="Zoom out or in">'
        '<button type="button" class="zo" title="Zoom out (-, or Ctrl and scroll)">−</button>'
        '<span class="cgtp" title="How big the graph is drawn"></span>'
        '<button type="button" class="zi" title="Zoom in (+, or Ctrl and scroll)">+</button></span>'
    )
    script = ""
    if not report.shared("graph-script", lambda: [False])[0]:  # once, for every graph: moving about and zooming
        report.shared("graph-script", lambda: [False])[0] = True
        script = _G_SCRIPT
    # in a box of its own with its panels: the :has() rules that outline a box whose code is open look only in here,
    # so a radio button elsewhere (the walk's steps) doesn't make the browser restyle the whole page
    data = f' data-group="{group}"' if views else ""
    return (
        f'{title}<div class="cgw"{data}>{switches}<div class="cgb">{bar}'
        f'<nav class="cgc" aria-label="Where this graph starts"></nav><div class="cgv"><div class="cg">{svg}</div>{zoom}</div>'
        f'<div class="cgk">{legend}</div></div>{"".join(html for _, html in panels.values())}{"".join(views)}</div>'
        f"{script}"
    )


@_draws(_Graph, "text")
def _graph_lines(block: _Graph, report: _Report) -> list[str]:
    out = ["", f"-- {block.title} --"] if block.title else [""]
    graph = block.graph
    if not graph.nodes:
        return out + [block.empty]
    leaving: dict[str, list[GraphEdge]] = defaultdict(list)
    for e in graph.edges:
        leaving[e.source].append(e)
    for n in sorted(graph.nodes, key=lambda n: n.column):
        if n.kind in ("aws", "service", "http"):
            continue
        lines = [f"{line} ({n.flags[line]})" if line in n.flags else line for line in n.lines]
        head = n.label + (
            f": {', '.join(lines)}" if n.kind in ("event", "env") and n.lines else f"  {n.sub}" if n.sub else ""
        )
        out.append(f"  {head}" + (" (!)" if n.tone == "warn" else ""))
        for e in leaving.get(n.id, []):
            target = graph.node(e.target)
            name = target.label if target else e.target
            said = {
                "call": f"calls {name}" + (f" ({e.label})" if e.label else "") + (f" when {e.when}" if e.when else ""),
                "event": f"→ {name}",
                "env": f"→ {name} reads {e.label}",
                "client": f"makes the {name} client",
                "http": f"sends {e.label}",
            }.get(e.kind) or f"{_EDGE_WORDS.get(e.kind, e.kind)} {name}: {e.label}"
            said += "".join(
                [
                    ", in a loop" if e.loop else "",
                    ", guessed from a method's name" if e.guessed else "",
                    ", through functions not drawn" if e.indirect and e.kind != "call" else "",
                ]
            )
            out.append(f"      {said}" + (" (!)" if e.tone == "warn" else ""))
        if n.more:
            out.append(f"      +{_g_calls(len(n.more))} not drawn: {', '.join(n.more)}")
        elif n.kind in ("handler", "function", "start") and not leaving.get(n.id):
            out.append("      (does nothing this follows: no AWS calls, own functions or HTTP)")
    if graph.hidden:
        out.append(f"  ({_plural(graph.hidden, 'more function')} not drawn: the steps below have them all)")
    return out
