"""
What the code map finds wrong, and the one-paragraph summary of what the code does
and returns.
"""

from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict

from ..kit.fmt import _plural
from ..kit.text import _clip

from .terms import LATEST_RUNTIMES
from .terms import _BATCHES, _REMOVED_MODULES
from .syntax import _a, _const, _parse
from .aws_model import _service_name
from .model import AwsCall, CodeMap, CodeSpot
from .mapping import _python_version
from ..platforms import get_platform


_PIP_NAMES = {"yaml": "pyyaml", "PIL": "pillow", "sklearn": "scikit-learn", "cv2": "opencv-python-headless",
              "dateutil": "python-dateutil", "jwt": "PyJWT", "dotenv": "python-dotenv", "bs4": "beautifulsoup4",
              "psycopg2": "psycopg2-binary", "Crypto": "pycryptodome", "jose": "python-jose", "magic": "python-magic"}

_REPLACEMENTS = {"distutils": "setuptools, or shutil and sysconfig", "imp": "importlib", "asyncore": "asyncio",
                 "asynchat": "asyncio", "smtpd": "aiosmtpd", "cgi": "email.message and urllib.parse",
                 "pipes": "shlex.quote", "crypt": "hashlib", "telnetlib": "telnetlib3", "imghdr": "Pillow or filetype",
                 "uu": "base64", "xdrlib": "struct"}


def _short_name(key: str) -> str:
    """
    One of its functions as people say it: 'app.main.handler' -> 'handler', 'app.store.Orders.save' ->
    'Orders.save', 'app.store.Orders.__init__' -> 'Orders' (what you call to run it).
    """
    parts = key.split(".")
    if len(parts) >= 2 and parts[-2][:1].isupper():
        return parts[-2] if parts[-1] == "__init__" else f"{parts[-2]}.{parts[-1]}"
    return parts[-1]


def _where(file: str, line: int, function: str = "") -> str:
    """
    'etl.py line 17', or 'etl.py line 17 in handler()'.
    """
    return f"{file} line {line}" + (f" in {_short_name(function)}()" if function else "")


def _listed(items: list[str], most: int = 3) -> str:
    """
    'a', 'a and b', 'a, b and c', 'a, b, c and 2 more'.
    """
    if len(items) > most:
        return ", ".join(items[:most]) + f" and {len(items) - most} more"
    return " and ".join([", ".join(items[:-1]), items[-1]]) if len(items) > 1 else (items[0] if items else "")


