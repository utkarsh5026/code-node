"""
A web app as a platform: FastAPI, Flask and Django. Each route is an entry point, and what it's called with is the
request: a route function's parameters (FastAPI's path, query and body, a Flask or Django view's URL values, a Django
view's request) and Flask's request object are the input, so text built from them is followed into SQL and shell
commands. Code at import runs once per worker process, and a call that blocks in an async route holds up every other
request on its event loop.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict

from ..analysis.findings import _listed, _short_name, _where
from ..analysis.model import AwsCall, CodeMap, CodeSpot
from . import Platform

_PLACEHOLDER_RE = re.compile(r"\{(\w+)(?::[^}]*)?\}|<(?:[^:<>]+:)?(\w+)>|\(\?P<(\w+)>")  # {id}, <int:id>, (?P<id>...)

_MARKERS = {
    "Query": "query",
    "Path": "path",
    "Body": "body",
    "Header": "headers",
    "Cookie": "cookies",
    "Form": "form",
    "File": "files",
}  # FastAPI's: where a parameter comes from in the request

_NOT_INPUT = {
    "Depends",
    "Security",
    "BackgroundTasks",
    "Response",
    "SecurityScopes",
    "Session",
    "AsyncSession",
    "Connection",
    "AsyncConnection",
}  # FastAPI fills these itself, not from the request

_WHOLE = {"Request", "WebSocket", "HTTPConnection"}  # the request itself

_SCALARS = {
    "int",
    "str",
    "float",
    "bool",
    "bytes",
    "UUID",
    "date",
    "datetime",
    "time",
    "timedelta",
    "Decimal",
    "EmailStr",
    "HttpUrl",
    "AnyUrl",
    "Any",
    "Literal",
    "list",
    "List",
    "set",
    "Set",
    "tuple",
    "Tuple",
    "Sequence",
    "frozenset",
    "FrozenSet",
    "StrictStr",
    "StrictInt",
    "conint",
    "constr",
}  # a query parameter's

_WRAPPERS = {
    "Optional",
    "Union",
    "Annotated",
    "list",
    "List",
    "set",
    "Set",
    "tuple",
    "Tuple",
    "Sequence",
    "frozenset",
    "FrozenSet",
}  # look inside them for the type that says where it comes from

FRAMEWORK_LOGOS = {  # a module the code imports -> its framework's logo (report/logos/), the first one found
    "fastapi": "fastapi-icon",
    "flask": "flask",
    "quart": "flask",
    "rest_framework": "django-icon",
    "django": "django-icon",
}

_BLOCKING_HTTP = ("requests.", "urllib.request.", "urlopen(")  # HTTP that waits for the answer, as code starts


def _named(node: ast.expr | None) -> str:
    """
    The name a type or a call is written with: Query(...) -> 'Query', fastapi.Request -> 'Request'.
    """
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Constant) and isinstance(node.value, str):  # a forward reference: 'Order'
        return node.value.rsplit(".", 1)[-1].split("[")[0].strip()
    return ""


def _marker(node: ast.expr | None) -> ast.expr | None:
    """
    FastAPI's Query(), Body(), Depends()... when that's what node is.
    """
    return node if _named(node) in _MARKERS or _named(node) in _NOT_INPUT else None


def _core(node: ast.expr | None) -> tuple[str, ast.expr | None]:
    """
    A parameter's annotation as (its type, the FastAPI marker in it): Annotated[str, Query()] -> ('str', Query()),
    list[Item] | None -> ('Item', None), int -> ('int', None).
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):  # X | None
        left, right = _core(node.left), _core(node.right)
        return left if left[0] != "None" else right
    if isinstance(node, ast.Subscript) and _named(node.value) in _WRAPPERS:
        inner = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        if _named(node.value) == "Annotated":
            return _core(inner[0])[0], next((m for m in map(_marker, inner[1:]) if m is not None), None)
        found = [_core(e) for e in inner]
        return next((f for f in found if f[0] not in ("None", "")), ("", None))
    if isinstance(node, ast.Constant) and node.value is None:
        return "None", None
    return _named(node), None


def _fastapi(names: set[str], params: list[tuple[ast.arg, ast.expr | None]]) -> dict[str, tuple[str, ...]]:
    """
    FastAPI's rules: a parameter named in the path is from the path, one marked Query(), Body(), Header()... from
    there, a Request is the whole request, a plain type (int, str, list[str]) is a query parameter, and a model
    (Order) is the body.
    """
    found: dict[str, tuple[str, ...]] = {}
    bodies = []
    for param, default in params:
        name = param.arg
        kind, marked = _core(param.annotation)
        call = _marker(default) or marked
        marker = _named(call)
        if marker in _NOT_INPUT or kind in _NOT_INPUT:
            continue
        if kind in _WHOLE:
            found[name] = ()
        elif kind == "UploadFile" or marker == "File":
            found[name] = ("files", name)
        elif marker == "Body" or (not marker and name not in names and kind and kind not in _SCALARS):
            bodies.append(name)
        elif marker:
            alias = next(
                (
                    kw.value.value
                    for kw in getattr(call, "keywords", [])
                    if kw.arg == "alias" and isinstance(kw.value, ast.Constant)
                ),
                None,
            )
            found[name] = (_MARKERS[marker], str(alias or (name.replace("_", "-") if marker == "Header" else name)))
        else:
            found[name] = ("path" if name in names else "query", name)
    for name in bodies:  # one body model is the whole body; more are each a field of it
        found[name] = ("body",) if len(bodies) == 1 else ("body", name)
    return found


