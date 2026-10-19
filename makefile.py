#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["rich>=13"]
# ///
"""
The Makefile's tasks in Python, drawn with rich, so they run and look the same on Linux, macOS and Windows.

    python makefile.py                 # list the tasks
    python makefile.py check           # everything CI runs
    python makefile.py test lint       # several, in order
    python makefile.py try --repo ~/projects/aws-analyzer
    uv run makefile.py install         # no .venv yet: uv brings rich
With uv, every task runs through `uv run`, which first brings .venv in line with pyproject.toml and uv.lock.
"""

from __future__ import annotations

import argparse
import difflib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError:  # a Python without rich: hand over to .venv's, or say how to get it
    _venv = Path(__file__).resolve().parent / ".venv"
    _python = _venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if _python.exists() and Path(sys.prefix).resolve() != _venv.resolve():
        sys.exit(subprocess.call([str(_python), str(Path(__file__).resolve()), *sys.argv[1:]]))
    sys.exit("makefile.py draws with rich, which isn't installed here. Run it with uv, which brings rich:\n"
             "    uv run makefile.py install\n"
             "or install rich first: pip install rich")

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
UV = shutil.which("uv")
EXAMPLE = "examples/orders-service"

console = Console(highlight=False)


@dataclass
class Options:
    """
    What the command line said beyond the task names.
    """

    repo: str
    out: str
    port: int


@dataclass
class Task:
    """
    One thing makefile.py can do: an action, the tasks to run before it, or both.
    """

    name: str
    emoji: str
    help: str
    group: str
    action: Callable[[Options], None] | None = None
    needs: tuple[str, ...] = ()
    venv: bool = True  # needs .venv; it is made first when missing
    until_stopped: bool = False  # runs until Ctrl+C, which then isn't a failure


class TaskFailed(Exception):
    """
    A command a task ran exited with an error.
    """


TASKS: dict[str, Task] = {}
GROUPS = ("Set up", "Check", "Run", "Docs", "Release")


def task(name: str, emoji: str, help: str, group: str, *, needs: tuple[str, ...] = (), venv: bool = True,
         until_stopped: bool = False) -> Callable[[Callable[[Options], None]], Callable[[Options], None]]:
    def add(action: Callable[[Options], None]) -> Callable[[Options], None]:
        TASKS[name] = Task(name, emoji, help, group, action, needs, venv, until_stopped)
        return action
    return add


def _shown(word: str) -> str:
    """
    A command word as it reads best: paths inside the repo relative to it, .venv's Python as "python".
    """
    if word == UV:
        return "uv"
    if word == str(VENV_PYTHON):
        return "python"
    if word.startswith(str(ROOT) + os.sep):
        return os.path.relpath(word, ROOT)
    return word


def run(*command: str | Path) -> None:
    words = [str(word) for word in command]
    console.print(Text("  $ ", style="dim") + Text(" ".join(_shown(word) for word in words), style="cyan"),
                  soft_wrap=True)
    code = subprocess.call(words, cwd=ROOT)
    if code:
        raise TaskFailed(f"`{' '.join(_shown(word) for word in words[:3])} …` exited with {code}")


def python(*arguments: str | Path) -> None:
    if UV:
        run(UV, "run", "python", *arguments)
    else:
        run(VENV_PYTHON, *arguments)


def code_node(options: Options, *arguments: str) -> None:
    python("-m", "code_node", options.repo, *arguments)


# Set up

@task("install", "📦", "make .venv with code-node and every dependency group in pyproject.toml", "Set up",
      venv=False)
def install(options: Options) -> None:
    if UV:
        run(UV, "sync")
        return
    # Without uv: pip reads the same groups (pip 25.1 or later), at pyproject.toml's pins rather than uv.lock's.
    if not VENV_PYTHON.exists():
        run(sys.executable, "-m", "venv", VENV)
    python("-m", "pip", "install", "-q", "--upgrade", "pip")
    python("-m", "pip", "install", "-e", ".", "--group", "dev", "--group", "docs")


@task("tool", "🚀", "put code-node on your PATH, live-edited (needs uv)", "Set up", venv=False)
def tool(options: Options) -> None:
    if not UV:
        raise TaskFailed("this needs uv: https://docs.astral.sh/uv/getting-started/installation/")
    run(UV, "tool", "install", "-e", ".")


