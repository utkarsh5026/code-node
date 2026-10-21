"""
Reading a folder: its files, module names, import paths and entry points.
"""

from __future__ import annotations

from pathlib import Path

from code_node.analysis.graph import code_graph
from code_node.analysis.mapping import map_code
from code_node.project import entry_points, read_project

from support import IMPORTED_FROM_SRC, PACKAGE, write


def test_a_console_script_in_a_src_layout_follows_methods(tmp_path: Path) -> None:
    project = read_project(write(tmp_path, PACKAGE))
    found = entry_points(project)
    assert found[0].name == "tool.cli.main"
    assert all("tests/" not in e.file for e in found)
    cmap = map_code(project.files, found[0].name, file=found[0].file)
    assert [f.name for f in cmap.functions] == ["tool.cli.main", "tool.store.Store.save", "tool.store.Store._write"]
    assert not any(n.kind == "event" for n in code_graph(cmap).nodes)


def test_console_scripts_come_from_every_pyproject(tmp_path: Path) -> None:
    project = read_project(
        write(
            tmp_path,
            {
                "pyproject.toml": '[project]\nname = "workspace"\n',
                "libs/cli/pyproject.toml": '[project]\nname = "tool"\n[project.scripts]\ntool = "tool.main:run"\n',
                "libs/cli/tool/__init__.py": "",
                "libs/cli/tool/main.py": "def run():\n    pass\n",
                "scripts/release.py": "def main():\n    pass\n\n\nif __name__ == '__main__':\n    main()\n",
            },
        )
    )
    assert project.configs == ["pyproject.toml", "libs/cli/pyproject.toml"]
    first = entry_points(project)[0]
    assert (first.name, first.why) == ("tool.main.run", "the tool command in libs/cli/pyproject.toml")


def test_a_pyproject_in_a_subfolder_names_paths_from_there(tmp_path: Path) -> None:
    files = {f"services/orders/{name}": text for name, text in IMPORTED_FROM_SRC.items()}
    files["services/orders/pyproject.toml"] = '[tool.pyright]\nextraPaths = ["src", "../../missing"]\n'
    assert read_project(write(tmp_path, files)).paths == ["services/orders/src/"]


def test_pyproject_paths_without_tomllib(monkeypatch) -> None:
    from code_node.project import _pyproject_paths

    text = (
        '[project]\nname = "x"\n[tool.pyright]\nextraPaths = [\n  "src",\n  "lib",\n]\n'
        '[tool.mypy]\nmypy_path = "a:b"\n[tool.setuptools.package-dir]\n"" = "pkgs"\n'
        '[[tool.poetry.packages]]\ninclude = "app"\nfrom = "apps"\n'
    )
    expected = ["src", "lib", "a", "b", "pkgs", "apps"]
    assert _pyproject_paths(text) == expected
    monkeypatch.setitem(__import__("sys").modules, "tomllib", None)  # as on Python 3.10
    assert _pyproject_paths(text) == expected


def test_syntax_warnings_stay_out_of_the_terminal(tmp_path: Path) -> None:
    import warnings

    code = 'import re\n\n\ndef main():\n    return re.match("\\d+", "1")\n'  # '\\d' in a plain string: a SyntaxWarning
    project = read_project(write(tmp_path, {"app.py": code}))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert "app.py" in project.trees
        map_code(project.files, "app.main")
    assert not caught


TOOL = {
    "pyproject.toml": "",
    "pkg/__init__.py": "",
    "pkg/tool.py": (
        "def helper():\n    pass\n\n\ndef run():\n    helper()\n\n\nclass Orders:\n    def _load(self):\n"
        '        pass\n\n    def save(self):\n        pass\n\n\nif __name__ == "__main__":\n    run()\n'
    ),
    "pkg/sub/deep.py": "def x():\n    pass\n",
}


def test_where_to_start_in_one_file_best_first(tmp_path: Path) -> None:
    from code_node.project import entries_in_file

    project = read_project(write(tmp_path, TOOL))
    assert [(e.name, e.why) for e in entries_in_file(project, "pkg/tool.py")] == [
        ("pkg.tool.run", 'runs under if __name__ == "__main__"'),
        ("pkg.tool.helper", "a function in this file"),
        ("pkg.tool.Orders.save", "a method of Orders"),  # its public methods before its private ones
        ("pkg.tool.Orders._load", "a method of Orders"),
    ]
    assert [e.name for e in entries_in_file(project, "pkg/tool.py", "Orders.save")] == ["pkg.tool.Orders.save"]
    assert entries_in_file(project, "missing.py") == []


def test_a_partly_typed_name_and_a_file_s_project(tmp_path: Path) -> None:
    from code_node.project import entry_in_files, functions_matching, project_root

    root = write(tmp_path / "repo", TOOL)
    project = read_project(root)
    assert project.modules["pkg/tool.py"] == "pkg.tool"
    assert project.modules["pkg/sub/deep.py"] == "deep"  # pkg/sub has no __init__.py: Python finds it beside itself
    assert [e.name for e in functions_matching(project, "SAVE")] == ["pkg.tool.Orders.save"]
    found = entry_in_files(project, "pkg.tool.Orders.save")
    assert found is not None and (found.file, found.why) == ("pkg/tool.py", "given")
    assert project_root(root / "pkg/sub/deep.py") == root  # the pyproject.toml above it
    assert project_root(tmp_path / "loose" / "x.py") == tmp_path / "loose"
