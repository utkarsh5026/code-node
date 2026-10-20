"""
Platforms: what a kind of entry point adds to reading plain Python. The reader, the findings and the graph are
generic; a platform says what its entry points look like, what they're called with, what its code can't do there,
and how to say so. AWS Lambda is one (aws_lambda.py). Pure, like analysis/: no I/O, no rendering.

Another package adds one by subclassing Platform and naming it under the `code_node.platforms` entry point group:

    [project.entry-points."code_node.platforms"]
    cloud_run = "my_package.cloud_run:CloudRun"

or, from a script, with register_platform(CloudRun()).
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from ..analysis.model import CodeMap, EventField

ENTRY_POINT_GROUP = "code_node.platforms"

_BUILT_IN = ("code_node.platforms.aws_lambda:LambdaPlatform",)


class Platform:
    """
    Plain Python, and the base a platform plugin overrides: an entry point is a function called with nothing the
    reader knows, code runs when Python imports it, and findings are worded for any code. A plugin sets `name` and
    overrides what's different where it runs.
    """

    name = ""  # what --platform takes and CodeMap.platform holds: 'lambda'; '' is plain Python
    title = "Python"  # 'AWS Lambda'
    entry_kind = ""  # how its entry points are listed: 'a Lambda handler (event, context)'
    inputs: tuple[str, ...] = ()  # what its entry function is called with: ('event', 'context'); the reader records
    # the fields the code reads from the one named 'event'
    input_name = "its input"  # 'the event'
    draws_input = False  # the graph draws the input box even when the code reads no field of it
    started = "When Python imports it"  # what runs at import is said to run: 'When Lambda starts it (...)'
    web_apps: tuple[str, ...] = ()  # app classes that make an entry point of a module-level object, like FastAPI

    def find_entries(self, module: str, tree: ast.Module) -> list[tuple[str, int, str]]:
        """
        Its entry points in one module, as (name in the module, line, why): [('lambda_handler', 12, 'a Lambda
        handler (event, context)')].
        """
        return []

    def input_kind(self, fields: Iterable[EventField]) -> str | None:
        """
        What sends the input, from the fields the code reads: 'an SQS batch'. None when it can't tell.
        """
        return None

    def python_version(self, cmap: CodeMap) -> tuple[int, int] | None:
        """
        The Python the code runs on, when it's known: (3, 12).
        """
        return None

    def unset_env(self, cmap: CodeMap) -> set[str]:
        """
        The environment variables the code needs that are known not to be set where it runs.
        """
        return set()

    def missing_entry(self, cmap: CodeMap, name: str, others: str) -> str:
        """
        The finding when the entry point isn't a function in its file.
        """
        return (f"No function {name}() in {cmap.handler_file}: there's nothing to start from. Name one of its "
                f"functions{others}.")

    def hang(self, cmap: CodeMap) -> str:
        """
        What an HTTP request without a timeout does when the server doesn't answer.
        """
        return "the call hangs for as long as the connection stays open."

    def lost_error(self) -> str:
        """
        What a run whose errors are dropped looks like.
        """
        return "looks like it worked, so whoever called it never learns it didn't."

    def import_error(self, module: str) -> str:
        """
        The error an import that can't be found raises: "ModuleNotFoundError: No module named 'x'".
        """
        return f"ModuleNotFoundError: No module named '{module}'"

    def install(self, pip: str, them: str) -> str:
        """
        How to add libraries the code imports: 'install it (pip install x) and list it in the project's
        dependencies'.
        """
        return f"install {them} (pip install {pip}) and list {them} in the project's dependencies"

    def entry_findings(self, cmap: CodeMap) -> list[tuple[str, str]]:
        """
        Findings about the entry point itself, as (level, message): the graph marks its box with them.
        """
        return []

    def findings(self, cmap: CodeMap) -> list[tuple[str, str]]:
        """
        Findings only this platform has, as (level, message): after the ones for any code.
        """
        return []

    def denied(self, cmap: CodeMap) -> dict[str, str]:
        """
        The permissions its AWS calls need that where it runs is known not to allow, each with why, in a few words:
        {'sns:Publish': 'not in its Policies in template.yaml'}. The graph marks those calls.
        """
        return {}

    def marks(self, cmap: CodeMap) -> dict[str, list[str]]:
        """
        Why a function's box in the graph is amber, for this platform's findings: {'etl.save': ['writes data.csv
        outside /tmp (line 9)']}.
        """
        return {}


PYTHON = Platform()

_platforms: dict[str, Platform] = {}

_loaded = False


def register_platform(platform: Platform) -> None:
    """
    Adds a platform (or replaces the one with its name): --platform takes its name, and its entry points are found.
    """
    if not platform.name:
        raise ValueError("a platform needs a name")
    _platforms[platform.name] = platform


def _add(found: Platform | type[Platform]) -> None:
    platform = found() if isinstance(found, type) else found
    if platform.name:
        _platforms.setdefault(platform.name, platform)  # one registered by hand first wins


def platforms() -> list[Platform]:
    """
    Every platform: the built-in ones, then those installed packages add, loaded the first time it's asked.
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
    return list(_platforms.values())


def get_platform(name: str | None) -> Platform:
    """
    The platform with that name; plain Python for '' or a name no platform has.
    """
    if not name:
        return PYTHON
    return next((p for p in platforms() if p.name == name), PYTHON)


__all__ = ["ENTRY_POINT_GROUP", "PYTHON", "Platform", "get_platform", "platforms", "register_platform"]
