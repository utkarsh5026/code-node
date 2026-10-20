"""
AWS Lambda as a platform: handlers are entry points, the handler is called with (event, context), code at import
runs once per cold start, the disk is read-only outside /tmp, and the run is billed while it waits. Its findings
check what a handler needs that plain Python doesn't.
"""

from __future__ import annotations

import ast
import posixpath
from collections import defaultdict
from typing import Iterable

from ..analysis.aws_model import _event_kind, _service_name
from ..analysis.findings import _listed, _where
from ..analysis.mapping import _python_version
from ..analysis.model import CodeMap, CodeSpot, EnvRead, EventField
from ..deploys import allowed, get_deploy
from ..kit.fmt import _plural
from . import Platform

_HANDLERS = ("lambda_handler", "handler")

_WRITABLE = ("/tmp", "/mnt/")  # Lambda's disk is read-only but for /tmp (and a file system mounted under /mnt)

_LAMBDA_ENV = frozenset(
    {  # environment variables Lambda sets itself: reading one needs no setting
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "AWS_EXECUTION_ENV",
        "AWS_LAMBDA_FUNCTION_NAME",
        "AWS_LAMBDA_FUNCTION_MEMORY_SIZE",
        "AWS_LAMBDA_FUNCTION_VERSION",
        "AWS_LAMBDA_INITIALIZATION_TYPE",
        "AWS_LAMBDA_LOG_GROUP_NAME",
        "AWS_LAMBDA_LOG_STREAM_NAME",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_LAMBDA_RUNTIME_API",
        "LAMBDA_TASK_ROOT",
        "LAMBDA_RUNTIME_DIR",
        "_HANDLER",
        "_X_AMZN_TRACE_ID",
        "TZ",
        "LANG",
        "PATH",
        "LD_LIBRARY_PATH",
        "PYTHONPATH",
        "AWS_XRAY_CONTEXT_MISSING",
        "AWS_XRAY_DAEMON_ADDRESS",
        "AWS_LAMBDA_LOG_FORMAT",
        "AWS_LAMBDA_LOG_LEVEL",
        "AWS_LAMBDA_MAX_CONCURRENCY",
        "HOME",
        "PWD",
        "_AWS_XRAY_DAEMON_ADDRESS",
        "_AWS_XRAY_DAEMON_PORT",
        "AWS_LAMBDA_EXEC_WRAPPER",
    }
)