@task("clean", "🧹", "remove build output and caches (keeps .venv)", "Set up", venv=False)
def clean(options: Options) -> None:
    removed = 0
    for path in [ROOT / name for name in ("dist", "build", "site", ".pytest_cache", ".ruff_cache", ".mypy_cache")]:
        if path.exists():
            shutil.rmtree(path)
            removed += 1
    for path in (ROOT / "src").glob("*.egg-info"):
        shutil.rmtree(path)
        removed += 1
    for folder, subfolders, _ in os.walk(ROOT):
        subfolders[:] = [name for name in subfolders if name not in (".venv", ".git")]
        if "__pycache__" in subfolders:
            shutil.rmtree(Path(folder) / "__pycache__")
            subfolders.remove("__pycache__")
            removed += 1
    console.print(f"  [dim]removed {removed} folder{'' if removed == 1 else 's'}[/]")


# Check

@task("lint", "🔍", "ruff check", "Check")
def lint(options: Options) -> None:
    python("-m", "ruff", "check", ".")


@task("fix", "🔧", "ruff check --fix", "Check")
def fix(options: Options) -> None:
    python("-m", "ruff", "check", "--fix", ".")


@task("test", "🧪", "run the tests", "Check")
def test(options: Options) -> None:
    python("-m", "pytest", "-q")


TASKS["check"] = Task("check", "✅", "everything CI runs: lint, test, try, docs, package", "Check",
                      needs=("lint", "test", "try", "docs", "package"))


# Run

@task("try", "🧭", "draw --repo's page to --out without opening it", "Run")
def try_page(options: Options) -> None:
    code_node(options, "--no-open", "-o", options.out)


@task("serve", "📡", "serve --repo's page on --port, redrawn on every save", "Run", until_stopped=True)
def serve(options: Options) -> None:
    code_node(options, "--serve", "--port", str(options.port))


@task("mermaid", "🌊", "print --repo's graph as Mermaid", "Run")
def mermaid(options: Options) -> None:
    code_node(options, "--mermaid")


# Docs

@task("docs", "📖", "build the docs site, failing on a broken link", "Docs")
def docs(options: Options) -> None:
    python("-m", "mkdocs", "build", "--strict")


@task("docs-serve", "👀", "serve the docs site locally", "Docs", until_stopped=True)
def docs_serve(options: Options) -> None:
    python("-m", "mkdocs", "serve")


@task("shots", "📸", "remake docs/images/ (needs Chrome)", "Docs")
def shots(options: Options) -> None:
    python("scripts/shots.py")


@task("site-graph", "🎨", "remake the home page's graph (docs/snippets/graph-trace.svg)", "Docs")
def site_graph(options: Options) -> None:
    python("scripts/site_graph.py")


# Release

@task("package", "🎁", "build the sdist and wheel, and check them as PyPI would", "Release")
def package(options: Options) -> None:
    shutil.rmtree(ROOT / "dist", ignore_errors=True)
    python("-m", "build", "-q")
    built = sorted(path.relative_to(ROOT) for path in (ROOT / "dist").glob("*"))
    if not built:
        raise TaskFailed("the build left nothing in dist/")
    python("-m", "twine", "check", "--strict", *built)


def show_tasks() -> None:
    table = Table(box=box.ROUNDED, border_style="grey50", show_header=False, padding=(0, 1),
                  title="🧩 [bold]code-node[/] tasks", title_justify="left")
    table.add_column(width=2)
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column()
    for number, group in enumerate(GROUPS):
        if number:
            table.add_section()
        table.add_row("", f"[bold magenta]{group}[/]", "")
        for each in TASKS.values():
            if each.group == group:
                table.add_row(each.emoji, each.name, each.help)
    console.print(table)
    usage = Table.grid(padding=(0, 3))
    usage.add_column(style="green", no_wrap=True)
    usage.add_column(style="dim")
    for example, meaning in [
        ("python makefile.py check", "run everything CI runs"),
        ("python makefile.py test lint", "run several, in order"),
        ("python makefile.py try --repo PATH", f"draw another folder's page (default {EXAMPLE})"),
        ("python makefile.py serve --port 0", "serve on a free port"),
        ("python makefile.py -k check", "keep going after a task fails"),
        ("uv run makefile.py install", "no .venv yet? uv brings rich"),
    ]:
        usage.add_row(example, meaning)
    console.print(Panel(usage, title="💡 how", title_align="left", border_style="grey50", box=box.ROUNDED,
                        expand=False))


