"""
_Walk: the steps as a walk through the code, one line at a time, as a debugger steps: a list of every step on the left,
each said in a few plain words, and on the right what the current one does and the function it's in, its line lit,
with Back, Next, Skip call (step over) and Finish (step out).

No JavaScript: each step is a radio button (one group, so once one has focus the arrow keys step through them).
Each function's steps sit in a box of their own, with the function's code drawn once at the end of it; the CSS shows
the card after the checked button and the code of its box with sibling selectors, so the light slides from line to
line as you step, and a step costs the same however many there are.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from ..kit.blocks import _Report, _draws
from ..kit.fmt import _plural
from ..kit.highlight import _python_html, _python_lines
from ..kit.render import _prose
from ..kit.text import _esc

from ..analysis.findings import _short_name
from ..analysis.model import CodeFunction, CodeStep
from ..analysis.syntax import _a
from .editor import editor_name, open_at
from .outline import _NOTE_TIPS, _Outline, _chips_html, _outline_lines
from .style import _ROOT

_GROUP = "cnd-walk"  # the radio buttons' name: one group, so the arrow keys move through every step

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

_AWS_DOES = {  # an AWS call, by what it does, as a sentence: 'Reads from S3 (GetObject)'
    "reads": "Reads from {}",
    "writes": "Writes to {}",
    "sends": "Sends a message with {}",
    "runs": "Starts something in {}",
    "signs": "Makes a signed link for {}",
}

_LIB_DOES = {"reads": "Reads from {}", "writes": "Writes to {}", "sends": "Sends a message with {}", "runs": "Calls {}"}

_SAID_FIRST = (
    "aws-reads",
    "aws-writes",
    "aws-sends",
    "aws-runs",
    "aws-signs",
    "lib-reads",
    "lib-writes",
    "lib-sends",
    "lib-runs",
    "http",
    "command",
    "file",
    "sleep",
    "client",
)  # the tags that say what a line is for, before the calls and names in it

_DOTS = (
    "aws-reads",
    "aws-writes",
    "aws-sends",
    "aws-runs",
    "aws-signs",
    "lib-reads",
    "lib-writes",
    "lib-sends",
    "lib-runs",
    "http",
)  # what's marked in the list

_HEADERS = [  # a block's first line -> what it does: (pattern, sentence with {} for what it matched)
    (r"(?:async )?for (.+?) in (.+):", "Goes through each {} in {}"),
    (r"while (.+):", "Repeats while {}"),
    (r"(?:el)?if (.+):", "If {}"),
    (r"match (.+):", "Picks a case for {}"),
    (r"case (.+):", "Case {}"),
    (r"(?:async )?with (.+):", "With {}"),
    (r"except (.+?)(?: as \w+)?:", "If it fails with {}"),
    (r"return (.+)", "Returns {}"),
    (r"raise (.+)", "Raises {}"),
]

_BARE = {
    "try:": "Tries the lines under it",
    "except:": "If anything under the try fails",
    "else:": "Otherwise",
    "finally:": "Finally, whatever happened above",
    "return": "Returns",
    "raise": "Raises the error again",
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
    startup_title: str = "When Python imports it, once, before the first call"
    calls_title: str = "Each call"
    functions: list[CodeFunction] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)
    empty: str = "(nothing it can follow)"
    editor: str = ""  # a link to open a line in an editor, from editor_link(): each step's card links to its line


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

    def add(
        self,
        step: CodeStep,
        depth: int,
        frame: int,
        stack: tuple[tuple[str, int], ...],
        caller: int | None = None,
        lit: int | None = None,
    ) -> int:
        index = len(self.stops)
        lit = step.line if lit is None else lit
        self.stops.append(_Stop(step, depth, frame, lit, stack, self.chapter, caller))
        if lit:
            self.frames[frame].stops.setdefault(lit, index)
        return index

    def enter(
        self, step: CodeStep, depth: int, stack: tuple[tuple[str, int], ...], caller: int | None, frame: int | None
    ) -> None:
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
    The first stop after i in no more than deeper_than calls: where Skip call and Finish go.
    """
    return next((j for j in range(i + 1, len(stops)) if len(stops[j].stack) <= deeper_than), None)


