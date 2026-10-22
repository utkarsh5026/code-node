"""
_Flow: the decisions each call makes, as a flowchart drawn top to bottom. What comes in, then each line that does
something worth knowing, each `if` as a question with an arrow for each answer, each loop as a box with an arrow back
to its top, each `try` with the way taken when a line in it raises, and where the function ends.

No JavaScript: one SVG for each flow. The path that goes on runs down the middle; an answer whose lines end early
(return, raise, skip to the next item, leave the loop) sits beside it, so the usual path reads as one line. A call to
one of the code's own functions is a box with what it reaches; one that makes decisions of its own is opened in place,
up to _OPEN_DEPTH calls deep and _OPEN_TALL high. One opened nowhere gets a flow of its own under the first, and its
box links to it.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Callable

from ..kit.blocks import _Report, _draws
from ..kit.fmt import _plural
from ..kit.text import _esc

from ..analysis.findings import _short_name
from ..analysis.model import CodeStep
from .brands import AWS_LOGOS, SERVICE_LOGOS, fills, logo_for
from .graph import _g_mono, _g_sans
from .walk import _SAID_FIRST, _note_said

_GAP = 30  # between boxes on a path
_SIDE = 56  # between the path down the middle and an answer beside it
_PAD = 28  # around the drawing
_BOX_LEAST, _BOX_MOST = 230, 340  # a box's width
_ROW = 21  # a line a box lists: what a call reaches
_ROWS_MOST = 4  # lines a call's box lists, at most
_END_MOST = 300  # an end's words, at most this wide
_QUESTION_MOST = 320  # a question's code, at most this wide

_OPEN_DEPTH = 2  # calls opened in place, at most this many deep
_OPEN_TALL = 1400  # ...and at most this tall; a call opened nowhere gets a flow of its own
_FLOWS_MOST = 24  # flows drawn, at most: a web app's routes, then the calls opened nowhere

_REACHES = ("aws-", "lib-", "http")  # the tags of what a line reaches outside the code

_KIND_OF = {  # a tag -> the colour its box takes, as the graph's arrows do
    "aws-reads": "reads",
    "lib-reads": "reads",
    "aws-writes": "writes",
    "lib-writes": "writes",
    "aws-sends": "sends",
    "lib-sends": "sends",
    "http": "sends",
    "aws-runs": "runs",
    "lib-runs": "runs",
    "event": "event",
    "env": "env",
    "warn": "warn",
}


@dataclass
class _Flow:
    """
    How each call decides what to do: steps are the map's (CodeMap.steps), one 'def' step for the entry point, or for
    a web app the app with a 'def' step for each route. comes_in is what the entry point is called with, as the graph
    says it: ('An S3 event', "what it's called with").
    """

    steps: list[CodeStep]
    title: str = ""
    comes_in: tuple[str, str] = ("", "")
    empty: str = "(no calls to draw)"


# ---------------------------------------------------------------- what's drawn


@dataclass
class _Box:
    """
    A piece of a flow, drawn at any place: its size, where the path runs through it (middle, from its left), and
    whether the code goes on past its bottom.
    """

    width: float
    height: float
    middle: float
    parts: list[Callable[[float, float], str]] = field(default_factory=list)
    goes_on: bool = True
    leaving: str = ""  # said on the arrow that leaves it: 'when every one is done'

    def draw(self, x: float, y: float) -> str:
        return "".join(part(x, y) for part in self.parts)


_NOTHING = _Box(0, 0, 0)


def _clip(text: str, room: float, measure: Callable[[str], float]) -> str:
    if measure(text) <= room:
        return text
    while text and measure(text + "…") > room:
        text = text[:-1]
    return text + "…"


def _mono(size: float) -> Callable[[str], float]:
    return lambda text: _g_mono(text, size)


def _sans(size: float, bold: bool = False) -> Callable[[str], float]:
    return lambda text: _g_sans(text, size, bold)


def _arrow(points: list[tuple[float, float]], css: str = "", head: bool = True) -> str:
    """
    A line through the points, with an arrowhead at the last one.
    """
    path = "M" + " L".join(f"{x:g} {y:g}" for x, y in points)
    out = f'<path class="fe{" " + css if css else ""}" d="{path}"/>'
    if not head:
        return out
    (x0, y0), (x1, y1) = points[-2], points[-1]
    if abs(y1 - y0) >= abs(x1 - x0):
        s = 1 if y1 > y0 else -1
        tip = f"M{x1 - 5:g} {y1 - 8 * s:g} L{x1:g} {y1:g} L{x1 + 5:g} {y1 - 8 * s:g}Z"
    else:
        s = 1 if x1 > x0 else -1
        tip = f"M{x1 - 8 * s:g} {y1 - 5:g} L{x1:g} {y1:g} L{x1 - 8 * s:g} {y1 + 5:g}Z"
    return out + f'<path class="fh{" " + css if css else ""}" d="{tip}"/>'


def _word(x: float, y: float, text: str, css: str) -> str:
    """
    A few words on an arrow, on a pill of their own: 'yes', 'no', 'next order'.
    """
    width = _g_sans(text, 11.5, True) + 10
    return (
        f'<g class="fw {css}"><rect x="{x:g}" y="{y - 9:g}" width="{width:g}" height="18" rx="9"/>'
        f'<text x="{x + width / 2:g}" y="{y + 4:g}" text-anchor="middle">{_esc(text)}</text></g>'
    )


def _join(x: float, y: float) -> str:
    return f'<circle class="fj" cx="{x:g}" cy="{y:g}" r="3.5"/>'


def _stack(boxes: list[_Box]) -> _Box:
    """
    Boxes one under the other, joined by arrows, as far as the first one the code doesn't go on past.
    """
    boxes = [b for b in boxes if b.height]
    for i, b in enumerate(boxes):
        if not b.goes_on:
            boxes = boxes[: i + 1]
            break
    if not boxes:
        return _NOTHING
    left = max(b.middle for b in boxes)
    right = max(b.width - b.middle for b in boxes)
    parts: list[Callable[[float, float], str]] = []
    y = 0.0
    for i, b in enumerate(boxes):
        parts.append(lambda x, top, b=b, at=y: b.draw(x + left - b.middle, top + at))
        y += b.height
        if i < len(boxes) - 1:
            gap = _GAP + (8 if b.leaving else 0)
            parts.append(
                lambda x, top, at=y, gap=gap, said=b.leaving: (
                    _arrow([(x + left, top + at), (x + left, top + at + gap)])
                    + (_word(x + left + 8, top + at + gap / 2, said, "fwq") if said else "")
                )
            )
            y += gap
    return _Box(left + right, y, left, parts, boxes[-1].goes_on, boxes[-1].leaving)


def _tip(step: CodeStep | None) -> str:
    return f"<title>{_esc(f'{step.file} line {step.line}: {step.code}')}</title>" if step is not None else ""


def _logo(name: str | None, x: float, y: float, size: float) -> str:
    found = logo_for(name, size) if name else None
    if not found:
        return ""
    width, height, body = found
    body = body.replace('id="cnl-', 'id="cnf-').replace("url(#cnl-", "url(#cnf-")  # the graph's, in a hidden tab
    return (
        f'<svg class="logo flg" x="{x:g}" y="{y:g}" width="{size:g}" height="{size:g}" viewBox="0 0 {width} {height}" '
        f'fill="currentColor" aria-hidden="true">{body}</svg>'
    )


def _logo_name(kind: str, text: str) -> str | None:
    """
    The logo of what a tag reaches: 'aws-s3' for ('aws-reads', 'S3 GetObject'), 'redis' for ('lib-reads', 'Redis: GET').
    """
    if kind.startswith("aws-"):
        service = text.rpartition(" ")[0] or text
        return AWS_LOGOS.get(service.lower().replace(" ", ""))
    if kind.startswith("lib-"):
        return SERVICE_LOGOS.get(text.partition(":")[0].lower())
    return None


_BADGES = {  # 26 x 26 line drawings, stroked in the box's colour
    "event": "M14.5 5.5 L8.5 14 H13 L11.5 20.5 L17.5 12 H13Z",
    "env": "M7 9h12M7 13h12M7 17h8",
    "log": "M8 8h10v10H8zM10.5 11.5h5M10.5 14.5h3",
    "code": "M10 9 L6.5 13 L10 17M16 9 L19.5 13 L16 17",
}


def _badge(badge: str, x: float, y: float) -> str:
    """
    A box's badge at x, y: 'entry' (the entry point), 'call' (one of its own functions), 'logo:aws-s3', a line drawing
    from _BADGES, or 'dot'.
    """
    tile = f'<rect class="fbd" x="{x:g}" y="{y:g}" width="26" height="26" rx="7"/>'
    if badge == "entry":
        return (
            tile + f'<path class="fbi fill" d="M{x + 10:g} {y + 8:g} L{x + 19:g} {y + 13:g} L{x + 10:g} {y + 18:g}Z"/>'
        )
    if badge == "call":
        return tile + f'<text class="fbl" x="{x + 13:g}" y="{y + 18:g}" text-anchor="middle">λ</text>'
    if badge.startswith("logo:"):
        found = logo_for(badge[5:], 26)
        if found and fills(found):
            return _logo(badge[5:], x, y, 26)
        return tile + _logo(badge[5:], x + 4, y + 4, 18)
    if badge in _BADGES:
        return tile + f'<path class="fbi" transform="translate({x:g} {y:g})" d="{_BADGES[badge]}"/>'
    return tile + f'<circle class="fbi fill" cx="{x + 13:g}" cy="{y + 13:g}" r="3.2"/>'


def _card(
    title: str,
    *,
    sub: str = "",
    rows: list[tuple[str, str]] | None = None,
    badge: str = "dot",
    css: str = "",
    mono: bool = False,
    foot: str = "",
    link: str = "",
    step: CodeStep | None = None,
) -> _Box:
    """
    A box on the path: a badge, a title with a quiet line under it, and the lines it lists, (tag, what) each: what a
    call reaches, or a warning. foot is a line at its bottom, a link to link's flow when given.
    """
    rows = rows or []
    measure = _mono(13) if mono else _sans(13.5, True)
    width = max(
        _BOX_LEAST,
        min(
            _BOX_MOST,
            max(
                measure(title) + 60,
                _g_sans(sub, 12) + 60,
                max((_g_mono(text, 12) + 60 for _, text in rows), default=0),
                _g_sans(foot, 12) + 32,
            ),
        ),
    )
    head = 46 if sub else 40
    height = head + (8 + _ROW * len(rows) if rows else 0) + (26 if foot else 0)

    def draw(x: float, y: float) -> str:
        out = [f'<g class="fn {css}">{_tip(step)}<rect class="fbg" x="{x:g}" y="{y:g}" width="{width:g}" ']
        out.append(f'height="{height:g}" rx="10"/>{_badge(badge, x + 10, y + (head - 26) / 2)}')
        name = _esc(_clip(title, width - 58, measure))
        if sub:
            out.append(f'<text class="ft{" mono" if mono else ""}" x="{x + 46:g}" y="{y + 21:g}">{name}</text>')
            out.append(
                f'<text class="fs" x="{x + 46:g}" y="{y + 38:g}">{_esc(_clip(sub, width - 58, _sans(12)))}</text>'
            )
        else:
            out.append(
                f'<text class="ft{" mono" if mono else ""}" x="{x + 46:g}" y="{y + head / 2 + 4.5:g}">{name}</text>'
            )
        if rows:
            out.append(f'<path class="fl" d="M{x:g} {y + head:g}h{width:g}"/>')
        for i, (kind, text) in enumerate(rows):
            row = y + head + 8 + _ROW * i + 14
            logo = _logo(_logo_name(kind, text), x + 14, row - 11, 14)
            out.append(
                logo
                or f'<circle class="fdot k-{_KIND_OF.get(kind, "quiet")}" cx="{x + 21:g}" cy="{row - 4:g}" r="3.5"/>'
            )
            out.append(f'<text class="fr" x="{x + 36:g}" y="{row:g}">{_esc(_clip(text, width - 48, _mono(12)))}</text>')
        if foot:
            said = f'<text class="ff" x="{x + 14:g}" y="{y + height - 10:g}">{_esc(foot)}</text>'
            out.append(f'<a href="#{link}">{said}</a>' if link else said)
        out.append("</g>")
        return "".join(out)

    return _Box(width, height, width / 2, [draw])


def _end(text: str, css: str, glyph: str, step: CodeStep | None = None) -> _Box:
    """
    Where a path ends: the function returns or raises, or the loop goes on to its next item or stops.
    """
    text = _clip(text, _END_MOST, _mono(12.5))
    width = _g_mono(text, 12.5) + 48
    marks = {
        "stop": lambda x, y: f'<path class="fgl fill" d="M{x + 15:g} {y + 11:g}h10v10h-10Z"/>',
        "back": lambda x, y: (
            f'<path class="fgl" transform="translate({x + 12:g} {y + 8:g})" '
            'd="M6 4 L2.5 7.5 L6 11 M2.5 7.5 H10 a4 4 0 0 1 4 4 V13"/>'
        ),
        "loop": lambda x, y: f'<path class="fgl" transform="translate({x + 12:g} {y + 8:g})" d="{_LOOP}"/>',
        "out": lambda x, y: (
            f'<path class="fgl" transform="translate({x + 12:g} {y + 8:g})" d="M8 2v9M4 7.5l4 4 4-4M3 14h10"/>'
        ),
        "raise": lambda x, y: (
            f'<circle class="fgl fill" cx="{x + 20:g}" cy="{y + 16:g}" r="7.5"/>'
            f'<path class="fgx" d="M{x + 20:g} {y + 12:g}v4.5M{x + 20:g} {y + 19.3:g}v.2"/>'
        ),
    }

    def draw(x: float, y: float) -> str:
        return (
            f'<g class="fp {css}">{_tip(step)}<rect x="{x:g}" y="{y:g}" width="{width:g}" height="32" rx="16"/>'
            f'{marks[glyph](x, y)}<text x="{x + 34:g}" y="{y + 20.5:g}">{_esc(text)}</text></g>'
        )

    return _Box(width, 32, width / 2, [draw], goes_on=False)


_LOOP = "M12.4 9.3A4.6 4.6 0 1 1 11.3 4.7M12.1 2.3v2.8H9.3"  # the graph's loop mark


def _question(text: str, step: CodeStep | None) -> _Box:
    """
    A decision: the test, in a box pointed at both ends.
    """
    text = _clip(text, _QUESTION_MOST, _mono(13))
    width, height = _g_mono(text, 13) + 56, 44

    def draw(x: float, y: float) -> str:
        m = height / 2
        shape = (
            f"M{x:g} {y + m:g} L{x + 18:g} {y:g} H{x + width - 18:g} L{x + width:g} {y + m:g} "
            f"L{x + width - 18:g} {y + height:g} H{x + 18:g}Z"
        )
        return (
            f'<g class="fq">{_tip(step)}<path d="{shape}"/><text x="{x + width / 2:g}" y="{y + m + 4.5:g}" '
            f'text-anchor="middle">{_esc(text)}</text></g>'
        )

    return _Box(width, height, width / 2, [draw])


def _frame(body: _Box, title: str, css: str, *, sub: str = "", back: str = "", step: CodeStep | None = None) -> _Box:
    """
    A box around a path: a loop, with an arrow from the end of its lines back to its top saying back ('next
    order'), a try, an else, or a call opened in place.
    """
    head = 46 if sub else 40
    room = _g_sans(title, 13, True) + 60 if css != "fcall" else _g_mono(title, 13) + 60
    left = 44 if back else 22
    width = max(body.width + left + 22, room, _BOX_LEAST + 40)
    middle = left + body.middle
    if body.width + left + 22 < width:  # the lines in the middle of a box wider than they are
        middle = max(middle, width / 2)
    below = 40 if back and body.goes_on else 20
    height = head + _GAP + body.height + below
    marks = {
        "floop": f'<path class="fgl" transform="translate({{x}} {{y}})" d="{_LOOP}"/>',
        "fcall": '<text class="fgt" x="{x}" y="{y}" dx="3" dy="13">λ</text>',
        "ftry": '<path class="fgl" transform="translate({x} {y})" d="M3 8a5 5 0 1 0 1.5-3.6M3 2v3h3"/>',
        "felse": '<path class="fgl" transform="translate({x} {y})" d="M8 2v10M4 8l4 4 4-4"/>',
    }

    def draw(x: float, y: float) -> str:
        out = [f'<g class="fx {css}">{_tip(step)}<rect class="fxb" x="{x:g}" y="{y:g}" width="{width:g}" ']
        out.append(f'height="{height:g}" rx="14"/>')
        out.append(marks[css].replace("{x}", f"{x + 14:g}").replace("{y}", f"{y + 12:g}"))
        mono = " mono" if css == "fcall" else ""
        out.append(f'<text class="fxt{mono}" x="{x + 36:g}" y="{y + 25:g}">{_esc(title)}</text>')
        if sub:
            out.append(f'<text class="fs" x="{x + 36:g}" y="{y + 41:g}">{_esc(sub)}</text>')
        out.append(f'<path class="fl" d="M{x:g} {y + head:g}h{width:g}"/></g>')
        out.append(_arrow([(x + middle, y + head), (x + middle, y + head + _GAP)]))
        out.append(body.draw(x + middle - body.middle, y + head + _GAP))
        if back and body.goes_on:
            bottom = y + head + _GAP + body.height
            lane = x + 18
            out.append(
                _arrow(
                    [(x + middle, bottom), (x + middle, bottom + 18), (lane, bottom + 18), (lane, y + head + 1)],
                    "back",
                )
            )
            out.append(_word(lane + 6, bottom + 18, back, "fwl"))
        return "".join(out)

    return _Box(width, height, middle, [draw])


# ---------------------------------------------------------------- the code, as boxes


def _plain(markup: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def _reaches(step: CodeStep) -> list[tuple[str, str]]:
    """
    What a step and every step under it reach outside the code, and the warnings about them, once each.
    """
    found: list[tuple[str, str]] = []
    for s in step.walk():
        for kind, text in s.notes:
            if kind.startswith(_REACHES) or kind == "warn":
                if (kind, text) not in found:
                    found.append((kind, text))
    return found


def _decisions(step: CodeStep) -> int:
    """
    The decisions made under a step: its ifs (a match counts once), loops and trys.
    """
    return sum(
        1 for s in step.walk() if s is not step and s.kind in ("if", "loop", "try") and not s.code.startswith("case ")
    )


@dataclass
class _Context:
    """
    Where a flow's drawing is: the loops around (their item, innermost last) and how many calls deep. anchor gives
    a call opened nowhere a flow of its own, and the id of it to link to.
    """

    anchor: Callable[[CodeStep], str]
    loops: list[str] = field(default_factory=list)
    depth: int = 0


def _call_box(call: CodeStep, context: _Context) -> _Box:
    """
    A call to one of its own functions: opened in place when it makes decisions and there's room, else a box with
    what it reaches.
    """
    name = f"{_short_name(call.name)}()"
    made = _decisions(call)
    if made and not call.seen and context.depth < _OPEN_DEPTH:
        inside = _Context(context.anchor, list(context.loops), context.depth + 1)
        body = _stack(_boxes(call.steps, inside))
        opened = _frame(body, name, "fcall", sub=f"{call.file} line {call.line}", step=call)
        if opened.height <= _OPEN_TALL:
            return opened
    rows = _reaches(call)
    if len(rows) > _ROWS_MOST:
        rows = rows[: _ROWS_MOST - 1] + [("more", f"+{len(rows) - _ROWS_MOST + 1} more")]
    link = context.anchor(call) if made else ""
    foot = f"◇ {_plural(made, 'decision')} inside · its flow ↓" if link else ""
    sub = f"{call.file} line {call.line}" + (", again" if call.seen else "")
    return _card(name, sub=sub, rows=rows, badge="call", css="k-call", mono=True, foot=foot, link=link, step=call)


def _taken(step: CodeStep) -> list[tuple[str, str]]:
    """
    The names a line takes from what comes in or the environment, as (name, where): ('bucket', 'event').
    """
    if step.kind != "do" or step.calls or any(k.startswith(_REACHES) for k, _ in step.notes):
        return []
    words = {what.split(" ", 1)[0] for _, what in step.holds}
    if not step.holds or len(words) != 1 or not words <= {"event", "request", "env"}:
        return []
    return [(name, what.split(" ", 1)[0]) for name, what in step.holds]


def _line_box(step: CodeStep, context: _Context) -> _Box:
    """
    A line that does something: its calls into its own functions, else what it reaches, logs or takes.
    """
    own = [call for call in step.calls if call.kind == "def"]
    reach = next(((k, t) for k, t in step.notes if k in _SAID_FIRST), None)
    if own:
        boxes = [_call_box(call, context) for call in own]
        if reach and reach[0].startswith(_REACHES):
            boxes.append(_reach_box(step, *reach))
        return _stack(boxes)
    if reach:
        return _reach_box(step, *reach)
    for kind, text in step.notes:
        if kind in ("log", "warn"):
            return _card(_plain(_note_said(kind, text)), badge="log", css="k-quiet", step=step)
    for name, what in step.holds:
        word = what.split(" ", 1)[0]
        if word in ("event", "request"):
            return _card(f"Takes {name} from the {word}", badge="event", css="k-event", step=step)
        if word == "env":
            return _card(f"Takes {name} from the environment", badge="env", css="k-env", step=step)
    for kind, text in step.notes:
        if kind in ("event", "env"):
            return _card(_plain(_note_said(kind, text)), badge=kind, css=f"k-{kind}", step=step)
    if step.steps:  # a class, its body run where it's defined
        return _stack(_boxes(step.steps, context))
    return _card(step.code, badge="code", css="k-quiet", mono=True, step=step)


def _reach_box(step: CodeStep, kind: str, text: str) -> _Box:
    name = _logo_name(kind, text)
    warnings = [(k, t) for k, t in step.notes if k == "warn"]
    return _card(
        _plain(_note_said(kind, text)),
        sub=f"line {step.line}",
        rows=warnings,
        badge=f"logo:{name}" if name and logo_for(name, 26) else "dot",
        css=f"k-{_KIND_OF.get(kind, 'quiet')}",
        step=step,
    )


def _leaves(step: CodeStep, context: _Context) -> _Box:
    """
    The end of the lines under an if, an else or an except that leave the loop.
    """
    if step.ends == "continue":
        item = context.loops[-1] if context.loops else ""
        return _end(f"skips to the next {item}" if item else "goes round again", "fskip", "loop", step)
    if step.ends == "break":
        return _end("leaves the loop", "fskip", "out", step)
    return _NOTHING


def _answer(step: CodeStep | None, context: _Context) -> _Box:
    if step is None:
        return _NOTHING
    return _stack([*_boxes(step.steps, context), _leaves(step, context)])


def _boxes(steps: list[CodeStep], context: _Context) -> list[_Box]:
    """
    A function's lines, or a block's, as boxes one under the other.
    """
    out: list[_Box] = []
    i = 0
    while i < len(steps):
        step = steps[i]
        taken = _taken(step)
        if taken:  # lines in a row that only take names from what comes in: one box
            where = taken[0][1]
            while i + 1 < len(steps) and {w for _, w in _taken(steps[i + 1])} == {where}:
                i += 1
                taken += _taken(steps[i])
            names = ", ".join(dict.fromkeys(name for name, _ in taken))
            said = f"Takes {names} from the environment" if where == "env" else f"Takes {names} from the {where}"
            out.append(
                _card(
                    said,
                    badge="env" if where == "env" else "event",
                    css=f"k-{'env' if where == 'env' else 'event'}",
                    step=step,
                )
            )
        elif step.kind == "if" and step.code.startswith("match "):
            out.append(_match_box(step, context))
        elif step.kind == "if":
            chain = [step]
            while i + 1 < len(steps) and steps[i + 1].kind == "if" and steps[i + 1].code.startswith("elif "):
                i += 1
                chain.append(steps[i])
            otherwise = None
            if i + 1 < len(steps) and steps[i + 1].kind == "else":
                i += 1
                otherwise = steps[i]
            out.append(_decision_box([(_test(s.code), s) for s in chain], otherwise, context))
        elif step.kind == "try":
            handlers = []
            while i + 1 < len(steps) and steps[i + 1].kind == "except":
                i += 1
                handlers.append(steps[i])
            out.append(_try_box(step, handlers, context))
        elif step.kind == "else":
            after = steps[i - 1].kind if i else ""
            title = (
                "Finally, whatever happened above"
                if step.code.startswith("finally")
                else "If nothing in the try raised"
                if after in ("try", "except")
                else "If the loop ran to its end, with no break"
            )
            out.append(_frame(_answer(step, context), title, "felse", step=step))
        elif step.kind == "loop":
            out.append(_loop_box(step, context))
        elif step.kind == "with":
            out.append(
                _stack([*[_call_box(c, context) for c in step.calls if c.kind == "def"], *_boxes(step.steps, context)])
            )
        elif step.kind == "return":
            out.append(_return_box(step, context))
        elif step.kind == "raise":
            what = step.code.removeprefix("raise").strip()
            out.append(_end(f"Raises {what}" if what else "Raises the error again", "fraise", "raise", step))
        elif step.kind in ("do", "def"):
            out.append(_line_box(step, context))
        i += 1
    return out


def _test(code: str) -> str:
    found = re.fullmatch(r"(?:el)?if (.+):", code.strip())
    return found.group(1) if found else code


def _return_box(step: CodeStep, context: _Context) -> _Box:
    what = step.code.removeprefix("return").strip() or "None"
    calls = [_call_box(c, context) for c in step.calls if c.kind == "def"]
    if context.depth:  # the end of a call opened in place: back to its caller
        end = _end(f"returns {what}", "fback", "back", step)
    else:
        end = _end(f"Returns {what}", "fret", "stop", step)
    return _stack([*calls, end])


def _loop_box(step: CodeStep, context: _Context) -> _Box:
    found = re.fullmatch(r"(?:async )?for (.+?) in (.+):", step.code)
    if found:
        item, items = found.groups()
        title, back, leaving = f"For each {item} in {items}", f"next {item}", "when every one is done"
    else:
        item, title, back, leaving = (
            "",
            f"While {step.code.removeprefix('while ').rstrip(':')}",
            "again",
            "when it stops",
        )
    before = [_call_box(c, context) for c in step.calls if c.kind == "def"]  # what gives it its items: once
    context.loops.append(item)
    body = _stack(_boxes(step.steps, context))
    context.loops.pop()
    box = _frame(body, title, "floop", back=back, step=step)
    box.leaving = leaving
    return _stack([*before, box]) if before else box


def _decision_box(chain: list[tuple[str, CodeStep]], otherwise: CodeStep | None, context: _Context) -> _Box:
    """
    A question and its two answers: the one that goes on down the middle, the other beside it. An elif is the next
    question, on the no path; `if not x` is asked as x, so yes stays the usual answer.
    """
    test, step = chain[0]
    yes = _answer(step, context)
    if len(chain) > 1:
        no = _decision_box(chain[1:], otherwise, context)
    else:
        no = _answer(otherwise, context)
    if test.startswith("not ") and len(chain) == 1:
        test, yes, no = test[4:], no, yes
        said = ("no", "yes")
    else:
        said = ("yes", "no")
    yes_word, no_word = said
    # the answer that ends early, or the only one with lines, goes beside the path; else the next question stays
    # in the middle, and yes does when there's none
    if not no.height or (yes.height and not yes.goes_on and no.goes_on) or (len(chain) > 1 and yes.goes_on):
        down, side, down_word, side_word = no, yes, no_word, yes_word
    else:
        down, side, down_word, side_word = yes, no, yes_word, no_word
    if not side.height:
        down, side, down_word, side_word = side, down, side_word, down_word
    question = _question(test + "?", step)
    half = question.width / 2
    right_of_down = max(down.width - down.middle, half) if down.height else half
    side_x = right_of_down + _SIDE + side.middle  # the side path, from the middle
    left = max(question.middle, down.middle if down.height else 0)
    right = max(half, side_x + side.width - side.middle)
    top = question.height + _GAP + 6
    down_on = down.goes_on or not down.height
    goes_on = down_on or side.goes_on
    meet = max(top + down.height, top + side.height) + (18 if side.goes_on else 0)  # clear of both
    height = meet

    def draw(x: float, y: float) -> str:
        c = x + left
        out = [question.draw(c - half, y)]
        if down.height:
            out.append(_arrow([(c, y + question.height), (c, y + top)]))
            out.append(down.draw(c - down.middle, y + top))
        if down_on and goes_on:
            out.append(
                _arrow([(c, y + (top + down.height if down.height else question.height)), (c, y + height)], head=False)
            )
        out.append(_word(c + 8, y + question.height + 14, down_word, f"fw{down_word}"))
        sx = c + side_x
        out.append(_arrow([(c + half, y + question.height / 2), (sx, y + question.height / 2), (sx, y + top)]))
        out.append(_word(c + half + 8, y + question.height / 2 - 12, side_word, f"fw{side_word}"))
        out.append(side.draw(sx - side.middle, y + top))
        if side.goes_on:
            out.append(_arrow([(sx, y + top + side.height), (sx, y + meet), (c + 6, y + meet)]))
            out.append(_join(c, y + meet))
        return "".join(out)

    return _Box(left + right, height, left, [draw], goes_on)


def _match_box(step: CodeStep, context: _Context) -> _Box:
    """
    A match: each case a question on the no path of the one before.
    """
    subject = step.code.removeprefix("match ").rstrip(":")
    cases = [(f"{subject} is {case.code.removeprefix('case ').rstrip(':')}", case) for case in step.steps]
    if not cases:
        return _NOTHING
    if cases[-1][0].endswith(" is _"):  # the case for anything else
        last = cases.pop()[1]
        return _decision_box(cases, last, context) if cases else _answer(last, context)
    return _decision_box(cases, None, context)


def _try_box(step: CodeStep, handlers: list[CodeStep], context: _Context) -> _Box:
    """
    A try: its lines in a box, and beside it what runs when one of them raises, for the first except.
    """
    box = _frame(_stack(_boxes(step.steps, context)), "Tries", "ftry", step=step)
    if not handlers:
        return box
    handler = handlers[0]
    found = re.fullmatch(r"except (.+?)(?: as \w+)?:", handler.code)
    said = f"if it raises {found.group(1)}" if found else "if anything raises"
    if len(handlers) > 1:
        said += f" (+{len(handlers) - 1} more)"
    side = _answer(handler, context)
    if not side.height:
        side = _end("drops the error", "fwarn", "raise", handler)
        side.goes_on = True
    side_x = box.width - box.middle + _SIDE + side.middle
    meet = max(box.height, 70 + side.height) + (18 if side.goes_on else 0)
    goes_on = box.goes_on or side.goes_on

    def draw(x: float, y: float) -> str:
        c = x + box.middle
        out = [box.draw(x, y)]
        sx = c + side_x
        out.append(_arrow([(x + box.width, y + 20), (sx, y + 20), (sx, y + 70)], "fail"))
        out.append(_word(x + box.width + 8, y + 8, said, "fwf"))
        out.append(side.draw(sx - side.middle, y + 70))
        if box.goes_on:
            out.append(_arrow([(c, y + box.height), (c, y + meet)], head=False))
        if side.goes_on:
            out.append(_arrow([(sx, y + 70 + side.height), (sx, y + meet), (c + 6, y + meet)]))
            out.append(_join(c, y + meet))
        return "".join(out)

    return _Box(box.middle + side_x + side.width - side.middle, meet, box.middle, [draw], goes_on)


# ---------------------------------------------------------------- the flows


def flow_entries(steps: list[CodeStep]) -> list[tuple[CodeStep, str]]:
    """
    The functions each call starts in, with the route each is for: the entry point, or a web app's routes.
    """
    if len(steps) == 1 and steps[0].steps and all(s.kind == "def" for s in steps[0].steps):
        return [(s, next((t for k, t in s.notes if k == "route"), "")) for s in steps[0].steps if not s.seen]
    return [(s, "") for s in steps if s.kind == "def"]


def _flow_svg(entry: CodeStep, route: str, comes_in: tuple[str, str], context: _Context, first: bool) -> str:
    boxes = []
    if route:
        boxes.append(_card(route, sub="a request comes in", badge="event", css="k-event", mono=True))
    elif first and comes_in[0]:
        boxes.append(_card(comes_in[0], sub=comes_in[1], badge="event", css="k-event"))
    name = f"{_short_name(entry.name)}()"
    css = "k-entry" if first else "k-call"
    boxes.append(
        _card(
            name,
            sub=f"{entry.file} line {entry.line}",
            badge="entry" if first else "call",
            css=css,
            mono=True,
            step=entry,
        )
    )
    boxes += _boxes(entry.steps, context)
    body = _stack(boxes)
    if body.goes_on:
        end = "Returns None" if first else "returns None"
        body = _stack([body, _end(end, "fret" if first else "fback", "stop" if first else "back")])
    width, height = body.width + 2 * _PAD, body.height + 2 * _PAD
    return (
        f'<svg viewBox="0 0 {width:g} {height:g}" width="{width:g}" height="{height:g}" role="img" '
        f'aria-label="How {_esc(name)} decides what to do">{body.draw(_PAD, _PAD)}</svg>'
    )


_KEY = (
    '<div class="fkey">'
    '<span><svg width="34" height="18" aria-hidden="true"><path class="kq" d="M2 9 L8 2 H26 L32 9 L26 16 H8Z"/></svg>'
    'a decision: <b class="fwyes">yes</b> and <b class="fwno">no</b> on its arrows</span>'
    '<span><svg width="30" height="18" aria-hidden="true"><rect class="kl" x="1" y="1" width="28" height="16" rx="5"/></svg>'
    "a loop: the arrow goes back for the next item</span>"
    '<span><svg width="30" height="18" aria-hidden="true"><rect class="kr" x="1" y="2" width="28" height="14" rx="7"/></svg>'
    "where the call ends</span>"
    '<span><svg width="30" height="18" aria-hidden="true"><rect class="kx" x="1" y="2" width="28" height="14" rx="7"/></svg>'
    "it raises</span>"
    '<span><svg width="30" height="10" aria-hidden="true"><path class="kf" d="M1 5h28"/></svg>when a line raises</span>'
    "</div>"
)


@_draws(_Flow, "html")
def _flow_html(block: _Flow, report: _Report) -> str:
    made = report.shared("flows", lambda: [0])  # flows drawn so far, so each has ids of its own
    group = f"cnd-flow{made[0]}"
    made[0] += 1
    entries = flow_entries(block.steps)
    if not entries:
        return f"<p>{_esc(block.empty)}</p>"
    own: dict[str, str] = {}  # a call opened nowhere -> the id of its flow
    later: list[CodeStep] = []

    def anchor(call: CodeStep) -> str:
        if call.name not in own:
            own[call.name] = f"{group}-{len(own)}"
            later.append(call)
        return own[call.name]

    out = [f"<h3>{_esc(block.title)}</h3>" if block.title else ""]
    shown = 0
    for i, (entry, route) in enumerate(entries[:_FLOWS_MOST]):
        svg = _flow_svg(entry, route, block.comes_in, _Context(anchor), first=True)
        head = (
            f'<p class="fhd"><code>{_esc(_short_name(entry.name))}()</code>{f" · {_esc(route)}" if route else ""}</p>'
        )
        out.append(f'<div class="cdf">{head if len(entries) > 1 else ""}<div class="cdfc">{svg}</div></div>')
        shown += 1
    done = 0
    while done < len(later) and shown < _FLOWS_MOST:  # the calls opened nowhere, each with a flow of its own
        call = later[done]
        done += 1
        svg = _flow_svg(call, "", block.comes_in, _Context(anchor, depth=1), first=False)
        out.append(
            f'<div class="cdf" id="{own[call.name]}"><p class="fhd">Inside <code>{_esc(_short_name(call.name))}()'
            f'</code> <small>{_esc(call.file)} line {call.line}</small></p><div class="cdfc">{svg}</div></div>'
        )
        shown += 1
    left = len(entries) - min(len(entries), _FLOWS_MOST) + len(later) - done
    if left:
        out.append(f'<p class="fmore">And {_plural(left, "more flow")}, left out to keep the page light.</p>')
    return "".join(out) + _KEY


# ---------------------------------------------------------------- in text


def _said(steps: list[CodeStep]) -> str:
    """
    Where an answer goes, in a few words: its first line that does something, then how it ends.
    """
    words = []
    for step in steps:
        if step.kind in ("do", "def"):
            own = [c for c in step.calls if c.kind == "def"]
            reach = next(((k, t) for k, t in step.notes if k in _SAID_FIRST or k == "log"), None)
            if own:
                words.append("calls " + ", ".join(f"{_short_name(c.name)}()" for c in own))
            elif reach:
                said = _plain(_note_said(*reach))
                words.append(said[:1].lower() + said[1:])
        elif step.kind == "return":
            words.append(f"returns {step.code.removeprefix('return').strip() or 'None'}")
        elif step.kind == "raise":
            words.append(f"raises {step.code.removeprefix('raise').strip() or 'the error again'}")
        elif step.kind in ("if", "loop", "try"):
            words.append("decides more (below)")
    return ", then ".join(words[:3]) + (" …" if len(words) > 3 else "")


_ENDS = {"continue": "skips to the next item", "break": "leaves the loop"}


def _answer_said(step: CodeStep | None) -> str:
    if step is None:
        return "goes on"
    said = _said(step.steps)
    ends = _ENDS.get(step.ends, "")
    return ", then ".join(filter(None, [said, ends])) or "goes on"


def _text_lines(steps: list[CodeStep], pad: int, out: list[str], answered: bool = False) -> None:
    """
    Each decision under steps as a line saying where each answer goes, its loops, trys and ends, indented as the code
    is; the calls that make decisions of their own after the line calling them. answered: steps are an answer's,
    whose end its question's line said.
    """
    indent = " " * pad
    i = 0
    while i < len(steps):
        step = steps[i]
        under: list[CodeStep] = [step]
        if step.kind == "if" and not step.code.startswith("match "):
            chain = [step]
            while i + 1 < len(steps) and steps[i + 1].kind == "if" and steps[i + 1].code.startswith("elif "):
                i += 1
                chain.append(steps[i])
            otherwise = None
            if i + 1 < len(steps) and steps[i + 1].kind == "else":
                i += 1
                otherwise = steps[i]
            for k, asked in enumerate(chain):
                test, yes = _test(asked.code), _answer_said(asked)
                no = "asks the next question" if k + 1 < len(chain) else _answer_said(otherwise)
                if test.startswith("not ") and len(chain) == 1:
                    test, yes, no = test[4:], no, yes
                out.append(f"{asked.line:>5}  {indent}{test}?  yes: {yes} · no: {no}")
            under = [*chain, *([otherwise] if otherwise else [])]
        elif step.kind == "if":
            out.append(f"{step.line:>5}  {indent}{step.code.rstrip(':')}")
        elif step.kind == "loop":
            out.append(f"{step.line:>5}  {indent}{step.code.rstrip(':')}  (back to its top for each)")
        elif step.kind == "try":
            out.append(f"{step.line:>5}  {indent}tries:")
        elif step.kind == "except":
            out.append(f"{step.line:>5}  {indent}{step.code.rstrip(':')}: {_answer_said(step)}")
        elif step.kind == "return" and not answered:
            out.append(f"{step.line:>5}  {indent}returns {step.code.removeprefix('return').strip() or 'None'}")
        elif step.kind == "raise" and not answered:
            out.append(f"{step.line:>5}  {indent}raises {step.code.removeprefix('raise').strip() or 'the error again'}")
        for each in under:
            for call in each.calls:
                if call.kind == "def" and _decisions(call) and not call.seen:
                    out.append(f"{each.line:>5}  {indent}  ↳ {_short_name(call.name)}()  {call.file} line {call.line}")
                    _text_lines(call.steps, pad + 4, out)
            if each.kind != "do":
                _text_lines(each.steps, pad + 2, out, answered=each.kind in ("if", "else", "except"))
        i += 1


@_draws(_Flow, "text")
def _flow_lines(block: _Flow, report: _Report) -> list[str]:
    out = ["", f"-- {block.title} --"] if block.title else [""]
    entries = flow_entries(block.steps)
    if not entries:
        return out + [block.empty]
    for entry, route in entries[:_FLOWS_MOST]:
        out.append(f"  {_short_name(entry.name)}()  {entry.file} line {entry.line}{f'  ({route})' if route else ''}")
        if not _decisions(entry):
            out.append("       (no decisions: one path from start to end)")
            continue
        _text_lines(entry.steps, 0, out)
    return out
