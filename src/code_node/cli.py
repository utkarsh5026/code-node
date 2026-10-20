"""
code-node: run it in a folder of Python code and it opens a page showing how the code works from an entry point,
as a graph of who calls whom and what each path reaches, and the steps of each call.

    code-node                       # this folder: picks an entry point (asks when there are several)
    code-node src/app/main.py       # start from a file: its main(), or pick one of its functions
    code-node src/app/main.py:run   # ...or name the function (or Class.method) in it
    code-node path/to/repo -e pkg.cli.main
    code-node --list                # the entry points it found
    code-node --all                 # every function in the graph, however deep
    code-node --serve               # a live page on localhost that redraws whenever the code changes
    code-node --editor cursor       # line links open in Cursor (vscode by default, none for no links)
    code-node --plugins             # the platforms, libraries and deploy files it reads code with
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from .deploys import deploys
from .libraries import libraries
from .pages import GRAPH_DEPTH, GRAPH_FUNCTIONS, PageOptions, make_mermaid, make_page
from .platforms import platforms
from .report.editor import EDITORS
from .project import (
    EntryPoint, Project, entries_in_file, entry_in_files, entry_points, functions_matching, project_root, read_project,
)
_CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "code-node"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="code-node", description="See how Python code works: a graph of what calls what and what it reaches.")
    parser.add_argument("path", nargs="?", default=".",
                        help="the folder to read (default: this one), or the file to start from: main.py or "
                             "main.py:function")
    parser.add_argument("-e", "--entry", help="where to start: module.function, module.Class.method, "
                                              "path/to/file.py[:function], or part of a function's name")
    parser.add_argument("-l", "--list", action="store_true", help="list the entry points found, and stop")
    parser.add_argument("--plugins", action="store_true",
                        help="list the plugins it reads code with (platforms, libraries, deploy files), and stop")
    parser.add_argument("-o", "--out", help="where to save the page (default: ~/.cache/code-node/)")
    parser.add_argument("--no-open", action="store_true", help="save the page without opening a browser")
    parser.add_argument("--all", action="store_true", help="draw every function, however deep (big graphs)")
    parser.add_argument("--depth", type=int, default=GRAPH_DEPTH, help="calls deep the graph draws (default 5)")
    parser.add_argument("--functions", type=int, default=GRAPH_FUNCTIONS,
                        help="functions the graph draws at most (default 24)")
    parser.add_argument("--mermaid", action="store_true", help="print the graph as Mermaid instead of a page")
    parser.add_argument("--serve", action="store_true",
                        help="serve the page on localhost and redraw it whenever a .py file changes")
    parser.add_argument("--port", type=int, default=None,
                        help="the --serve port (default: the first free one from 8765; 0 picks any free one)")
    names = [p.name for p in platforms()]
    parser.add_argument("--platform", choices=names, default="",
                        help="where the code runs, for that platform's checks (found entry points set it: a Lambda "
                             "handler is lambda; default plain Python)")
    parser.add_argument("--lambda", dest="platform", action="store_const", const="lambda",
                        help="the same as --platform lambda")
    parser.add_argument("--editor", choices=[*EDITORS, "none"], default="vscode",
                        help="the editor the page's line links open (default vscode; none for no links)")
    return parser.parse_args(argv)


def _ask(candidates: list[EntryPoint]) -> EntryPoint:
    """
    The entry point the user picks from a numbered list (the first, when nobody's there to ask).
    """
    if len(candidates) == 1 or not sys.stdin.isatty():
        return candidates[0]
    _print_entries(candidates)
    while True:
        answer = input(f"Start from which one? [1-{len(candidates)}, Enter for 1] ").strip()
        if not answer:
            return candidates[0]
        if answer.isdigit() and 1 <= int(answer) <= len(candidates):
            return candidates[int(answer) - 1]


def _print_entries(candidates: list[EntryPoint]) -> None:
    width = max(len(c.name) for c in candidates)
    for i, entry in enumerate(candidates, 1):
        print(f"  {i:>2}. {entry.name:<{width}}  {entry.why}  ({entry.file}:{entry.line})")


def _pick_entry(project: Project, given: str | None) -> EntryPoint | None:
    """
    The entry point to start from: the one given (exactly, or found by part of its name), else one found.
    """
    if given:
        named = entry_in_files(project, given)
        if named is not None:
            return named
        exact = [c for c in entry_points(project) + functions_matching(project, given.rsplit(".", 1)[-1])
                 if c.name == given]
        if exact:
            return exact[0]
        if "." in given and not functions_matching(project, given):
            return EntryPoint(given, "given", "", 0)
        matches = functions_matching(project, given)
        if not matches:
            print(f"No function in {project.root} matches {given!r}.", file=sys.stderr)
            return None
        return _ask(matches[:30])
    found = entry_points(project)
    if not found:
        kinds = ["console script", "main()", *(p.entry_kind.split(":")[0].split(" (")[0].removeprefix("a ")
                                               for p in platforms() if p.entry_kind)]
        print(f"Found no entry point in {project.root}: no {', '.join(kinds[:-1])}, or {kinds[-1]}. Name one with -e "
              "module.function.", file=sys.stderr)
        return None
    return _ask(found[:30])


def _print_plugins() -> None:
    """
    Every plugin installed, by kind: built-in ones and those other packages add.
    """
    kinds = [
        ("Platforms (one per entry point: where it runs)",
         [(p.name, p.title, p.entry_kind or "") for p in platforms()]),
        ("Libraries (as many as the code imports: what it reaches)",
         [(lib.name, lib.title, ", ".join(lib.modules)) for lib in libraries()]),
        ("Deploy files (each found in the folder: how it's deployed)",
         [(d.name, d.title, ", ".join(d.files)) for d in deploys()]),
    ]
    for title, rows in kinds:
        print(title)
        width = max((len(name) for name, _, _ in rows), default=0)
        for name, label, what in rows:
            print(f"  {name:<{width}}  {label}" + (f"  ({what})" if what else ""))


def _is_wsl() -> bool:
    version = Path("/proc/version")
    return version.exists() and "microsoft" in version.read_text(errors="ignore").lower()


def _open(target: str) -> None:
    """
    Opens a saved page (a path) or the server (a URL) in the browser, from WSL too (where Python's webbrowser often
    can't reach Windows').
    """
    is_url = target.startswith("http")
    if _is_wsl():
        if shutil.which("wslview"):
            subprocess.run(["wslview", target], check=False)
            return
        if shutil.which("explorer.exe"):
            where = target if is_url else subprocess.run(
                ["wslpath", "-w", target], capture_output=True, text=True, check=False).stdout.strip()
            subprocess.run(["explorer.exe", where], check=False)
            return
    webbrowser.open(target if is_url else Path(target).as_uri())


def _out_path(given: str | None, project: Project, entry: str) -> Path:
    if given:
        return Path(given).expanduser().resolve()
    slug = re.sub(r"[^\w.-]+", "-", f"{project.root.name}--{entry}")
    return _CACHE / f"{slug}.html"


def _split_file(text: str) -> tuple[Path, str] | None:
    """
    'src/app.py:run' -> (src/app.py, 'run'); 'src/app.py' -> (src/app.py, ''); None when it isn't a .py file.
    """
    file, _, function = text.partition(".py:") if ".py:" in text else (text, "", "")
    path = Path(file + (".py" if function or text.endswith(".py:") else "")).expanduser()
    return (path.resolve(), function) if path.suffix == ".py" and path.is_file() else None


def _from_file(project: Project, file: Path, function: str) -> EntryPoint | None:
    """
    The entry point in a file: the function given, else the best of the file's (asking when there are several).
    """
    rel = file.relative_to(project.root).as_posix()
    if rel not in project.files:
        print(f"{rel} is skipped (a virtual environment, cache or build folder).", file=sys.stderr)
        return None
    found = entries_in_file(project, rel, function)
    if not found:
        print(f"{rel} has no functions to start from: code-node follows a function (a script's top-level code "
              "isn't one yet).", file=sys.stderr)
        return None
    return _ask(found[:30])


def _root_for(path: Path, file: Path | None) -> Path:
    """
    The folder to read: the one given, unless a file to start from was given that isn't in it (or as the path
    itself), when it's that file's project.
    """
    if file is None:
        return path
    folder = path.resolve()
    if path.is_dir() and folder in file.parents:
        return folder if path != Path(".") else project_root(file)
    return project_root(file)


def main(argv: list[str] | None = None) -> int:
    """
    The code-node command.
    """
    args = _parse_args(argv)
    if args.plugins:
        _print_plugins()
        return 0
    in_file = _split_file(args.path) or (_split_file(args.entry) if args.entry else None)
    root = _root_for(Path(args.path).expanduser(), in_file[0] if in_file else None)
    if not root.is_dir():
        print(f"{root} isn't a folder or a .py file.", file=sys.stderr)
        return 2
    project = read_project(root)
    if not project.files:
        print(f"No Python files under {project.root}.", file=sys.stderr)
        return 1
    if args.list:
        found = entry_points(project)
        print(f"{len(found)} entry point{'s' if len(found) != 1 else ''} in {project.root}:")
        _print_entries(found or [EntryPoint("(none: name one with -e module.function)", "", "-", 0)])
        return 0
    entry = _from_file(project, *in_file) if in_file else _pick_entry(project, args.entry)
    if entry is None:
        return 1
    options = PageOptions(draw_all=args.all, functions=args.functions, depth=args.depth, platform=args.platform,
                          editor=args.editor)
    if args.mermaid:
        print(make_mermaid(project.root, entry, options))
        return 0
    if args.serve:
        from .serve import serve

        return serve(project.root, entry, options, port=args.port, open_page=None if args.no_open else _open)
    page, cmap = make_page(project.root, entry, options)
    out = _out_path(args.out, project, entry.name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, "utf-8")
    services = list(dict.fromkeys(call.service for call in cmap.library_calls))
    print(f"{entry.name}: {len(cmap.functions)} functions, {len(cmap.aws)} AWS calls"
          + (f", {len(cmap.library_calls)} through libraries ({', '.join(services)})" if services else "")
          + (f" ({cmap.note})" if cmap.note else "")
          + (f"\nDeployed as {cmap.function.name} in {cmap.function.source}" if cmap.function is not None else "")
          + f"\nSaved {out}")
    if not args.no_open:
        _open(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