def _name_of(step: CodeStep) -> str:
    return f"{_short_name(step.name)}()" if step.kind == "def" else step.file


def _code(text: str) -> str:
    return f"<code>{_esc(text)}</code>"


def _note_said(kind: str, text: str) -> str:
    """
    One of a line's tags as the start of a sentence (HTML): 'Reads from S3 (GetObject)', 'Sends an HTTP POST request'.
    """
    if kind.startswith("lib-"):
        service, _, operation = text.partition(": ")
        return _esc(_LIB_DOES.get(kind[4:], "Calls {}").format(service)) + (
            f" ({_esc(operation)})" if operation else ""
        )
    if kind.startswith("aws-"):
        service, _, operation = text.rpartition(" ")
        if " waiter" in service:
            return f"Waits for {_esc(text)}"
        return _esc(_AWS_DOES.get(kind[4:], "Calls {}").format(service or text)) + (
            f" ({_esc(operation)})" if service else ""
        )
    if kind == "http":
        verb, _, where = text.removeprefix("HTTP ").partition(" ")
        return f"Sends an HTTP {_esc(verb)} request" + (f" to {_code(where)}" if where else "")
    if kind == "env":
        return f"Reads the environment variable {_code(text)}"
    if kind == "event":  # 'request query.q': the platform's word for its input, then the field
        word, _, part = text.partition(" ")
        return f"Reads {_code(part)} from the {_esc(word)}"
    return _esc(text[:1].upper() + text[1:])


def _headline(stop: _Stop) -> tuple[str, str]:
    """
    What the stop does, in a few plain words (HTML), and the tag it's about, if any: 'Reads from S3 (GetObject)',
    'Goes through each record in event['Records']', 'Takes bucket from the event'.
    """
    step = stop.step
    if step.kind == "module":
        return f"Runs {_code(step.file)}, once", ""
    if step.kind == "def":
        name = _code(_name_of(step))
        if stop.caller is None:
            return (f"Each call starts in {name}" if stop.chapter else f"Runs {name}"), ""
        return (f"Calls {name} again" if step.seen else f"Goes into {name}"), ""
    if step.kind != "do":
        bare = _BARE.get(step.code.strip())
        if bare:
            return bare, ""
        for pattern, sentence in _HEADERS:
            found = re.fullmatch(pattern, step.code.strip())
            if found:
                return sentence.format(*(_code(part) for part in found.groups())), ""
        return f"Runs {_code(step.code)}", ""
    for kind, text in step.notes:
        if kind in _SAID_FIRST:
            return _note_said(kind, text), kind
    modules = [call for call in step.calls if call.kind == "module"]
    if modules:
        return "Imports " + ", ".join(_code(call.file) for call in modules), ""
    if len(step.calls) == 1 and step.calls[0].name.endswith(".__init__"):
        made = _short_name(step.calls[0].name)
        return f"Makes {_a(made)} {_code(made)}", ""
    if step.calls:
        return "Calls " + ", ".join(_code(_name_of(call)) for call in step.calls), ""
    for kind, text in step.notes:
        if kind in ("log", "warn"):
            return _note_said(kind, text), kind
    for name, what in step.holds:
        if what.startswith("event "):
            return f"Takes {_code(name)} from the event", ""
        if what.startswith("env "):
            return f"Takes {_code(name)} from the environment", ""
        return f"Sets {_code(name)} to {_esc(what)}", ""
    if step.notes:
        return _note_said(*step.notes[0]), step.notes[0][0]
    return f"Runs {_code(step.code)}", ""


