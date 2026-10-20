"""
Libraries: what the code reaches through a library that isn't boto3. A library plugin knows a library's clients
(a Redis client, a database connection and its cursors, an OpenAI client) and what each of their calls does (reads
a key, writes a table, runs a model). The reader keeps track of the clients the code makes as it does boto3's, asks
the plugin about each call made through one, and the graph draws a box for each service they reach. Pure, like
analysis/: no I/O, no rendering.

Unlike a platform (one per map), libraries stack: each is asked about the modules it names, so code that imports
redis, psycopg2 and openai is read with all three, and the platform's checks apply to what each finds (on Lambda,
a connection made on every call; a client that waits longer than the function's timeout).

Another package adds one by subclassing Library and naming it under the `code_node.libraries` entry point group:

    [project.entry-points."code_node.libraries"]
    kafka = "my_package.kafka:Kafka"

or, from a script, with register_library(Kafka()).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Callable

from ..analysis.syntax import _a, _const, _unparse

if TYPE_CHECKING:
    from ..analysis.model import CodeMap, LibraryCall

ENTRY_POINT_GROUP = "code_node.libraries"

_BUILT_IN = (
    "code_node.libraries.redis:RedisLibrary",
    "code_node.libraries.sql:SqlLibrary",
    "code_node.libraries.mongo:MongoLibrary",
    "code_node.libraries.llm:LlmLibrary",
)

ACCESS = ("reads", "writes", "sends", "runs")  # what a call does to what it reaches, as for AWS calls

ICONS = ("database", "queue", "key", "send", "spark", "bucket", "flow", "cloud")  # what a service's box can show


@dataclass(frozen=True)
class Handle:
    """
    Something a library gives the code that the reader keeps track of, as a name holds it: a Redis client, a
    database cursor, a MongoDB collection. kind is the library's own word for it; facts are what the plugin wants
    to remember about it, as (name, value) pairs: (('database', 'shop'), ('collection', 'orders')).
    """

    kind: str  # 'client', 'connection', 'cursor', 'collection'
    service: str = ""  # what it reaches, as people name it: 'Redis', 'PostgreSQL'
    facts: tuple[tuple[str, str], ...] = ()
    opens: bool = False  # making it opens a client or a connection: better made once, at module level
    waits: str = ""  # how long a call through it waits when the service doesn't answer, when that's too long
    # ('as long as Redis takes'); '' when it's given a timeout
    fix: str = ""  # ...and how to give it one: 'redis.Redis(..., socket_timeout=5)'

    def fact(self, name: str, default: str = "") -> str:
        return next((value for key, value in self.facts if key == name), default)

    def but(self, kind: str | None = None, **facts: str) -> Handle:
        """
        A handle made from this one: another kind, with more facts (or new values for some). It doesn't open
        anything itself.
        """
        kept = tuple((key, value) for key, value in self.facts if key not in facts)
        return replace(self, kind=kind or self.kind, facts=kept + tuple(facts.items()), opens=False)


@dataclass
class Use:
    """
    What a call through a library does, for the map: its operation, how it touches the service, and what on.
    """

    operation: str  # 'GET', 'INSERT', 'chat.completions.create'
    access: str = "reads"  # one of ACCESS
    target: str = ""  # a key, a table, a collection, a model: 'cart:{user}', 'orders'
    service: str = ""  # the box it's drawn in ('' for the handle's service, else the library's title)
    icon: str = ""  # '' for the library's
    flag: str = ""  # a warning about this call, in a few words, said on its box and its step: 'built from the event'
    why: str = ""  # ...and for the findings, the rest of a sentence that starts with the call and where it is ('Redis
    # KEYS at app.py line 9'): 'walks every key in the database, ... Use scan_iter(match=...) instead.'
    batch: str = ""  # when it's made in a loop, the call that does many at once: 'executemany()'
    gives: Handle | None = None  # what the call returns, when that's worth keeping track of (a cursor)


@dataclass
class _Argument:
    """
    What the reader knows about one argument of a call.
    """

    handle: Handle | None = None  # a handle it holds
    text: str = ""  # the text it's built from, as code: the f-string a name holds, not the name
    inputs: tuple[str, ...] = ()  # what goes into it from the entry point's input: ('event body.id',)
    built: bool = False  # text put together while the code runs (an f-string, +, % or .format()), not a literal


@dataclass
class Call:
    """
    A call a library plugin is asked about, as the reader sees it: its arguments as written, the literals among
    them, what each one holds, and where the call is.
    """

    name: str  # the function's full name ('redis.Redis', 'sqlite3.connect'), or the method's ('get')
    node: ast.Call
    loop: str = ""  # the loop it's in: 'for item in items:'
    startup: bool = False  # made when the code is imported
    once: bool = False  # made once and kept: at import, in a cached function, or kept in a global
    look: Callable[[ast.expr], _Argument] = field(default=lambda node: _Argument(), repr=False)

    def argument(self, index: int | None = None, keyword: str = "") -> ast.expr | None:
        """
        An argument as written: the index-th positional one, else the keyword one.
        """
        if index is not None and index < len(self.node.args) and not isinstance(self.node.args[index], ast.Starred):
            return self.node.args[index]
        return next((kw.value for kw in self.node.keywords if keyword and kw.arg == keyword), None)

    def given(self, *keywords: str) -> bool:
        """
        Whether any of these keyword arguments is passed (or **kwargs, which could hold it).
        """
        return any(kw.arg in keywords or kw.arg is None for kw in self.node.keywords)

    def value(self, index: int | None = None, keyword: str = "") -> Any:
        """
        A literal argument's value: 'orders', 5. None when it isn't a literal.
        """
        node = self.argument(index, keyword)
        return _const(node) if node is not None else None

    def code(self, index: int | None = None, keyword: str = "", most: int = 60) -> str:
        """
        An argument as written: "f'cart:{user}'". '' when it isn't passed.
        """
        node = self.argument(index, keyword)
        return _unparse(node, most) if node is not None else ""

    def shown(self, index: int | None = None, keyword: str = "", most: int = 40) -> str:
        """
        An argument as a box lists it: a literal string as it is ('orders'), an f-string with what goes in it
        ('cart:{user}'), else the code ('key').
        """
        node = self.argument(index, keyword)
        if node is None:
            return ""
        if isinstance(_const(node), str):
            return _short(str(_const(node)), most)
        if isinstance(node, ast.JoinedStr):
            parts = [
                str(_const(v)) if isinstance(_const(v), str) else "{" + _unparse(v.value, 20) + "}"
                for v in node.values
                if isinstance(v, (ast.Constant, ast.FormattedValue))
            ]
            return _short("".join(parts), most)
        return _short(_unparse(node, most), most)

    def held(self, index: int | None = None, keyword: str = "") -> Handle | None:
        """
        The handle an argument holds: the connection passed to a function, the text() SQLAlchemy made.
        """
        node = self.argument(index, keyword)
        return self.look(node).handle if node is not None else None

    def text(self, index: int | None = None, keyword: str = "") -> str:
        """
        The text an argument is, as code: the literal or f-string passed, or the one a name passed holds
        ('sql' -> "f'SELECT * FROM orders WHERE id = {order_id}'"). '' when it can't tell.
        """
        node = self.argument(index, keyword)
        if node is None:
            return ""
        found = self.look(node)
        if found.text:
            return found.text
        if isinstance(_const(node), str) or isinstance(node, (ast.JoinedStr, ast.BinOp)):
            return _unparse(node, 400)
        return ""

    def built(self, index: int | None = None, keyword: str = "") -> bool:
        """
        Whether an argument is text put together as the code runs (an f-string, +, % or .format(), where it's
        passed or in the name passed), rather than a literal.
        """
        node = self.argument(index, keyword)
        return node is not None and self.look(node).built

    def inputs(self, index: int | None = None, keyword: str = "") -> list[str]:
        """
        What from the entry point's input goes into an argument, however many names it went through on the way:
        ['event body.id']. That's what whoever calls the code controls.
        """
        node = self.argument(index, keyword)
        return list(self.look(node).inputs) if node is not None else []


def _short(text: str, most: int) -> str:
    return text if len(text) <= most else text[: most - 1] + "…"


class Library:
    """
    A library the reader can follow calls through. A plugin sets `name`, `title` and `modules` (the top-level
    modules it's for), and overrides the hooks below: make() for what the module's functions and classes give the
    code, attribute(), item() and call() for what's done with those, describe() for how a name holding one is said,
    and findings() for what's worth fixing in its calls. Each hook returns None for what it doesn't know, which the
    reader then leaves alone.
    """

    name = ""  # 'redis'
    title = ""  # 'Redis': how people call it, said where the page lists the plugins it used
    modules: tuple[str, ...] = ()  # the top-level modules it's for: ('redis',). Code that imports none of them never
    # reaches it
    icon = "cloud"  # its boxes' icon, one of ICONS

    def make(self, name: str, call: Call) -> Handle | Use | None:
        """
        A call to a function or class of its modules, by its full name ('redis.Redis', 'redis.from_url',
        'sqlite3.connect'): the Handle it gives the code, or what it does (a Use).
        """
        return None

    def attribute(self, handle: Handle, name: str) -> Handle | None:
        """
        An attribute read from a handle that is itself something to keep track of: mongo_client.shop (a database),
        openai_client.chat (part of the client). None for a method: calling it asks call().
        """
        return None

    def item(self, handle: Handle, key: Any) -> Handle | None:
        """
        handle[key]: mongo_client['shop']. key is the literal, or None when it isn't one.
        """
        return None

    def call(self, handle: Handle, method: str, call: Call) -> Handle | Use | None:
        """
        A method called on a handle: what it does (a Use, which can give another handle), or the handle it gives
        (a cursor from a connection).
        """
        return None

    def describe(self, handle: Handle) -> str:
        """
        What a name holding the handle holds, in a few words: 'a Redis client', 'a PostgreSQL cursor'.
        """
        service = handle.service or self.title
        return f"{_a(service)} {service} {handle.kind}"

    def findings(self, cmap: CodeMap, calls: list[LibraryCall]) -> list[tuple[str, str]]:
        """
        Its own findings, as (level, message), from its calls in the map. The general ones (flagged calls, calls in
        a loop that a batch call would do, clients that wait too long or connect on every call) are made for every
        library.
        """
        return []


_libraries: dict[str, Library] = {}

_loaded = False


def register_library(library: Library) -> None:
    """
    Adds a library plugin (or replaces the one with its name): from then on, calls through its modules are followed.
    """
    if not library.name or not library.modules:
        raise ValueError("a library plugin needs a name and the modules it's for")
    libraries()
    _libraries[library.name] = library


def _add(found: Library | type[Library]) -> None:
    library = found() if isinstance(found, type) else found
    if library.name and library.modules:
        _libraries.setdefault(library.name, library)  # one registered by hand first wins


def libraries() -> list[Library]:
    """
    Every library plugin: the built-in ones, then those installed packages add, loaded the first time it's asked.
    """
    global _loaded
    if not _loaded:
        _loaded = True
        from importlib import import_module
        from importlib.metadata import entry_points

        for target in _BUILT_IN:
            module, _, attr = target.partition(":")
            _add(getattr(import_module(module), attr))
        for point in entry_points(group=ENTRY_POINT_GROUP):
            try:
                _add(point.load())
            except Exception:  # noqa: BLE001  a broken plugin leaves the others working
                continue
    return list(_libraries.values())


def library_for(module: str) -> Library | None:
    """
    The library plugin for a top-level module ('redis'), or None.
    """
    return next((library for library in reversed(libraries()) if module in library.modules), None)


def get_library(name: str) -> Library | None:
    """
    The library plugin with that name, or None.
    """
    return next((library for library in libraries() if library.name == name), None)


__all__ = [
    "ACCESS",
    "ENTRY_POINT_GROUP",
    "ICONS",
    "Call",
    "Handle",
    "Library",
    "Use",
    "get_library",
    "libraries",
    "library_for",
    "register_library",
]