class LambdaPlatform(Platform):
    """
    An AWS Lambda handler: def handler(event, context) in its deployment package.
    """

    name = "lambda"
    title = "AWS Lambda"
    entry_kind = "a Lambda handler (event, context)"
    inputs = ("event", "context")
    input_name = "the event"
    input_word = "event"
    draws_input = True
    started = "When Lambda starts it (once per cold start)"
    web_apps = (
        "Chalice",
        "APIGatewayRestResolver",
        "APIGatewayHttpResolver",
        "ALBResolver",
        "LambdaFunctionUrlResolver",
    )

    def find_entries(self, module: str, tree: ast.Module) -> list[tuple[str, int, str]]:
        found = []
        for node in tree.body:
            is_handler = (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in _HANDLERS
                and len(node.args.posonlyargs + node.args.args) == 2
            )
            if is_handler:
                found.append((node.name, node.lineno, self.entry_kind))
        return sorted(found, key=lambda entry: _HANDLERS.index(entry[0]))

    def input_kind(self, fields: Iterable[EventField]) -> str | None:
        return _event_kind(fields)

    def python_version(self, cmap: CodeMap) -> tuple[int, int] | None:
        return _python_version(cmap.function.runtime) if cmap.function is not None else None

    def unset_env(self, cmap: CodeMap) -> set[str]:
        fn = cmap.function
        if fn is None or fn.env_error is not None:
            return set()
        return {e.name for e in cmap.env if e.required and e.name not in fn.env_names and e.name not in _LAMBDA_ENV}

    def denied(self, cmap: CodeMap) -> dict[str, str]:
        fn = cmap.function
        if fn is None or getattr(fn, "permissions", None) is None:
            return {}
        return {
            c.permission: f"{fn.name}'s role in {fn.source} doesn't allow {c.permission}"
            for c in cmap.aws
            if c.permission and not c.guessed and not allowed(c.permission, fn.permissions)
        }

    def missing_entry(self, cmap: CodeMap, name: str, others: str) -> str:
        return (
            f"No function {name}() in {cmap.handler_file}: every call fails with Runtime.HandlerNotFound before "
            f"any of its code runs. Point the handler setting at one of its functions{others}, or add it."
        )

    def hang(self, cmap: CodeMap) -> str:
        fn = cmap.function
        timeout = f"its {fn.timeout:,} s timeout" if fn is not None else "its timeout"
        return f"the run waits until Lambda stops it at {timeout}, and you pay for the wait."

    def lost_error(self) -> str:
        return "reports success, so Lambda doesn't retry it, CloudWatch doesn't count the error, and its event is lost."

    def import_error(self, module: str) -> str:
        return f"Runtime.ImportModuleError: No module named '{module}'"

    def install(self, pip: str, them: str) -> str:
        return f"add {them} to the package (pip install {pip} -t .) or a layer"

    def entry_findings(self, cmap: CodeMap) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        if cmap.note or cmap.entry is None:
            return found
        name = (cmap.handler or "").rsplit(".", 1)[-1]
        if cmap.is_async:
            found.append(
                (
                    "warn",
                    (
                        f"{name}() is async def: the Python runtime calls it without awaiting it, so its code never runs "
                        "and the call returns a coroutine. Wrap it in a plain function that runs it: def handler(event, "
                        "context): return asyncio.run(main(event, context))."
                    ),
                )
            )
        elif any(f.name == cmap.entry for f in cmap.functions):  # a function, not an app object
            positional = [p for p in cmap.params if not p.startswith("*")]
            required = [p for p in positional if "=" not in p]
            star = any(p.startswith("*") and not p.startswith("**") for p in cmap.params)
            if len(required) > 2 or (len(positional) < 2 and not star):
                found.append(
                    (
                        "warn",
                        (
                            f"{name}() takes {_plural(len(required), 'argument')}, and Lambda passes two (event and "
                            f"context): every call fails with TypeError. Make it def {name}(event, context)."
                        ),
                    )
                )
        unset = self.unset_env(cmap)
        if unset:
            missing: dict[str, list[EnvRead]] = defaultdict(list)
            for read in cmap.env:
                if read.name in unset:
                    missing[read.name].append(read)
            names = list(missing)
            first = [reads[0] for reads in missing.values()]
            startup = any(r.startup for r in first)
            where = _listed([f"{r.file} line {r.line}" for r in first], 2)
            them = "it" if len(names) == 1 else "them"
            found.append(
                (
                    "warn",
                    (
                        f"{_listed(names)} {'isn' if len(names) == 1 else 'aren'}'t set on {cmap.function.name}, and its code "
                        f"reads {them} with os.environ[...] ({where}): that line fails with KeyError: '{names[0]}'"
                        + (", when Lambda loads the code, so every call fails" if startup else "")
                        + f". Add {them} to its environment variables (the console's Configuration tab, Environment "
                        "variables)."
                    ),
                )
            )
        return found

    def findings(self, cmap: CodeMap) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        if cmap.note:
            return found
        fn = cmap.function
        layered = [i for i in cmap.imports if i.source == "layer" and not i.optional]
        if layered and fn is not None:
            tops = list(dict.fromkeys(i.top for i in layered))
            found.append(
                (
                    "info",
                    (
                        f"{_listed(tops)} {'isn' if len(tops) == 1 else 'aren'}'t in the package, so "
                        f"{'it has' if len(tops) == 1 else 'they have'} to come from its layers "
                        f"({_listed([layer.rsplit(':', 2)[0].rsplit(':', 1)[-1] for layer in fn.layers], 2)}): if no layer has "
                        f"{'it' if len(tops) == 1 else 'them'}, calls fail with Runtime.ImportModuleError."
                    ),
                )
            )
        for spot in self._outside_tmp(cmap):
            name = posixpath.basename(spot.detail.rstrip("/")) or "out"
            found.append(
                (
                    "warn",
                    (
                        f"It writes {spot.detail} at {_where(spot.file, spot.line)}, outside /tmp: Lambda's disk is read-only "
                        f"there, so that line fails with OSError: [Errno 30] Read-only file system. Write under /tmp instead "
                        f"(/tmp/{name})."
                    ),
                )
            )
        for spot in [s for s in cmap.spots if s.kind == "client" and not s.ok]:
            service = _service_name(spot.detail) if spot.detail != "?" else "AWS"
            found.append(
                (
                    "info",
                    (
                        f"It makes a new {service} client on every call, at {_where(spot.file, spot.line, spot.function)}"
                        + (" inside a loop" if spot.loop else "")
                        + ": making one takes time, more on a cold start. Make it once at module level (above the handler), "
                        "so warm calls reuse it."
                    ),
                )
            )
        for spot in [s for s in cmap.spots if s.kind == "connect" and not s.ok and not s.startup]:
            found.append(
                (
                    "info",
                    (
                        f"It opens a new {spot.detail} connection on every call, at "
                        f"{_where(spot.file, spot.line, spot.function)}"
                        + (" inside a loop" if spot.loop else "")
                        + ": that's a round trip or more before any work, and many runs at once can use up the server's "
                        "connections. Make it once at module level (above the handler), so warm calls reuse it."
                    ),
                )
            )
        denied = self.denied(cmap)
        if denied and fn is not None:
            calls = [c for c in cmap.aws if c.permission in denied]
            missing = list(dict.fromkeys(c.permission for c in calls))
            deploy = get_deploy(fn.reader)
            fix = deploy.grant(fn, missing) if deploy is not None else f"allow {', '.join(missing)} in its role"
            given = f" (it has {_listed(fn.policies, 3)})" if fn.policies else ""
            found.append(
                (
                    "warn",
                    (
                        f"{fn.name}'s role in {fn.source}{given} doesn't allow {_listed(missing)}, which "
                        + _listed([f"{c.label} at {_where(c.file, c.line)}" for c in calls], 2)
                        + (" needs: that call fails" if len(calls) == 1 else " need: those calls fail")
                        + f" with AccessDenied. {fix[0].upper()}{fix[1:]}."
                    ),
                )
            )
        for spot in [s for s in cmap.spots if s.kind == "sleep" and not s.startup]:
            found.append(
                (
                    "info",
                    (
                        f"It sleeps at {_where(spot.file, spot.line, spot.function)} ({spot.code}): the function is billed "
                        "for the time it waits. If it waits for something to finish, a Step Functions Wait state or an SQS "
                        "delay costs nothing while it waits."
                    ),
                )
            )
        return found

    def marks(self, cmap: CodeMap) -> dict[str, list[str]]:
        marked: dict[str, list[str]] = defaultdict(list)
        for spot in self._outside_tmp(cmap):
            marked[spot.function].append(f"writes {spot.detail} outside /tmp (line {spot.line})")
        return marked

    @staticmethod
    def _outside_tmp(cmap: CodeMap) -> list[CodeSpot]:
        return [s for s in cmap.spots if s.kind == "write" and not s.detail.startswith(_WRITABLE)]
