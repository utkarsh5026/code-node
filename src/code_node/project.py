"""
A folder of Python code: its files, the names Python imports them by, and the entry points worth starting from.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .analysis.syntax import _parse
from .deploys import all_deployments, deploy_file_names
from .platforms import platforms

_SKIPPED_FOLDERS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        ".env",
        "node_modules",
        "__pycache__",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
        "site-packages",
        ".eggs",
        ".idea",
        ".vscode",
    }
)

_MAX_FILES = 5_000  # Python files read from one folder, at most

_MAX_FILE_BYTES = 2 * 1024 * 1024  # a bigger .py file is generated code: skipped

_MAIN_NAMES = ("main", "run", "cli", "app")

_IMPORT_RE = re.compile(r"^[ \t]*(?:from[ \t]+([\w.]+)[ \t]+import|import[ \t]+([\w., \t]+))", re.M)

_PATH_SETTINGS = (  # where a pyproject.toml puts folders on the import path: (table, key)
    ("tool.pyright", "extraPaths"),
    ("tool.basedpyright", "extraPaths"),
    ("tool.pytest.ini_options", "pythonpath"),
)

_VSCODE_PATHS_RE = re.compile(r'"python\.(?:analysis|autoComplete)\.extraPaths"\s*:\s*\[(.*?)\]', re.S)

_CLI_APPS = ("Typer",)  # web apps are a platform's (FastAPI for the web one, Chalice for Lambda's)


@dataclass
class EntryPoint:
    """
    A place to start reading the code from: 'pkg.cli.main', and why it's a good one.
    """

    name: str  # module.function, module.Class.method, or module.app (a web app object)
    why: str  # 'a console script (code-node)', 'runs under if __name__ == "__main__"', 'a Lambda handler'
    file: str
    line: int
    platform: str = ""  # the platform that found it ('lambda' for a Lambda handler): its checks run on the code


@dataclass
class Project:
    """
    The Python files under a folder, read as text: {path from the folder, with /: source}.
    """

    root: Path
    files: dict[str, str] = field(default_factory=dict)
    modules: dict[str, str] = field(default_factory=dict)  # file -> the module name Python imports it by
    skipped: list[str] = field(default_factory=list)
    limited: bool = False
    configs: list[str] = field(default_factory=list)  # its pyproject.toml files, the root's first
    deploy_files: dict[str, str] = field(default_factory=dict)  # files deploy plugins read (template.yaml,
    # serverless.yml): {path from the folder: text}
    paths: list[str] = field(default_factory=list)  # the other folders imports start from, as the project puts
    # them on sys.path (pyright's extraPaths, pytest's pythonpath): 'src/', or '' for the folder itself
    _trees: dict[str, ast.Module] | None = None

    @property
    def trees(self) -> dict[str, ast.Module]:
        """
        Each file's syntax tree, parsed the first time it's asked for (files that don't parse are left out).
        """
        if self._trees is None:
            self._trees = {}
            for rel, text in self.files.items():
                try:
                    self._trees[rel] = _parse(text, rel)
                except (SyntaxError, ValueError):
                    self.skipped.append(rel)
        return self._trees

    @property
    def own_tops(self) -> set[str]:
        """
        The top-level packages and modules that are this folder's own code.
        """
        return {module.split(".")[0] for module in self.modules.values()}

    def libraries(self) -> set[str]:
        """
        Every top-level module the code imports that isn't its own: read as installed libraries, never as missing.
        """
        own = self.own_tops | {
            rel[len(place) :].split("/")[0].split(".")[0]
            for place in self.paths
            for rel in self.files
            if rel.startswith(place)
        }
        found: set[str] = set()
        for text in self.files.values():
            for match in _IMPORT_RE.finditer(text):
                names = match.group(1) or match.group(2)
                found |= {name.strip().split(".")[0] for name in names.split(",")}
        found = {name.split(" ")[0] for name in found if name}
        return {name for name in found if name not in own and name not in sys.stdlib_module_names}


def _module_name(path: Path, root: Path) -> str:
    """
    The name Python imports a file by: up through the folders that hold an __init__.py, the way a package is laid
    out. 'src/pkg/sub/mod.py' (pkg and sub with __init__.py) -> 'pkg.sub.mod'.
    """
    parts = [path.stem] if path.name != "__init__.py" else []
    folder = path.parent
    while folder != root and (folder / "__init__.py").exists():
        parts.insert(0, folder.name)
        folder = folder.parent
    return ".".join(parts)


def read_project(root: str | os.PathLike[str]) -> Project:
    """
    Every .py file under root, skipping virtual environments, caches and build output.
    """
    base = Path(root).resolve()
    project = Project(base)
    deploy_names = deploy_file_names()
    for folder, subfolders, names in os.walk(base):
        subfolders[:] = sorted(d for d in subfolders if d not in _SKIPPED_FOLDERS and not d.endswith(".egg-info"))
        for name in sorted(names):
            if name == "pyproject.toml":
                project.configs.append((Path(folder) / name).relative_to(base).as_posix())
            if name in deploy_names and (Path(folder) / name).stat().st_size <= _MAX_FILE_BYTES:
                rel = (Path(folder) / name).relative_to(base).as_posix()
                project.deploy_files[rel] = (Path(folder) / name).read_text("utf-8", "replace")
            if not name.endswith(".py"):
                continue
            path = Path(folder) / name
            rel = path.relative_to(base).as_posix()
            if len(project.files) >= _MAX_FILES:
                project.limited = True
                return project
            if path.stat().st_size > _MAX_FILE_BYTES:
                project.skipped.append(rel)
                continue
            text = path.read_text("utf-8", "replace")
            project.files[rel] = text
            project.modules[rel] = _module_name(path, base)
    project.paths = import_paths(base)
    return project


def _toml_lists(text: str, table: str, key: str) -> list[str]:
    """
    A pyproject.toml setting that's a list of strings, or one string: ["src"] for extraPaths = ["src"].
    """
    try:
        import tomllib
    except ImportError:  # Python 3.10: find the table and the key by hand
        body = re.search(rf"^\[{re.escape(table)}\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
        value = body and re.search(rf"^\s*{key}\s*=\s*(\[.*?\]|\"[^\"]*\"|'[^']*')", body.group(1), re.M | re.S)
        if not value:
            return []
        if value.group(1).startswith("["):
            return re.findall(r"[\"']([^\"']*)[\"']", value.group(1))
        return value.group(1)[1:-1].split()
    try:
        data: object = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    for part in [*table.split("."), key]:
        data = data.get(part) if isinstance(data, dict) else None
    if isinstance(data, str):
        return data.split()  # pytest's pythonpath = "src lib" is split on spaces
    return [str(item) for item in data] if isinstance(data, list) else []


def import_paths(root: Path) -> list[str]:
    """
    The folders under root the project puts on the import path, as prefixes of its files' paths ('src/', or '' for
    root itself): pyright's (and Pylance's) extraPaths, in pyproject.toml, pyrightconfig.json or .vscode/settings.json,
    and pytest's pythonpath. Folders outside root, or that aren't there, are left out.
    """
    found: list[str] = []
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text("utf-8", "replace")
        for table, key in _PATH_SETTINGS:
            found += _toml_lists(text, table, key)
    pyright = root / "pyrightconfig.json"
    if pyright.is_file():
        try:
            data = json.loads(pyright.read_text("utf-8", "replace"))
        except ValueError:
            data = {}
        extra = data.get("extraPaths") if isinstance(data, dict) else None
        found += [str(item) for item in extra] if isinstance(extra, list) else []
    vscode = root / ".vscode" / "settings.json"
    if vscode.is_file():  # JSON with comments, so the lists are found as text
        for match in _VSCODE_PATHS_RE.finditer(vscode.read_text("utf-8", "replace")):
            found += re.findall(r'"([^"]*)"', match.group(1))
    return folder_prefixes(root, [root / item.replace("${workspaceFolder}", ".") for item in found])


def folder_prefixes(root: Path, folders: list[Path]) -> list[str]:
    """
    Folders as prefixes of the paths of root's files: [root/'src'] -> ['src/']; root itself is ''. Folders outside
    root, or that aren't there, are left out.
    """
    base = root.resolve()
    prefixes: list[str] = []
    for folder in folders:
        folder = folder.resolve()
        if not folder.is_dir() or (folder != base and base not in folder.parents):
            continue
        rel = folder.relative_to(base).as_posix()
        prefix = "" if rel == "." else rel + "/"
        if prefix not in prefixes:
            prefixes.append(prefix)
    return prefixes


def _console_scripts(path: Path) -> dict[str, str]:
    """
    A pyproject.toml's console scripts: {'code-node': 'code_node.cli:main'}.
    """
    if not path.exists():
        return {}
    text = path.read_text("utf-8", "replace")
    try:
        import tomllib
    except ImportError:  # Python 3.10: read the [project.scripts] table by hand
        table = re.search(r"^\[(?:project\.scripts|tool\.poetry\.scripts)\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
        lines = table.group(1).splitlines() if table else []
        pairs = (re.match(r"\s*['\"]?([\w.-]+)['\"]?\s*=\s*['\"]([\w.:]+)['\"]", line) for line in lines)
        return {match.group(1): match.group(2) for match in pairs if match}
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    scripts = dict(data.get("project", {}).get("scripts", {}))
    scripts.update(data.get("tool", {}).get("poetry", {}).get("scripts", {}))
    return {name: str(target) for name, target in scripts.items()}


def _main_guard_calls(tree: ast.Module) -> list[str]:
    """
    The functions an `if __name__ == "__main__":` block calls: ['main'].
    """
    called = []
    for node in tree.body:
        is_guard = (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
        )
        if not is_guard:
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                called.append(inner.func.id)
    return called


def _module_functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _web_apps(tree: ast.Module) -> list[tuple[str, int, str, str]]:
    """
    Module-level web and CLI apps, with the platform whose app it is: `app = FastAPI()` -> [('app', 3, 'a web app:
    each route', 'web')].
    """
    found = []
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        func = node.value.func
        made = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        web = next((platform.name for platform in platforms() if made in platform.web_apps), None)
        if web is not None or made in _CLI_APPS:
            kind = "a CLI app: each command" if web is None else "a web app: each route"
            found += [(t.id, node.lineno, kind, web or "") for t in node.targets if isinstance(t, ast.Name)]
    return found


def _calls(node: ast.AST) -> set[str]:
    """
    The plain names a function calls: {'app', 'print'}.
    """
    return {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def _is_test(rel: str) -> bool:
    """
    A test file: under tests/ or named test_*.py / *_test.py / conftest.py.
    """
    name = rel.rsplit("/", 1)[-1]
    return (
        "tests/" in f"/{rel}"
        or "/test/" in f"/{rel}"
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def entry_points(project: Project) -> list[EntryPoint]:
    """
    Where the code starts, best first: console scripts, the entry points platforms find (Lambda handlers), web apps,
    then what runs under `if __name__ == "__main__":` and functions named main.
    """
    found: dict[str, EntryPoint] = {}
    by_module = {module: rel for rel, module in project.modules.items()}

    def add(entry: EntryPoint) -> None:
        found.setdefault(entry.name, entry)

    scripts = [
        (script, target, config)
        for config in project.configs
        for script, target in _console_scripts(project.root / config).items()
    ]
    for script, target, config in scripts:
        module, _, function = target.partition(":")
        rel = by_module.get(module)
        if not (rel and function and rel in project.trees):
            continue
        tree = project.trees[rel]
        node = _module_functions(tree).get(function.split(".")[0])
        apps = {name: (line, kind, runs_on) for name, line, kind, runs_on in _web_apps(tree)}
        runs = [name for name in (_calls(node) if node is not None else set()) if name in apps]
        command = f"the {script} command" + (f" in {config}" if "/" in config else "")
        if runs:  # main() just runs the app: start from the app, so each command is followed
            line, kind, runs_on = apps[runs[0]]
            add(EntryPoint(f"{module}.{runs[0]}", f"{command} ({kind})", rel, line, runs_on))
        add(EntryPoint(f"{module}.{function}", command, rel, getattr(node, "lineno", 0)))
    code = {rel: tree for rel, tree in project.trees.items() if not _is_test(rel)}
    for deployed in all_deployments(project.deploy_files, project.files):
        tree = project.trees.get(deployed.file)
        node = _module_functions(tree).get(deployed.function) if tree is not None else None
        if node is not None:
            add(
                EntryPoint(
                    f"{project.modules[deployed.file]}.{deployed.function}",
                    f"{deployed.name} in {deployed.source}",
                    deployed.file,
                    node.lineno,
                    deployed.platform,
                )
            )
    for rel, tree in code.items():
        module = project.modules[rel]
        for platform in platforms():
            for name, line, why in platform.find_entries(module, tree):
                add(EntryPoint(f"{module}.{name}", why, rel, line, platform.name))
        for name, line, kind, runs_on in _web_apps(tree):
            add(EntryPoint(f"{module}.{name}", kind, rel, line, runs_on))
    for rel, tree in code.items():
        module = project.modules[rel]
        functions = _module_functions(tree)
        for name in _main_guard_calls(tree):
            if name in functions:
                add(EntryPoint(f"{module}.{name}", 'runs under if __name__ == "__main__"', rel, functions[name].lineno))
    for rel, tree in code.items():
        functions = _module_functions(tree)
        for name in _MAIN_NAMES:
            if name in functions:
                add(
                    EntryPoint(
                        f"{project.modules[rel]}.{name}", f"a function named {name}()", rel, functions[name].lineno
                    )
                )
    # one another of its kind names, as include('orders.urls') does, comes after it: the site's URLs before an app's
    named = {
        e.name
        for e in found.values()
        for other in found.values()
        if other.why == e.why
        and other.file != e.file
        and re.search(rf"['\"]{re.escape(e.name.rsplit('.', 1)[0])}['\"]", project.files.get(other.file, ""))
    }
    return [e for e in found.values() if e.name not in named] + [e for e in found.values() if e.name in named]


def entry_in_files(project: Project, entry: str) -> EntryPoint | None:
    """
    The entry point as given, when its module (or, for a method, the module before its class) is a file here.
    """
    by_module = {module: rel for rel, module in project.modules.items()}
    for cut in (1, 2):
        module = entry.rsplit(".", cut)[0]
        if module in by_module and entry.count(".") >= cut:
            return EntryPoint(entry, "given", by_module[module], 0)
    return None


def functions_matching(project: Project, text: str) -> list[EntryPoint]:
    """
    Functions and methods whose name contains text ('save' finds repo.Orders.save), for a partly typed entry point.
    """
    found = []
    needle = text.lower()
    for rel, tree in project.trees.items():
        module = project.modules[rel]
        for node in tree.body:
            members = (
                [(f"{module}.{node.name}", node)] if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else []
            )
            if isinstance(node, ast.ClassDef):
                members = [
                    (f"{module}.{node.name}.{m.name}", m)
                    for m in node.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
            found += [EntryPoint(name, "matches", rel, fn.lineno) for name, fn in members if needle in name.lower()]
    return found


def project_root(file: Path) -> Path:
    """
    The folder a file's project starts at: the nearest one above it with .git, pyproject.toml, setup.py or setup.cfg,
    else the file's own folder.
    """
    for folder in [file.parent, *file.parent.parents]:
        if any((folder / marker).exists() for marker in (".git", "pyproject.toml", "setup.py", "setup.cfg")):
            return folder
    return file.parent


def entries_in_file(project: Project, rel: str, function: str = "") -> list[EntryPoint]:
    """
    Where to start in one file, best first: the function named (function or Class.method), else what its
    `if __name__ == "__main__":` block calls, its platforms' entry points (Lambda handlers) and apps, functions named
    main, then every other function in it from the top.
    """
    module = project.modules.get(rel)
    tree = project.trees.get(rel)
    if module is None or tree is None:
        return []
    found = [e for e in entry_points(project) if e.file == rel]
    if function:
        known = next((e for e in found if e.name == f"{module}.{function}"), None)  # a handler keeps its platform
        return [EntryPoint(f"{module}.{function}", "named", rel, 0, known.platform if known else "")]
    named = {e.name for e in found}
    functions = _module_functions(tree)
    for name in _main_guard_calls(tree):
        if name in functions and f"{module}.{name}" not in named:
            found.insert(
                0, EntryPoint(f"{module}.{name}", 'runs under if __name__ == "__main__"', rel, functions[name].lineno)
            )
            named.add(f"{module}.{name}")
    for name, node in functions.items():
        if f"{module}.{name}" not in named:
            found.append(EntryPoint(f"{module}.{name}", "a function in this file", rel, node.lineno))
    for cls in [node for node in tree.body if isinstance(node, ast.ClassDef)]:
        methods = [m for m in cls.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for method in sorted(methods, key=lambda m: m.name.startswith("_")):
            found.append(
                EntryPoint(f"{module}.{cls.name}.{method.name}", f"a method of {cls.name}", rel, method.lineno)
            )
    return found