def _says(stops: list[_Stop], i: int, first: dict[str, int], docs: dict[str, str], over: bool) -> str:
    """
    What the stop's line does, in a sentence or two (HTML), under its headline. over: it has a Skip call button.
    """
    stop = stops[i]
    step = stop.step
    if step.kind == "module":
        return "<p>Python runs this file from the top, once, the first time something imports it.</p>"
    if step.kind == "def":
        said = []
        if stop.caller is not None:
            when = f", only when {_code(' and '.join(step.when))}" if step.when else ""
            said.append(f"Called from {_code(stop.stack[-2][0])}, line {stops[stop.caller].step.line}{when}.")
        doc = docs.get(step.name, "")
        out = "".join(f"<p>{line}</p>" for line in said) + (f'<p class="wdoc">{_esc(doc)}</p>' if doc else "")
        if step.seen and step.name in first:
            out += (
                f'<p>Its steps are shown where it\'s first called: <label class="wjump" for="cw{first[step.name]}">'
                f"step {first[step.name] + 1}</label>.</p>"
            )
        elif not step.steps and not step.notes:
            out += "<p>There's nothing in it to follow.</p>"
        return out
    said = []
    headline_tag = next((kind for kind, _ in step.notes if kind in _DOTS), "")
    if headline_tag and step.kind == "do":  # what it reaches outside the code: 'An AWS call that reads.'
        tip = _NOTE_TIPS[headline_tag]
        said.append(_esc(tip[:1].upper() + tip[1:]) + ".")
    if step.kind == "return":
        entered = stops[stop.stack[-1][1]] if stop.stack else None
        if entered is not None and entered.caller is not None and len(stop.stack) > 1:
            said.append(
                f"{_code(stop.stack[-1][0])} ends here and hands this back to {_code(stop.stack[-2][0])}, "
                f"line {stops[entered.caller].step.line}."
            )
        else:
            said.append("The function ends here: this is what the call returns.")
    elif step.kind == "else":
        said.append(
            "Runs last, whether or not a line above it raised."
            if step.code.startswith("finally")
            else "Runs when the branch or loop above it doesn't."
        )
    elif step.kind in _KIND_SAYS:
        said.append(_KIND_SAYS[step.kind])
    own = [call for call in step.calls if call.kind == "def"]
    if own:
        it = "it" if len(own) == 1 else "each"
        said.append(
            f"Next goes into {it} to show its steps"
            + (
                "; Skip call runs it without going in."
                if over and len(own) == 1
                else "; Skip call runs them without going in."
                if over
                else "."
            )
        )
    return "".join(f"<p>{line}</p>" for line in said)


def _facts_html(step: CodeStep, said: str) -> str:
    """
    What else the line touches, beyond its headline, and what it knows of values, a row each:
    'env ORDERS_TABLE  an environment variable it reads', 'bucket  holds  event Records[].s3.bucket.name',
    'Bucket  comes from  event Records[].s3.bucket.name'.
    """
    rows = [
        f'<li>{_chips_html([note])}<span class="wfm">{_esc(_NOTE_TIPS.get(note[0], ""))}</span></li>'
        for note in step.notes
        if note[0] != said and note[0] != "more"
    ]
    rows += [f'<li><span class="wfm">{_esc(text)}</span></li>' for kind, text in step.notes if kind == "more"]
    rows += [f'<li>{_code(name)}<span class="wfv">holds</span>{_esc(what)}</li>' for name, what in step.holds]
    one_call = len({arg.rsplit(" ", 1)[0] for arg, _ in step.given}) == 1  # its headline says which: just 'Bucket'
    rows += [
        f'<li>{_code(arg.rsplit(" ", 1)[-1] if one_call else arg)}<span class="wfv">comes from</span>'
        f"{_esc(source)}</li>"
        for arg, source in step.given
    ]
    return f'<ul class="wfacts">{"".join(rows)}</ul>' if rows else ""


def _button(target: int | None, text: str, css: str = "", tip: str = "") -> str:
    """
    A button that goes to stop target: a label for its radio button, or greyed out when there's nowhere to go.
    """
    title = f' title="{_esc(tip)}"' if tip else ""
    css = f"wbt {css}".strip()
    if target is None:
        return f'<span class="{css} off"{title}>{text}</span>'
    return f'<label class="{css}" for="cw{target}"{title}>{text}</label>'


