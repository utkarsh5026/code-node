"""
Draws the docs' plugin figures as SVG, a light and a dark file each, with the services' real logos (the ones in
src/code_node/report/logos/):

    docs/images/plugins-mix-{light,dark}.svg   examples/cart-service: what each plugin reads, and what they find together
    docs/images/reaches-{light,dark}.svg       the services, platforms and deploy files code-node knows

    python scripts/docs_figures.py

What the mix figure says comes from code-node's own run on examples/cart-service, so it stays true to the example:
it stops with an error when a finding it shows is no longer found.
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from code_node.analysis.findings import code_map_findings  # noqa: E402
from code_node.pages import PageOptions, map_entry  # noqa: E402
from code_node.project import entry_points, read_project  # noqa: E402
from code_node.report.brands import fills, logo_for  # noqa: E402
from code_node.report.graph import _g_sans  # noqa: E402

IMAGES = ROOT / "docs" / "images"
CART = ROOT / "examples" / "cart-service"

THEMES = {  # the docs site's own colours (docs/stylesheets/extra.css)
    "light": {
        "paper": "#ffffff",
        "fg": "#1b1d22",
        "dim": "#5f6470",
        "rule": "#e2e4e9",
        "panel": "#f6f7f9",
        "line": "#9097a3",
        "warn": "#d97706",
        "tile": "#ffffff",
    },
    "dark": {
        "paper": "#16181d",
        "fg": "#e4e6eb",
        "dim": "#9aa0ab",
        "rule": "#2b2e36",
        "panel": "#1d2026",
        "line": "#7d8494",
        "warn": "#d97706",
        "tile": "#ffffff",
    },
}

WIDE = 1100  # the mix figure's width

LOGO_INK = "#1b1d22"  # a logo's near-black parts: logos sit on a white tile in both themes, as they're drawn for one

SANS = "'IBM Plex Sans', -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'IBM Plex Mono', ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace"


def _svg(width: int, height: int, body: str, theme: dict[str, str], title: str) -> str:
    style = (
        f"text{{font-family:{SANS};fill:{theme['fg']}}}.dim{{fill:{theme['dim']}}}"
        f".mono{{font-family:{MONO}}}.cap{{font-size:11px;letter-spacing:.12em;fill:{theme['dim']}}}"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}" color="{theme["fg"]}">'
        f"<title>{escape(title)}</title><style>{style}</style>"
        f'<rect width="{width}" height="{height}" fill="{theme["paper"]}"/>{body}</svg>\n'
    )


def _logo(name: str, x: float, y: float, size: float) -> str:
    """
    A logo fitted into a size x size square at (x, y), kept to its own shape: the version drawn for that size.
    """
    found = logo_for(name, size)
    if found is None:
        raise SystemExit(f"no logo {name}: add it to src/code_node/report/brands.py and run scripts/logos.py")
    width, height, body = found
    return (
        f'<svg x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" viewBox="0 0 {width} {height}" '
        f'fill="currentColor" color="{LOGO_INK}">{body}</svg>'
    )


_clips = 0  # clip paths made, for unique ids


def _tile(name: str, x: float, y: float, size: float, theme: dict[str, str]) -> str:
    """
    A logo's tile: an AWS icon filling it with its corners rounded, else the logo on white, a little in from the edge.
    """
    global _clips
    radius = size * 0.24
    found = logo_for(name, size)
    if found is not None and fills(found):
        _clips += 1
        return (
            f'<clipPath id="cnf-{_clips}"><rect x="{x}" y="{y}" width="{size}" height="{size}" rx="{radius:.1f}"/>'
            f'</clipPath><g clip-path="url(#cnf-{_clips})">{_logo(name, x, y, size)}</g>'
        )
    pad = size * 0.14
    return (
        f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="{radius:.1f}" fill="{theme["tile"]}" '
        f'stroke="{theme["rule"]}"/>' + _logo(name, x + pad, y + pad, size - 2 * pad)
    )


def _card(x: float, y: float, w: float, h: float, theme: dict[str, str], stroke: str = "") -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{theme["paper"]}" '
        f'stroke="{stroke or theme["rule"]}" stroke-width="1.2"/>'
    )


def _curve(x1: float, y1: float, x2: float, y2: float, colour: str) -> str:
    middle = (x1 + x2) / 2
    return (
        f'<path d="M{x1:.1f},{y1:.1f} C{middle:.1f},{y1:.1f} {middle:.1f},{y2:.1f} {x2 - 6:.1f},{y2:.1f}" '
        f'fill="none" stroke="{colour}" stroke-width="1.4"/>'
        f'<path d="M{x2 - 7:.1f},{y2 - 4:.1f} L{x2:.1f},{y2:.1f} L{x2 - 7:.1f},{y2 + 4:.1f}" fill="none" '
        f'stroke="{colour}" stroke-width="1.4" stroke-linejoin="round"/>'
    )


# ---------------------------------------------------------------- what they find together

READS = [  # (logo, what it is, what it reads)
    ("aws-cloudformation", "template.yaml", "deploy file · AWS SAM"),
    ("aws-lambda", "AWS Lambda", "platform · one per entry point"),
]

LIBRARIES = [("postgresql", "PostgreSQL"), ("redis", "Redis"), ("openai-icon", "OpenAI"), ("aws", "boto3")]

FOUND = [  # (the plugins that find it together, what it says, words a finding of the example must have)
    (
        ("aws-cloudformation", "aws-dynamodb", "aws-sns"),
        "PutItem and Publish: its role doesn't allow them",
        "doesn't allow dynamodb:PutItem and sns:Publish",
    ),
    (
        ("aws-cloudformation", "aws-lambda"),
        "RECEIPTS_TABLE and TOPIC_ARN aren't set",
        "RECEIPTS_TABLE and TOPIC_ARN aren't set",
    ),
    (("postgresql",), "DELETE built from the request: SQL injection", "SQL injection"),
    (
        ("openai-icon", "aws-lambda", "aws-cloudformation"),
        "No timeout: Lambda stops it at 15 s",
        "Lambda stops it at its 15 s timeout",
    ),
    (("postgresql", "aws-lambda"), "A new connection on every call", "new PostgreSQL connection on every call"),
    (("postgresql",), "SELECT runs once per item in the cart", "PostgreSQL SELECT runs once per item"),
]


def _check_found() -> tuple[str, str]:
    """
    The example's entry point and where it is ('cart/app.py line 20'), after checking every finding the figure shows
    is still one code-node makes.
    """
    entry = entry_points(read_project(CART))[0]
    cmap, _ = map_entry(CART, entry, PageOptions())
    said = " ".join(message for _, message in code_map_findings(cmap))
    gone = [words for _, _, words in FOUND if words not in said]
    if gone:
        raise SystemExit(f"examples/cart-service no longer finds: {'; '.join(gone)}")
    return cmap.entry or "", f"{cmap.handler_file} line {cmap.entry_line}"


def plugins_mix(theme: dict[str, str]) -> str:
    entry, where = _check_found()
    parts = [
        '<text class="cap" x="24" y="30">READ WITH</text>',
        '<text class="cap" x="330" y="30">FROM</text>',
        '<text class="cap" x="588" y="30">WHAT THEY FIND TOGETHER</text>',
    ]
    left_w, ends = 262, []
    y = 48
    for name, title, sub in READS:
        parts.append(
            _card(24, y, left_w, 62, theme)
            + _tile(name, 38, y + 13, 36, theme)
            + f'<text x="88" y="{y + 28}" font-size="14" font-weight="600"'
            + (' class="mono"' if "." in title else "")
            + f">{escape(title)}</text>"
            + f'<text class="dim" x="88" y="{y + 46}" font-size="12">{escape(sub)}</text>'
        )
        ends.append(y + 31)
        y += 76
    parts.append(
        _card(24, y, left_w, 112, theme)
        + f'<text x="38" y="{y + 26}" font-size="14" font-weight="600">Libraries</text>'
        + f'<text class="dim" x="114" y="{y + 26}" font-size="12">every one it imports</text>'
    )
    for i, (name, label) in enumerate(LIBRARIES):
        x = 38 + i * 60
        parts.append(
            _tile(name, x, y + 40, 40, theme)
            + f'<text class="dim" x="{x + 20}" y="{y + 98}" font-size="11.5" text-anchor="middle">'
            f"{escape(label)}</text>"
        )
    ends.append(y + 56)
    bottom = y + 112

    box_x, box_w, box_h = 330, 206, 72
    box_y = (48 + bottom) / 2 - box_h / 2
    for end in ends:
        parts.append(_curve(24 + left_w, end, box_x, box_y + box_h / 2, theme["line"]))
    function = entry.rpartition(".")[2]
    parts.append(
        f'<rect x="{box_x}" y="{box_y}" width="{box_w}" height="{box_h}" rx="12" fill="{theme["panel"]}" '
        f'stroke="{theme["fg"]}" stroke-width="1.6"/>'
        f'<rect x="{box_x + 14}" y="{box_y + 20}" width="32" height="32" rx="9" fill="{theme["fg"]}"/>'
        f'<path d="M{box_x + 26},{box_y + 29}v14l11-7z" fill="{theme["paper"]}"/>'
        f'<text class="mono" x="{box_x + 58}" y="{box_y + 33}" font-size="13.5" font-weight="600">'
        f"{escape(function)}()</text>"
        f'<text class="dim" x="{box_x + 58}" y="{box_y + 52}" font-size="12">{escape(where)}</text>'
    )

    row_x, row_w, row_h, gap = 588, WIDE - 588 - 24, 46, 10
    top = 48
    for i, (logos, text, _) in enumerate(FOUND):
        y = top + i * (row_h + gap)
        parts.append(_curve(box_x + box_w, box_y + box_h / 2, row_x, y + row_h / 2, theme["line"]))
        parts.append(_card(row_x, y, row_w, row_h, theme))
        for k, name in enumerate(logos):
            parts.append(_tile(name, row_x + 9 + k * 34, y + 8, 30, theme))
        text_x = row_x + 9 + 3 * 34 + 8
        if _g_sans(text, 13) * 1.12 > row_x + row_w - 34 - text_x:  # the system fonts run wider than Arial
            raise SystemExit(f"too long for its row: {text}")
        parts.append(f'<text x="{text_x}" y="{y + 28}" font-size="13">{escape(text)}</text>')
        dot_x = row_x + row_w - 18
        parts.append(
            f'<circle cx="{dot_x}" cy="{y + row_h / 2}" r="7.5" fill="{theme["warn"]}"/>'
            f'<path d="M{dot_x},{y + row_h / 2 - 4}v4.4M{dot_x},{y + row_h / 2 + 3.4}v.3" '
            f'stroke="{theme["paper"]}" stroke-width="2" stroke-linecap="round"/>'
        )
    height = max(bottom, top + len(FOUND) * (row_h + gap)) + 18
    return _svg(
        WIDE,
        int(height),
        "".join(parts),
        theme,
        "What code-node's plugins find together in examples/cart-service: its SAM template, the Lambda "
        "platform and its libraries read one entry point, and together they find a role that doesn't allow "
        "two AWS calls, two unset variables, SQL injection, a client with no timeout, a connection on every "
        "call and a query run once per item.",
    )


# ---------------------------------------------------------------- what it knows

KNOWS = [  # (row, what reads it, [(logo, name)])
    (
        "AWS",
        "every boto3 service, with its IAM permission",
        [
            ("aws-s3", "S3"),
            ("aws-dynamodb", "DynamoDB"),
            ("aws-sns", "SNS"),
            ("aws-sqs", "SQS"),
            ("aws-lambda", "Lambda"),
            ("aws-eventbridge", "EventBridge"),
            ("aws-step-functions", "Step Functions"),
            ("aws-kinesis", "Kinesis"),
            ("aws-secrets-manager", "Secrets Manager"),
        ],
    ),
    (
        "Databases",
        "library plugins",
        [
            ("postgresql", "PostgreSQL"),
            ("mysql-icon", "MySQL"),
            ("sqlite", "SQLite"),
            ("mongodb-icon", "MongoDB"),
            ("redis", "Redis"),
        ],
    ),
    ("Models", "library plugin", [("openai-icon", "OpenAI"), ("anthropic-icon", "Anthropic")]),
    (
        "Runs on",
        "platforms",
        [
            ("aws-lambda", "AWS Lambda"),
            ("fastapi-icon", "FastAPI"),
            ("flask", "Flask"),
            ("django-icon", "Django"),
            ("python", "Plain Python"),
        ],
    ),
    ("Deployed with", "deploy files", [("aws-cloudformation", "AWS SAM"), ("serverless", "Serverless")]),
]


def _wrap(text: str, room: float) -> list[str]:
    words, lines = text.split(), [""]
    for word in words:
        trial = f"{lines[-1]} {word}".strip()
        if _g_sans(trial, 11.5) <= room or not lines[-1]:
            lines[-1] = trial
        else:
            lines.append(word)
    return lines[:2]


def reaches(theme: dict[str, str]) -> str:
    parts = []
    label_w, step, size = 196, 84, 46
    y = 20
    for i, (title, sub, logos) in enumerate(KNOWS):
        if i:
            parts.append(f'<line x1="24" x2="976" y1="{y - 12}" y2="{y - 12}" stroke="{theme["rule"]}"/>')
        parts.append(f'<text x="24" y="{y + 22}" font-size="14.5" font-weight="600">{escape(title)}</text>')
        for k, line in enumerate(_wrap(sub, label_w - 30)):
            parts.append(f'<text class="dim" x="24" y="{y + 42 + 15 * k}" font-size="12">{escape(line)}</text>')
        for k, (name, label) in enumerate(logos):
            x = 24 + label_w + k * step
            parts.append(_tile(name, x + (step - size) / 2 - 6, y, size, theme))
            for j, line in enumerate(_wrap(label, step - 8)):
                parts.append(
                    f'<text x="{x + step / 2 - 6}" y="{y + size + 17 + 14 * j}" font-size="11.5" '
                    f'text-anchor="middle">{escape(line)}</text>'
                )
        tall = any(len(_wrap(label, step - 8)) > 1 for _, label in logos) or len(_wrap(sub, label_w - 30)) > 1
        y += 108 if tall else 94
    height = y - 16
    return _svg(
        1000,
        height,
        "".join(parts),
        theme,
        "What code-node knows: AWS through boto3 (S3, DynamoDB, SNS, SQS, Lambda and every other service), "
        "PostgreSQL, MySQL, SQLite, MongoDB and Redis, OpenAI and Anthropic, AWS Lambda, FastAPI, Flask, "
        "Django and plain Python, and AWS SAM and Serverless deploy files.",
    )


FIGURES = {"plugins-mix": plugins_mix, "reaches": reaches}


def main() -> None:
    for name, draw in FIGURES.items():
        for theme in THEMES:
            out = IMAGES / f"{name}-{theme}.svg"
            out.write_text(draw(THEMES[theme]), "utf-8")
            print(f"{out.relative_to(ROOT)}  {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