def code_map_findings(cmap: CodeMap) -> list[tuple[str, str]]:
    """
    What's worth fixing in the code, from its CodeMap: an entry point that isn't there, imports that can't be found
    or that newer Pythons removed, HTTP requests without a timeout, list calls that read only their first page,
    errors it drops, secrets written in the code, and AWS calls in a loop that a batch call would do in fewer
    requests. Then what its platform adds (a Lambda handler's own checks), worded for where it runs.
    """
    found: list[tuple[str, str]] = []
    if cmap.note:
        return found
    platform = get_platform(cmap.platform)
    version = platform.python_version(cmap)
    entry_name = (cmap.handler or "").rsplit(".", 1)[-1]
    spots: dict[str, list[CodeSpot]] = defaultdict(list)
    for spot in cmap.spots:
        spots[spot.kind].append(spot)

    for spot in spots["syntax"]:
        mine = sys.version_info[:2]
        if version and version > mine:
            found.append(("info", (
                f"{spot.file} doesn't parse with this Python {mine[0]}.{mine[1]} ({spot.detail}): it may use syntax "
                f"only Python {version[0]}.{version[1]} knows, so code-node couldn't follow it. Run code-node with "
                f"Python {version[0]}.{version[1]} to read it."
            )))
        else:
            found.append(("warn", (
                f"{spot.file} doesn't parse ({spot.detail}): Python can't load it either, so code that imports it fails "
                "with SyntaxError, and the map stops there. Fix that line."
            )))
    if cmap.entry is None and cmap.handler_file and not any(s.file == cmap.handler_file for s in spots["syntax"]):
        others = f" ({_listed(cmap.handlers)} look like entry points)" if cmap.handlers else ""
        found.append(("warn", platform.missing_entry(cmap, entry_name, others)))
    found += platform.entry_findings(cmap)

    gone = [i for i in cmap.imports if i.source == "missing" and not i.optional]
    if gone:
        tops = list(dict.fromkeys(i.top for i in gone))
        startup = any(i.startup for i in gone)
        pip = " ".join(_PIP_NAMES.get(top, top) for top in tops[:5])
        install = platform.install(pip, "it" if len(tops) == 1 else "them")
        found.append(("warn", (
            f"It imports {_listed(tops)}, which {'isn' if len(tops) == 1 else 'aren'}'t in the code, Python's "
            f"standard library or the Python environment ({gone[0].file} line {gone[0].line}): "
            + ("every call fails" if startup else "calls that reach that line fail")
            + f" with {platform.import_error(tops[0])}. {install[0].upper()}{install[1:]}."
        )))
    for i in [i for i in cmap.imports if i.source == "removed"]:
        removed = _REMOVED_MODULES[i.top]
        found.append(("warn", (
            f"It imports {i.top} ({i.file} line {i.line}), which Python {removed[0]}.{removed[1]} removed: on the "
            f"Python it runs on that fails with {platform.import_error(i.top)}. Use "
            f"{_REPLACEMENTS.get(i.top, 'a replacement')} instead."
        )))
    family_latest = LATEST_RUNTIMES["python"]
    latest = _python_version(family_latest)
    later = [i for i in cmap.imports if i.source == "stdlib" and i.top in _REMOVED_MODULES and latest
             and _REMOVED_MODULES[i.top] <= latest]
    if later:
        tops = list(dict.fromkeys(i.top for i in later))
        removed = _REMOVED_MODULES[tops[0]]
        swaps = _listed([f"{top} by {_REPLACEMENTS.get(top, 'a replacement')}" for top in tops], 2)
        found.append(("info", (
            f"It imports {_listed(tops)}, which Python {removed[0]}.{removed[1]} removed: on Python "
            f"{removed[0]}.{removed[1]} or later it fails with {platform.import_error(tops[0])} until "
            f"{'that is' if len(tops) == 1 else 'they are'} replaced ({swaps})."
        )))

    slow = [s for s in spots["http"] if not s.ok]
    if slow:
        found.append(("warn", (
            f"{_plural(len(slow), 'HTTP request')} {'has' if len(slow) == 1 else 'have'} no timeout "
            f"({_listed([f'{s.detail} at {_where(s.file, s.line)}' for s in slow], 2)}): if the server doesn't "
            f"answer, {platform.hang(cmap)} Pass timeout=10 (or what the call needs)."
        )))
    for call in cmap.aws:
        if call.pages == "one" and call.operation.startswith(("List", "Scan", "Query")) and not call.guessed:
            first = {"ListObjectsV2": "1,000 keys", "ListObjects": "1,000 keys", "Scan": "1 MB", "Query": "1 MB"}.get(
                call.operation, "the first page")
            fix = ("loop while the answer has LastEvaluatedKey, passing it back as ExclusiveStartKey"
                   if call.service == "dynamodb" else
                   f"use get_paginator('{_snake(call.operation)}').paginate(...) on its client")
            found.append(("warn", (
                f"{call.label} at {_where(call.file, call.line)} reads only its first page: past {first} the rest is "
                f"left out without an error. To read every page, {fix}."
            )))
    for spot in spots["swallow"]:
        found.append(("warn", (
            f"Errors are dropped at {_where(spot.file, spot.line, spot.function)} ({spot.code}): a run that failed "
            f"{platform.lost_error()} Log it (logger.exception(...)) and raise it again, or report the failed item."
        )))
    secrets = spots["secret"]
    if secrets:
        where = _listed([f"{s.detail} at {s.file} line {s.line}" for s in secrets], 2)
        found.append(("warn", (
            f"Secret-looking values are written in the code ({where}; "
            "the values aren't shown here): anyone who can read the code can read them. "
            "Keep them in Secrets Manager or Parameter Store, and read them when the code starts."
        )))

    batched = [c for c in cmap.aws if c.loop and (c.service, c.operation) in _BATCHES and not c.guessed]
    for call in list({(c.service, c.operation): c for c in batched}.values()):
        alternative, size = _BATCHES[(call.service, call.operation)]
        found.append(("info", (
            f"{call.label} runs once per item in {call.loop.rstrip(':')} ({_where(call.file, call.line)}): a request "
            f"for each. {alternative} sends up to {size:,} at a time, so a run takes fewer round trips."
        )))
    return found + platform.findings(cmap)


def _snake(operation: str) -> str:
    """
    'ListObjectsV2' -> 'list_objects_v2', boto3's method name.
    """
    try:
        from botocore import xform_name
    except ImportError:
        return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", operation).lower()
    return xform_name(operation)


