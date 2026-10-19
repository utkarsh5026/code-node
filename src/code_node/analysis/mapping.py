"""
map_code(): a CodeMap of how code works from one entry point, read with ast from its files.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..kit.text import _clip

from .terms import _LIBRARIES, _RUNTIME_MODULES
from .model import CodeMap
from .reader import _CodeReader


def _python_version(runtime: str | None) -> tuple[int, int] | None:
    """
    'python3.12' -> (3, 12).
    """
    match = re.fullmatch(r"python(\d+)\.(\d+)", runtime or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


def entry_file(entry: str, names: Iterable[str]) -> tuple[str, str] | None:
    """
    The file an entry point is in, and the folder its modules are named from: 'pkg.cli.main' -> ('src/pkg/cli.py',
    'src/'); 'pkg.cli.App.run' (a method) is found in 'pkg/cli.py' too. None when no file matches.
    """
    parts = entry.split(".")[:-1]
    names = list(names)
    for cut in (len(parts), len(parts) - 1):
        if cut < 1:
            continue
        stem = "/".join(parts[:cut])
        for suffix in (f"{stem}.py", f"{stem}/__init__.py"):
            for name in sorted(names, key=len):
                if name == suffix or name.endswith("/" + suffix):
                    return name, name[: -len(suffix)]
    return None


def _given_file(entry: str, file: str) -> tuple[str, str] | None:
    """
    The entry point's file as given, and the folder its modules are named from: ('pkg.cli.main', 'src/pkg/cli.py')
    -> ('src/pkg/cli.py', 'src/').
    """
    for cut in (1, 2):
        module = entry.rsplit(".", cut)[0]
        for stem in (module.replace(".", "/") + ".py", module.replace(".", "/") + "/__init__.py"):
            if file == stem or file.endswith("/" + stem):
                return file, file[: -len(stem)]
    return None


def map_code(
    files: dict[str, str | bytes],
    entry: str,
    *,
    names: Iterable[str] | None = None,
    libraries: Iterable[str] = (),
    file: str | None = None,
    python: str | None = None,
    max_depth: int | None = None,
    platform: str = "",
) -> CodeMap:
    """
    How Python code works, read with Python's ast module and never run: files is {path: source}, entry the function
    to start from as module.function ('pkg.cli.main') or module.Class.method. Starting there, it follows the code into
    its own functions and modules, keeping track of what each name holds (a boto3 client, part of its input, an
    environment variable...), and returns a CodeMap: what runs at import and on each call, step by step, its AWS calls
    with the IAM permission each needs, the environment variables it reads, the libraries it imports. file is the
    entry point's file when it's known (else the first file whose path matches its module); platform='lambda' adds
    the checks only a Lambda handler needs.

        map_code({"app.py": open("app.py").read()}, "app.handler")
    """
    texts = {path: text.decode("utf-8", "replace") if isinstance(text, bytes) else str(text)
             for path, text in files.items()}
    names = list(names) if names is not None else list(texts)
    cmap = CodeMap(None, entry, platform=platform)
    if not entry or "." not in entry:
        cmap.note = f"The entry point ({entry or 'none'}) doesn't name a module and a function, like app.main."
        return cmap
    found = _given_file(entry, file) if file else entry_file(entry, names)
    if found is None:
        module = entry.rsplit(".", 1)[0].replace(".", "/")
        cmap.note = f"No file matches the entry point {entry} (looked for {module}.py)."
        return cmap
    cmap.handler_file, root = found
    libs = set(libraries) | _RUNTIME_MODULES | _LIBRARIES
    libs.discard(entry.split(".")[0])  # its own top package is never a library
    reader = _CodeReader(texts, names, root, cmap, _python_version(python), libs, False)
    if max_depth is not None:
        reader.max_depth = max_depth
    try:
        reader.read(entry)
    except RecursionError:
        cmap.limited = "stopped where the code nests too deep to follow"
    except Exception as exc:  # noqa: BLE001  code it can't follow: what it found so far, said to be partial
        cmap.limited = f"stopped partway, at code it couldn't follow ({type(exc).__name__}: {_clip(str(exc), 80)})"
    if cmap.limited.startswith("stopped"):
        cmap.functions, cmap.event = list(reader.reached.values()), list(reader.event_reads.values())
        cmap.routes = [(method, path, key) for method, path, key, _ in reader.routes]
    return cmap