class WebPlatform(Platform):
    """
    A web app (FastAPI, Flask, Django): each route is an entry point, called with the request.
    """

    name = "web"
    title = "Web app"
    entry_kind = "a FastAPI, Flask or Django app: each route"
    input_name = "the request"
    input_word = "request"
    draws_input = True
    started = "When the server starts it (once in each worker process)"
    web_apps = ("FastAPI", "Flask", "APIRouter", "Blueprint", "Quart")
    input_objects = ("flask.request", "quart.request")
    input_aliases = {"get_json": "json", "get_data": "data"}

    def find_entries(self, module: str, tree: ast.Module) -> list[tuple[str, int, str]]:
        if module.rsplit(".", 1)[-1] != "urls":
            return []
        for node in tree.body:
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
                if isinstance(node, ast.AnnAssign)
                else []
            )
            if any(isinstance(t, ast.Name) and t.id == "urlpatterns" for t in targets):
                return [("urlpatterns", node.lineno, "Django's URLs: each view")]
        return []

    def route_inputs(
        self, function: ast.FunctionDef | ast.AsyncFunctionDef, path: str, imports: set[str], bound: bool = False
    ) -> dict[str, tuple[str, ...]]:
        a = function.args
        positional = a.posonlyargs + a.args
        defaults: list[ast.expr | None] = [None] * (len(positional) - len(a.defaults)) + list(a.defaults)
        params = list(zip(positional, defaults))[1 if bound else 0 :] + list(zip(a.kwonlyargs, a.kw_defaults))
        names = {name for match in _PLACEHOLDER_RE.finditer(path) for name in match.groups() if name}
        if "fastapi" in imports or ("{" in path and "(?P" not in path):
            return _fastapi(names, params)
        if imports & {"flask", "quart"}:  # a view is called with its URL's values only; the rest is flask.request
            return {p.arg: ("path", p.arg) for p, _ in params if p.arg in names}
        # Django: the request first, then the URL's values
        return {p.arg: () if i == 0 else ("path", p.arg) for i, (p, _) in enumerate(params)}

    def entry_icon(self, cmap: CodeMap) -> str:
        imported = {i.top for i in cmap.imports}
        return next((logo for module, logo in FRAMEWORK_LOGOS.items() if module in imported), "")

    def hang(self, cmap: CodeMap) -> str:
        return (
            "the request waits as long as the connection stays open, holding one of the server's workers, and "
            "the client gives up first."
        )

    def lost_error(self) -> str:
        return (
            "answers with a success status, so the client thinks it worked and the server's error log never shows it."
        )

    def findings(self, cmap: CodeMap) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        if cmap.note:
            return found
        for function, lines in self._blocking(cmap).items():
            name = _short_name(function)
            found.append(
                (
                    "warn",
                    (
                        f"{_listed([f'{what} at {_where(file, line)}' for what, file, line in lines], 2)} "
                        f"{'waits' if len(lines) == 1 else 'wait'} without await inside async def {name}(): while "
                        f"{'it waits' if len(lines) == 1 else 'they wait'}, the server's event loop can't run anything else, "
                        f"so every other request this worker is serving waits too. Make {name}() a plain def (FastAPI runs "
                        "those in a thread pool), or use an async client (httpx.AsyncClient, aioboto3, await asyncio.sleep)."
                    ),
                )
            )
        for spot in [s for s in cmap.spots if s.kind == "connect" and not s.ok and not s.startup]:
            found.append(
                (
                    "info",
                    (
                        f"It opens a new {spot.detail} connection on every request, at "
                        f"{_where(spot.file, spot.line, spot.function)}"
                        + (" inside a loop" if spot.loop else "")
                        + ": that's a round trip or more before any work, and many requests at once can use up the server's "
                        "connections. Make a pool once, at module level or when the app starts, and take a connection from it."
                    ),
                )
            )
        return found

    def marks(self, cmap: CodeMap) -> dict[str, list[str]]:
        return {
            function: [f"{what} blocks its event loop (line {line})" for what, _, line in lines]
            for function, lines in self._blocking(cmap).items()
        }

    @staticmethod
    def _blocking(cmap: CodeMap) -> dict[str, list[tuple[str, str, int]]]:
        """
        Calls that block inside an async def, by function: [('requests.get()', 'api.py', 9)]. HTTP through
        requests or urllib, time.sleep() and boto3, which all wait for their answer without giving the loop back.
        """
        async_functions = {f.name for f in cmap.functions if f.is_async}
        lines: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
        spots: list[CodeSpot | AwsCall] = [
            s
            for s in cmap.spots
            if (s.kind == "http" and s.code.startswith(_BLOCKING_HTTP))
            or (s.kind == "sleep" and s.code.startswith("time.sleep"))
        ]
        spots += [c for c in cmap.aws if not c.guessed]
        for spot in spots:
            if spot.function in async_functions and not spot.startup:
                what = spot.code.split("(", 1)[0] + "()" if isinstance(spot, CodeSpot) else spot.label
                lines[spot.function].append((what, spot.file, spot.line))
        return lines