def _code_summary(cmap: CodeMap) -> list[str]:
    """
    How the code works in a few sentences: what it does when it's imported (when Lambda starts it, for a handler),
    then what each call reads from its input, which AWS services it reaches and how, its own functions it calls, and
    what it returns.
    """
    platform = get_platform(cmap.platform)
    out = []
    file = cmap.handler_file or ""
    early = []
    names = list(dict.fromkeys(_service_name(s.detail) for s in cmap.spots
                               if s.kind == "client" and s.startup and s.detail != "?"))
    if names:
        early.append(f"makes {_a(names[0])} {names[0]} client" if len(names) == 1 else f"makes {_listed(names)} clients")
    env = list(dict.fromkeys(e.name for e in cmap.env if e.startup))
    if env:
        early.append(f"reads {_listed(env)} from its environment")
    early += _aws_phrase([c for c in cmap.aws if c.startup])
    if early:
        out.append(f"{platform.started}, the code {_listed(early, 4)}.")
    if cmap.entry is None:
        return out
    entry = cmap.entry.rsplit(".", 1)[-1]
    out.append(f"Each call runs {entry}() in {file}.")
    labels = [f.label for f in cmap.event]
    leaves = [label for label in labels if not any(
        other.startswith((label + "[", label + ".", label + " (")) for other in labels)]
    if leaves:
        kind = platform.input_kind(cmap.event)
        out.append(f"It reads {_listed(leaves, 4)} from {platform.input_name}"
                   + (f", which looks like {kind}" if kind else "") + ".")
    phrase = _aws_phrase([c for c in cmap.aws if not c.startup])
    http = [s for s in cmap.spots if s.kind == "http" and not s.startup]
    more = list(phrase)
    if http:
        more.append(f"sends {_plural(len(http), 'HTTP request')}")
    commands = [path for method, path, _ in cmap.routes if method == "CLI" and not path.startswith("(")]
    web = [f"{method} {path}" for method, path, _ in cmap.routes if method != "CLI"]
    if commands:
        more.append(f"has {_plural(len(commands), 'command')} ({_listed(commands)})")
    if web:
        more.append(f"answers {_plural(len(web), 'web route')} ({_listed(web)})")
    if more:
        out.append(f"It {_listed(more, 6) if len(more) < 3 else '; '.join(more[:-1]) + '; and ' + more[-1]}.")
    called = [f for f in cmap.functions if f.depth == 1]
    returns = list(dict.fromkeys(code for code, _, _ in cmap.returns))
    last = []
    if called:
        last.append("calls " + _listed([f"{_short_name(f.name)}()" + (
            f" from {f.file}" if f.file != file else "") for f in called], 4))
    if returns:
        last.append(f"returns {_returned(returns[0])}" + (f" (or {_plural(len(returns) - 1, 'other value')})"
                                                          if len(returns) > 1 else ""))
    if last:
        out.append(f"It {' and '.join(last)}.")
    if not (leaves or more or last):
        out.append(f"It does nothing this can follow: no AWS calls, own functions, HTTP requests or fields of "
                   f"{platform.input_name}.")
    return out


def _returned(code: str) -> str:
    """
    What a return statement gives back, said shortly: "{'statusCode': 200, 'body': ...}" -> 'a dict with
    statusCode and body'; short code as it is.
    """
    try:
        node = _parse(code, mode="eval").body
    except SyntaxError:
        return _clip(code, 60)
    if isinstance(node, ast.Dict) and node.keys and all(isinstance(_const(k), str) for k in node.keys):
        keys = [str(_const(k)) for k in node.keys]
        return f"a dict with {_listed(keys, 4)}" if len(code) > 50 else code
    return _clip(code, 60)


def _aws_phrase(calls: list[AwsCall]) -> list[str]:
    """
    ['reads from S3 (GetObject) and SQS (ListQueues)', 'writes to DynamoDB (PutItem)'].
    """
    grouped: dict[str, dict[str, list[AwsCall]]] = {}
    for call in calls:
        grouped.setdefault(call.access, {}).setdefault(call.service, []).append(call)
    verbs = {"reads": "reads from", "writes": "writes to", "sends": "sends to", "runs": "calls",
             "signs": "signs links for"}
    parts = []
    for access, services in grouped.items():
        each = []
        for service, group in services.items():
            ops = list(dict.fromkeys(c.operation for c in group))
            each.append(f"{_service_name(service)} ({', '.join(ops[:3])}{', …' if len(ops) > 3 else ''})")
        parts.append(f"{verbs[access]} {_listed(each, 4)}")
    return parts