def plan(names: list[str]) -> list[Task]:
    """
    The tasks to run, in order: each one's needs before it, none twice, and install first when .venv is missing.
    """
    ordered: list[Task] = []

    def add(name: str) -> None:
        each = TASKS[name]
        if each in ordered:
            return
        for need in each.needs:
            add(need)
        if each.action:
            ordered.append(each)

    for name in names:
        add(name)
    if not VENV_PYTHON.exists() and any(each.venv for each in ordered) and TASKS["install"] not in ordered:
        console.print("[yellow]⚠️  No .venv yet, so making it first.[/]")
        ordered.insert(0, TASKS["install"])
    return ordered


def _seconds(seconds: float) -> str:
    return f"{seconds:.1f}s" if seconds < 60 else f"{int(seconds // 60)}m {seconds % 60:.0f}s"


def run_tasks(tasks: list[Task], options: Options, keep_going: bool) -> int:
    results: list[tuple[Task, str, float]] = []  # the task, "passed" / "failed" / "stopped", seconds
    started = time.perf_counter()
    for each in tasks:
        console.print()
        console.rule(f"{each.emoji}  [bold]{each.name}[/]  [dim]{each.help}[/]", align="left", style="cyan")
        began = time.perf_counter()
        assert each.action is not None  # plan() keeps only tasks that do something
        try:
            each.action(options)
        except TaskFailed as failure:
            took = time.perf_counter() - began
            results.append((each, "failed", took))
            console.print(f"[bold red]❌ {each.name} failed[/] [dim]in {_seconds(took)}:[/] {failure}")
            if not keep_going:
                break
        except KeyboardInterrupt:
            took = time.perf_counter() - began
            results.append((each, "stopped", took))
            console.print(f"\n[yellow]🛑 {each.name} stopped[/] [dim]after {_seconds(took)}[/]")
            break
        else:
            took = time.perf_counter() - began
            results.append((each, "passed", took))
            console.print(f"[green]✔ {each.name}[/] [dim]{_seconds(took)}[/]")

    failed = [each.name for each, result, _ in results if result == "failed"]
    interrupted = [each for each, result, _ in results if result == "stopped" and not each.until_stopped]
    skipped = tasks[len(results):]
    total = _seconds(time.perf_counter() - started)
    console.print()
    if len(tasks) > 1:
        summary = Table(box=box.SIMPLE_HEAD, header_style="bold", padding=(0, 1))
        summary.add_column("task")
        summary.add_column("result")
        summary.add_column("time", justify="right", style="dim")
        marks = {"passed": "[green]✅ passed[/]", "failed": "[red]❌ failed[/]", "stopped": "[yellow]🛑 stopped[/]"}
        for each, result, took in results:
            summary.add_row(f"{each.emoji} {each.name}", marks[result], _seconds(took))
        for each in skipped:
            summary.add_row(f"{each.emoji} {each.name}", "[dim]⏩ skipped[/]", "")
        console.print(summary)
    if failed:
        console.print(Panel(f"[bold]{', '.join(failed)}[/] failed  [dim]· {total}[/]", title="💥",
                            title_align="left", border_style="red", box=box.ROUNDED, expand=False))
        return 1
    if interrupted:
        console.print(Panel(f"Stopped  [dim]· {total}[/]", border_style="yellow", box=box.ROUNDED, expand=False))
        return 130
    done = len(results)
    console.print(Panel(f"[bold]{done} task{'' if done == 1 else 's'}[/] done  [dim]· {total}[/]", title="🎉",
                        title_align="left", border_style="green", box=box.ROUNDED, expand=False))
    return 0


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="makefile.py", add_help=False)
    parser.add_argument("tasks", nargs="*")
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("-k", "--keep-going", action="store_true")
    parser.add_argument("--repo", default=EXAMPLE)
    parser.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "code-node-page.html"))
    parser.add_argument("--port", type=int, default=8765)
    parsed = parser.parse_args(arguments)
    if parsed.help or not parsed.tasks or parsed.tasks == ["help"]:
        show_tasks()
        return 0
    unknown = [name for name in parsed.tasks if name not in TASKS]
    if unknown:
        for name in unknown:
            close = difflib.get_close_matches(name, TASKS, n=1)
            hint = f" Did you mean [bold cyan]{close[0]}[/]?" if close else ""
            console.print(f"[red]❓ No task called [bold]{name}[/].[/]{hint}")
        console.print("[dim]python makefile.py lists them.[/]")
        return 2
    options = Options(repo=parsed.repo, out=parsed.out, port=parsed.port)
    return run_tasks(plan(parsed.tasks), options, parsed.keep_going)


if __name__ == "__main__":
    sys.exit(main())