def _card_html(stops: list[_Stop], i: int, first: dict[str, int], docs: dict[str, str], editor: str = "") -> str:
    """
    The current stop's card: Back and Next (and Skip call and Finish, past what a line calls), what the line does in
    plain words, the calls it's inside (each a link back to its start), and what it touches.
    """
    stop, total = stops[i], len(stops)
    depth = len(stop.stack)
    over = _after(stops, i, depth) if stop.step.calls else None
    over = over if over != i + 1 else None
    out = _after(stops, i, depth - 1) if depth > 1 else None
    nav = [
        _button(i - 1 if i else None, "← Back"),
        _button(i + 1 if i + 1 < total else None, "Next →", "go"),
        f'<span class="wpos">Step <b>{i + 1}</b> of {total}</span><span class="wgap"></span>',
    ]
    if over is not None:
        nav.append(
            _button(over, "Skip call", tip="Run what this line calls without going in, and stop at the next line here")
        )
    if out is not None:
        name = stop.stack[-1][0]
        nav.append(
            _button(
                out,
                f"Finish <code>{_esc(name)}</code>",
                tip=f"Run the rest of {name} and go back to where it was called",
            )
        )
    headline, said = _headline(stop)
    trail = []
    for k, (name, at) in enumerate(stop.stack):
        css = ' class="here"' if k == depth - 1 else ""
        trail.append(f'<label for="cw{at}"{css}>{_esc(name)}</label>')
    where = '<span class="wsep">›</span>'.join(trail)
    href = open_at(editor, stop.step.file, stop.step.line) if stop.step.file else ""
    line = f"line {stop.step.line}" if stop.step.line else stop.step.file
    if href:
        line = (
            f'<a class="wed" href="{_esc(href)}" title="Open {_esc(stop.step.file)} at this line in '
            f'{_esc(editor_name(editor))}">{line} ↗</a>'
        )
    elif line:
        line = f'<span class="wln">{_esc(line)}</span>'
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
    return (
        f'<div class="wc"><div class="wnav">{"".join(nav)}</div>'
        f'<div class="whead">{headline}</div>'
        f'<div class="wstk"><span class="win">In</span>{where}{line}</div>'
        f'<div class="wsay">{_says(stops, i, first, docs, over is not None)}{_facts_html(stop.step, said)}</div>'
        + (f'<div class="wthen">{_esc(then)}</div>' if then else "")
        + "</div>"
    )


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
    return (
        f'<div class="wf wf{index}" style="--n:{len(rows)}"><div class="wfh">{name}<span>{_esc(frame.file)}'
        f'</span><span class="wfl">{where}</span></div><div class="wfw"><div class="wfp"><div class="wbar"></div>'
        f"{''.join(body)}</div></div></div>"
    )


def _item_html(stops: list[_Stop], i: int, card: str) -> str:
    """
    A step in the list: its radio button, then its number and what it does in a few words (or, for a function it goes
    into, the function's name and file, as a heading over its steps) as the button's label, then its card, which shows
    (beside the list) while the button is checked.
    """
    stop = stops[i]
    step = stop.step
    if step.kind in ("def", "module"):
        name = step.file if step.kind == "module" else _name_of(step)
        where = "runs when it's imported" if step.kind == "module" else step.file
        text = (
            f'<span class="wtx"><b>{_esc(name)}</b><span class="wof">'
            f"{_esc('again, shown before' if step.seen else where)}</span></span>"
        )
    else:
        headline, said = _headline(stop)
        dot = f'<span class="wdot d-{said}" title="{_esc(_NOTE_TIPS.get(said, ""))}"></span>' if said in _DOTS else ""
        text = f'<span class="wtx">{headline}</span>{dot}'
    checked = " checked" if i == 0 else ""
    return (
        f'<input type="radio" class="wr" name="{_GROUP}" id="cw{i}"{checked}><label class="wil k-{_esc(step.kind)}" '
        f'for="cw{i}" style="--d:{stop.depth}"><span class="wno">{i + 1}</span><span class="wx">{text}</span>'
        f"</label>{card}"
    )


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
        out.append(_item_html(stops, i, _card_html(stops, i, first, docs, block.editor)))
        at = rows_of[stop.frame].get(stop.lit)
        if at is not None:  # the line its code lights
            report.rules.add(f".{root} #cw{i}:checked~.wf{stop.frame}{{--k:{at}}}")
    while opened:
        out.append(drawn[opened.pop()] + "</div>")
    sub = (
        f'<div class="wsub">{_plural(len(stops), "step")}, in the order the code runs. Press Next or click a step to '
        "light its line in the code; after a click, <kbd>↑</kbd> <kbd>↓</kbd> move through them.</div>"
    )
    return (
        f'{title}{sub}<div class="walk"><div class="wl" role="radiogroup" aria-label="The steps">{"".join(out)}'
        '</div><div class="ws"></div></div>'
    )


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
