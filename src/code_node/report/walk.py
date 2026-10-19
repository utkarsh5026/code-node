"""
_Walk: the steps as a walk through the code, one line at a time, as a debugger steps: a list of every step on the left,
and on the right the function the current step is in, its line lit, with Back, Next, Step over and Step out.

No JavaScript: each step is a radio button (one group, so once one has focus the arrow keys step through them).
Each function's steps sit in a box of their own, with the function's code drawn once at the end of it; the CSS shows
the card after the checked button and the code of its box with sibling selectors, so the light slides from line to
line as you step, and a step costs the same however many there are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from ..kit.blocks import _Report, _draws
from ..kit.fmt import _plural
from ..kit.highlight import _python_html, _python_lines
from ..kit.render import _prose
from ..kit.text import _esc

from ..analysis.findings import _short_name
from ..analysis.model import CodeFunction, CodeStep
from .outline import _NOTE_TIPS, _Outline, _chips_html, _outline_lines
from .style import _ROOT

_GROUP = "cnd-walk"  # the radio buttons' name: one group, so the arrow keys move through every step

_LIST_CHIPS = 2  # tags a step shows in the list; its card shows them all

_FRAME_LINES = 160  # a function or file longer than this shows only the lines around its steps
_FRAME_AROUND = 4  # lines kept above and below each step then

_KIND_SAYS = {  # what a line of each kind means, said once on its card
    "loop": "A loop: the lines under it run once for each item.",
    "if": "A branch: the lines under it run only when this is true.",
    "with": "The lines under it run inside this block, which tidies up after them.",
    "try": "The lines under it run; if one of them raises, the except below it runs instead of the rest.",
    "except": "Runs only when a line in the try above it raises.",
    "raise": "Raises an error: the function stops here, and so does each caller that doesn't catch it.",
}


@dataclass
class _Walk:
    """
    What runs when the code is imported, then each call from the entry point, as stops to step through. functions
    are its own functions (for where each one ends and its docstring) and sources the files read ({file: its text});
    without a file's text, its function shows only the lines that are steps.
    """

    startup: list[CodeStep]
    steps: list[CodeStep]
    title: str = ""
    startup_title: str = "When Python imports it (once, before the first call)"
    calls_title: str = "Each call"
    functions: list[CodeFunction] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)
    empty: str = "(nothing it can follow)"


@dataclass
class _Frame:
    """
    The code a run of stops is in: a function whole (its decorators, def and body) or a module's file.
    """

    file: str
    start: int
    end: int
    name: str  # 'read_orders()', or the file for a module
    stops: dict[int, int] = field(default_factory=dict)  # line -> the first stop on it


@dataclass
class _Stop:
    """
    One step of the walk: a line (or a function being entered), where it sits in the list, and the calls it's inside.
    """

    step: CodeStep
    depth: int  # how far it's indented in the list
    frame: int
    lit: int  # the line of its frame it lights: its own, or for a call shown before, the line that calls it
    stack: tuple[tuple[str, int], ...]  # the calls it's inside, outermost first: (name, the stop that enters it)
    chapter: int  # 0: when it's imported, 1: each call
    caller: int | None = None  # a function being entered: the stop of the line that calls it


class _Walker:
    """
    Lays the outline's tree out flat, in the order the code runs, with a frame for each function (or module) it goes
    into: the stops in a frame are the ones its code shows.
    """

    def __init__(self, block: _Walk) -> None:
        self.functions = {f.name: f for f in block.functions}
        self.stops: list[_Stop] = []
        self.frames: list[_Frame] = []
        self.chapter = 0
        self.lines(block.startup, 0, None, ())
        self.chapter = 1
        self.lines(block.steps, 0, None, ())

    def frame(self, step: CodeStep) -> int:
        """
        A new frame for the function or module step goes into (or the file a line run at import is in).
        """
        known = self.functions.get(step.name) if step.kind == "def" else None
        if known:
            frame = _Frame(known.file, known.line, known.line + known.lines - 1, f"{_short_name(known.name)}()")
        elif step.kind == "def":
            last = max((s.line for s in step.walk() if s.line), default=step.line)
            frame = _Frame(step.file, step.line, last, f"{_short_name(step.name)}()")
        else:
            frame = _Frame(step.file, 1, 0, step.file)  # a module: its whole file, measured when it's drawn
        self.frames.append(frame)
        return len(self.frames) - 1

    def add(self, step: CodeStep, depth: int, frame: int, stack: tuple[tuple[str, int], ...],
            caller: int | None = None, lit: int | None = None) -> int:
        index = len(self.stops)
        lit = step.line if lit is None else lit
        self.stops.append(_Stop(step, depth, frame, lit, stack, self.chapter, caller))
        if lit:
            self.frames[frame].stops.setdefault(lit, index)
        return index

    def enter(self, step: CodeStep, depth: int, stack: tuple[tuple[str, int], ...], caller: int | None,
              frame: int | None) -> None:
        """
        A function (or module) being run: a stop on its def, then its own lines under it, in a frame of its own. One
        whose steps were shown before stays in the caller's frame, with the line that calls it lit.
        """
        name = f"{_short_name(step.name)}()" if step.kind == "def" else f"{step.file}, imported"
        inside = (*stack, (name, len(self.stops)))
        if step.seen and frame is not None and caller is not None:
            self.add(step, depth, frame, inside, caller, lit=self.stops[caller].lit)
            return
        own = self.frame(step)
        self.add(step, depth, own, inside, caller)
        if not step.seen:
            self.lines(step.steps, depth + 1, own, inside)

    def lines(self, steps: list[CodeStep], depth: int, frame: int | None, stack: tuple[tuple[str, int], ...]) -> None:
        for step in steps:
            if step.kind in ("def", "module"):
                self.enter(step, depth, stack, None, frame)
                continue
            if frame is None:  # a line run when its file is imported, outside any function
                frame = self.frame(step)
                stack = ((f"{step.file}, imported", len(self.stops)),)
            index = self.add(step, depth, frame, stack)
            for call in step.calls:
                self.enter(call, depth + 1, stack, index, frame)
            self.lines(step.steps, depth + 1, frame, stack)


def _after(stops: list[_Stop], i: int, deeper_than: int) -> int | None:
    """
    The first stop after i in no more than deeper_than calls: where Step over and Step out go.
    """
    return next((j for j in range(i + 1, len(stops)) if len(stops[j].stack) <= deeper_than), None)


def _name_of(step: CodeStep) -> str:
    return f"{_short_name(step.name)}()" if step.kind == "def" else step.file


def _says(stops: list[_Stop], i: int, first: dict[str, int], docs: dict[str, str]) -> str:
    """
    What the stop's line does, in a sentence or two (HTML).
    """
    stop = stops[i]
    step = stop.step
    if step.kind == "module":
        return f"<p>Python runs <b>{_esc(step.file)}</b> from the top, once, the first time it's imported.</p>"
    if step.kind == "def":
        name = f"<code>{_esc(_name_of(step))}</code>"
        if stop.caller is None:
            said = f"Each call starts here, in {name}." if stop.chapter else f"Python runs {name} here."
        else:
            calling = stops[stop.caller]
            said = (f"<code>{_esc(stop.stack[-2][0])}</code> calls {name} on line {calling.step.line}"
                    + (": its steps follow." if step.steps and not step.seen else "."))
        doc = docs.get(step.name, "")
        out = f"<p>{said}</p>" + (f'<p class="wdoc">{_esc(doc)}</p>' if doc else "")
        if step.seen and step.name in first:
            out += (f'<p>Its steps are shown where it\'s first called: <label class="wjump" for="cw{first[step.name]}">'
                    f"step {first[step.name] + 1}</label>.</p>")
        elif not step.steps and not step.notes:
            out += "<p>There's nothing in it to follow.</p>"
        return out
    said = []
    if step.kind == "return":
        here = f"<code>{_esc(stop.stack[-1][0])}</code>" if stop.stack else "The function"
        entered = stops[stop.stack[-1][1]] if stop.stack else None
        if entered is not None and entered.caller is not None and len(stop.stack) > 1:
            said.append(f"{here} ends here and hands this back to <code>{_esc(stop.stack[-2][0])}</code>, "
                        f"line {stops[entered.caller].step.line}.")
        else:
            said.append(f"{here} ends here: this is what the call returns.")
    elif step.kind == "else":
        said.append("Runs last, whether or not a line above it raised." if step.code.startswith("finally")
                    else "The other way: runs when the branch or loop above it doesn't.")
    elif step.kind in _KIND_SAYS:
        said.append(_KIND_SAYS[step.kind])
    if step.calls:
        names = ", ".join(f"<code>{_esc(_name_of(call))}</code>" for call in step.calls)
        said.append(f"Calls {names}: Next goes into it, Step over runs it and stops at the next line here."
                    if len(step.calls) == 1 else
                    f"Calls {names}: Next goes into each, Step over runs them and stops at the next line here.")
    return "".join(f"<p>{line}</p>" for line in said)


def _notes_html(step: CodeStep) -> str:
    """
    Each tag on the line with what it means: 'S3 GetObject reads · an AWS call that reads'.
    """
    rows = [f"<li>{_chips_html([note])}<span>{_esc(_NOTE_TIPS.get(note[0], ''))}</span></li>" for note in step.notes]
    return f'<ul class="wnotes">{"".join(rows)}</ul>' if rows else ""


def _button(target: int | None, text: str, css: str = "", tip: str = "") -> str:
    """
    A button that goes to stop target: a label for its radio button, or greyed out when there's nowhere to go.
    """
    title = f' title="{_esc(tip)}"' if tip else ""
    css = f"wbt {css}".strip()
    if target is None:
        return f'<span class="{css} off"{title}>{text}</span>'
    return f'<label class="{css}" for="cw{target}"{title}>{text}</label>'


def _card_html(stops: list[_Stop], i: int, first: dict[str, int], docs: dict[str, str]) -> str:
    """
    The current stop's card: Back and Next, where it is (the calls it's inside, each a link back to its start) and
    what its line does.
    """
    stop, total = stops[i], len(stops)
    depth = len(stop.stack)
    over = _after(stops, i, depth) if stop.step.calls else None
    out = _after(stops, i, depth - 1) if depth > 1 else None
    nav = [_button(i - 1 if i else None, "‹ Back"),
           f'<span class="wpos">Step <b>{i + 1}</b> of {total}</span>',
           _button(i + 1 if i + 1 < total else None, "Next ›", "go")]
    if over is not None and over != i + 1:
        nav.append(_button(over, "Step over", tip="Run the call and stop at the next line here"))
    if out is not None:
        nav.append(_button(out, "Step out", tip="Finish this function"))
    trail = []
    for k, (name, at) in enumerate(stop.stack):
        css = ' class="here"' if k == depth - 1 else ""
        trail.append(f'<label for="cw{at}"{css}>{_esc(name)}</label>')
    stack = '<span class="wsep">›</span>'.join(trail)
    then = ""
    if i + 1 < total:
        nxt = stops[i + 1]
        if nxt.chapter != stop.chapter:
            then = "Next: the first call, from the entry point"
        elif len(nxt.stack) < depth or (len(nxt.stack) == depth and nxt.stack[-1] != stop.stack[-1]):
            back = nxt.stack[-1][0] if nxt.stack else ""
            then = f"Next: back in {back}, line {nxt.step.line}" if nxt.step.line else f"Next: back in {back}"
    else:
        then = "That's the last step."
    return (f'<div class="wc"><div class="wnav">{"".join(nav)}</div>'
            f'<div class="wstk">{stack}</div><div class="wsay">{_says(stops, i, first, docs)}'
            f"{_notes_html(stop.step)}</div>"
            + (f'<div class="wthen">{_esc(then)}</div>' if then else "") + "</div>")


def _frame_rows(frame: _Frame, lines: list[str], stops: list[_Stop]) -> list[tuple[int, str]]:
    """
    The frame's lines, (number, HTML): from its file when it was read, else just its steps' lines. A long one keeps
    only the lines around its steps, with a (0, '') row where lines are left out.
    """
    if not lines:
        shown = {line: _python_html(stops[i].step.code) for line, i in frame.stops.items()}
        return sorted(shown.items())
    start, end = max(1, frame.start), min(len(lines), frame.end if frame.end else len(lines))
    while start > 1 and lines[start - 2].lstrip().startswith("@"):  # its decorators, over its def
        start -= 1
    if frame.stops:  # a step outside where its function was thought to end
        start, end = min(start, min(frame.stops)), max(end, min(len(lines), max(frame.stops)))
    while end > start and end not in frame.stops and not lines[end - 1].strip():
        end -= 1
    numbers = range(start, end + 1)
    if len(numbers) > _FRAME_LINES:
        near = {k for at in [frame.start, *frame.stops] for k in range(at - _FRAME_AROUND, at + _FRAME_AROUND + 1)}
        numbers = [k for k in numbers if k in near]
    rows: list[tuple[int, str]] = []
    for k in numbers:
        if rows and rows[-1][0] and k > rows[-1][0] + 1:
            rows.append((0, ""))
        rows.append((k, lines[k - 1]))
    return rows


def _frame_html(index: int, frame: _Frame, rows: list[tuple[int, str]]) -> str:
    """
    A frame's code, its lines numbered, each line that's a step a link to it, and the bar that lights the current one.
    """
    body = []
    for number, code in rows:
        at = frame.stops.get(number)
        if not number:
            body.append('<span class="sl gap"><span class="sn">⋯</span></span>')
        elif at is None:
            body.append(f'<span class="sl"><span class="sn">{number}</span>{code}</span>')
        else:
            body.append(f'<label class="sl" for="cw{at}"><span class="sn">{number}</span>{code}</label>')
    where = (f"line {rows[0][0]}" if len(rows) == 1 else f"lines {rows[0][0]}–{rows[-1][0]}") if rows else ""
    if any(not number for number, _ in rows):
        where += ", around its steps"
    name = "" if frame.name == frame.file else f"<b>{_esc(frame.name)}</b>"
    return (f'<div class="wf wf{index}" style="--n:{len(rows)}"><div class="wfh">{name}<span>{_esc(frame.file)}'
            f'</span><span class="wfl">{where}</span></div><div class="wfw"><div class="wfp"><div class="wbar"></div>'
            f'{"".join(body)}</div></div></div>')


def _item_html(stops: list[_Stop], i: int, card: str) -> str:
    """
    A step in the list: its radio button, then its line number and code (or the function it enters) and its first tags
    as the button's label, then its card, which shows (beside the list) while the button is checked.
    """
    stop = stops[i]
    step = stop.step
    if step.kind == "module":
        text = f'<span class="won">↳ <b>{_esc(step.file)}</b> <span class="wof">runs when it\'s imported</span></span>'
    elif step.kind == "def" and stop.caller is not None:
        text = (f'<span class="won">↳ <b>{_esc(_name_of(step))}</b> <span class="wof">{_esc(step.file)}'
                + (", shown before" if step.seen else "") + "</span></span>")
    else:
        text = f'<code class="wcd">{_python_html(step.code)}</code>'
    notes = step.notes if step.kind != "def" or stop.caller is None else []
    chips = _chips_html(notes[:_LIST_CHIPS]) + (
        f'<span class="wmore">+{len(notes) - _LIST_CHIPS}</span>' if len(notes) > _LIST_CHIPS else "")
    checked = " checked" if i == 0 else ""
    tags = f'<span class="wtags">{chips}</span>' if chips else ""
    line = "" if step.kind == "module" else step.line or ""
    return (f'<input type="radio" class="wr" name="{_GROUP}" id="cw{i}"{checked}><label class="wil k-{_esc(step.kind)}" '
            f'for="cw{i}" style="--d:{stop.depth}"><span class="ln">{line}</span><span class="wx">{text}{tags}</span>'
            f"</label>{card}")


@_draws(_Walk, "html")
def _walk_html(block: _Walk, report: _Report) -> str:
    """
    The list of steps, each function's (or module's) steps in a box of their own with its code after them: the CSS
    shows the card after the checked radio button, and the code of the box it's in (`.wr:checked ~ .wf`). No :has(),
    so a step costs the same however many there are; the one rule a step adds says which line of its code to light.
    """
    title = f"<h4>{_prose(block.title)}</h4>" if block.title else ""
    walker = _Walker(block)
    stops, frames = walker.stops, walker.frames
    if not stops:
        return title + f'<div class="more">{_esc(block.empty)}</div>'
    root = report.root or _ROOT
    highlighted: dict[str, list[str]] = {}
    first: dict[str, int] = {}
    for i, stop in enumerate(stops):
        if stop.step.kind == "def" and not stop.step.seen:
            first.setdefault(stop.step.name, i)
    docs = {f.name: f.doc for f in block.functions if f.doc}
    drawn, rows_of = [], []
    for k, frame in enumerate(frames):
        if frame.file in block.sources and frame.file not in highlighted:
            highlighted[frame.file] = _python_lines(block.sources[frame.file])
        rows = _frame_rows(frame, highlighted.get(frame.file, []), stops)
        rows_of.append({number: n for n, (number, _) in enumerate(rows) if number})
        drawn.append(_frame_html(k, frame, rows))
    out: list[str] = []
    opened: list[int] = []  # the frames whose boxes are open, innermost last
    chapter = -1
    for i, stop in enumerate(stops):
        if stop.chapter != chapter:
            while opened:
                out.append(drawn[opened.pop()] + "</div>")
            chapter = stop.chapter
            if chapter == 0:
                out.append(f'<div class="wch">{_esc(block.startup_title)}</div>')
            elif block.startup:
                out.append(f'<div class="wch">{_esc(block.calls_title)}</div>')
        while opened and opened[-1] != stop.frame and stop.frame in opened:  # back from a call
            out.append(drawn[opened.pop()] + "</div>")
        if not opened or opened[-1] != stop.frame:  # into a call
            out.append('<div class="wfn">')
            opened.append(stop.frame)
        out.append(_item_html(stops, i, _card_html(stops, i, first, docs)))
        at = rows_of[stop.frame].get(stop.lit)
        if at is not None:  # the line its code lights
            report.rules.add(f".{root} #cw{i}:checked~.wf{stop.frame}{{--k:{at}}}")
    while opened:
        out.append(drawn[opened.pop()] + "</div>")
    sub = (f'<div class="wsub">{_plural(len(stops), "step")} in the order the code runs. Next goes into each of its '
           "own functions it calls, Step over runs one without going in. Click a step (in the list or in the code), "
           "then <kbd>↑</kbd> <kbd>↓</kbd> step through.</div>")
    return (f'{title}{sub}<div class="walk"><div class="wl" role="radiogroup" aria-label="The steps">{"".join(out)}'
            '</div><div class="ws"></div></div>')


@_draws(_Walk, "text")
def _walk_lines(block: _Walk, report: _Report) -> list[str]:
    out: list[str] = []
    if block.startup:
        out += _outline_lines(_Outline(block.startup, block.startup_title), report)
    return out + _outline_lines(_Outline(block.steps, block.title, empty=block.empty), report)


def walk_stops(block: _Walk) -> list[tuple[int, str, list[str]]]:
    """
    The walk's stops in the order they're stepped through: (line, code, the calls it's inside, outermost first).
    """
    return [(s.step.line, s.step.code, [name for name, _ in s.stack]) for s in _Walker(block).stops]
