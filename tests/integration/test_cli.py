"""
The command end to end, through main(): what it prints and the page it saves.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from code_node.analysis.mapping import map_code
from code_node.cli import main
from code_node.project import read_project

from support import EXAMPLES, FAN, HANDLER, IMPORTED_FROM_SRC, PACKAGE, write


def test_the_page_opens_a_box_s_calls_with_javascript_and_works_without(tmp_path: Path) -> None:
    write(tmp_path / "code", {"app.py": FAN})
    out = tmp_path / "page.html"
    assert main([str(tmp_path / "code"), "--no-open", "-o", str(out), "--functions", "4"]) == 0
    page = out.read_text()
    # each graph a box's calls open is a template the script swaps in, with the path down to it
    assert '<div class="cgw" data-group="cn-graph0">' in page and page.count("<script>") == 1
    assert '<template id="cn-graph0-v1">' in page and '<a class="dr" href="#cn-graph0-v' in page
    assert '<a class="cgcb" href="#cn-graph0-main">← The whole graph</a>' in page
    assert '<template id="cn-graph0-all">' in page and '<a class="cgta oj" href="#cn-graph0-all"' in page
    # without JavaScript the links are hidden and the legend says where the rest are, as before
    assert 'class="kp kh nj"' in page and "the Step by step tab has them all" in page
    assert ".cnd .cgw:not(.js) :is(.oj,.dr),.cnd .cgw.js .nj{display:none}" in page
    # a function drawn in several graphs has one panel of code
    panels = re.findall(r'<aside class="cside" id="([^"]+)"', page)
    assert len(panels) == len(set(panels)) and len(panels) < 2 * len(re.findall(r'<a class="cl" href="#cn-code-', page))
    step = re.search(r'<aside class="cside" id="([^"]+)" aria-label="The code of step3\(\)"', page)
    assert step is not None and page.count(f'href="#{step.group(1)}"') > 1
    assert main([str(tmp_path / "code"), "--no-open", "-o", str(out), "--all"]) == 0
    assert '<div class="cgw">' in out.read_text() and "<template id=" not in out.read_text()  # nothing left out


def test_the_command_saves_a_page(tmp_path: Path, capsys) -> None:
    write(tmp_path / "code", {"app.py": HANDLER})
    out = tmp_path / "page.html"
    assert main([str(tmp_path / "code"), "--no-open", "-o", str(out)]) == 0
    page = out.read_text()
    assert "How app.lambda_handler works" in page and "<svg" in page
    # the page is its tabs, the entry point beside them, with no cards or findings
    assert '<div class="cnd"><div class="tabs">' in page and "<code>app.lambda_handler</code>" in page
    assert all(f">{tab}<small>" in page for tab in ("Graph", "Step by step"))
    assert (
        'class="cards"' not in page
        and 'class="fd"' not in page
        and ">Findings<" not in page
        and 'class="t"' not in page
    )
    assert main([str(tmp_path / "code"), "--mermaid"]) == 0
    assert "flowchart LR" in capsys.readouterr().out


def test_starting_from_a_file(tmp_path: Path, capsys) -> None:
    root = write(tmp_path / "repo", {**PACKAGE, ".git/HEAD": "ref: main\n"})
    out = tmp_path / "page.html"
    assert main([str(root / "src/tool/cli.py"), "--no-open", "-o", str(out)]) == 0
    assert "tool.cli.main: 3 functions" in capsys.readouterr().out
    assert main([f"{root / 'src/tool/store.py'}:Store.save", "--no-open", "-o", str(out)]) == 0
    assert "tool.store.Store.save: 2 functions" in capsys.readouterr().out
    assert main([str(root), "-e", str(root / "src/tool/store.py"), "--no-open", "-o", str(out)]) == 0
    assert "tool.store.Store.save" in capsys.readouterr().out


def test_the_command_lists_its_plugins(capsys) -> None:
    assert main(["--plugins"]) == 0
    out = capsys.readouterr().out
    assert all(re.search(row, out) for row in (r"lambda +AWS Lambda", r"redis +Redis +redis", r"sam +AWS SAM"))


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("pyproject.toml", '[tool.pyright]\nextraPaths = ["src"]\n'),
        ("pyproject.toml", '[tool.pytest.ini_options]\npythonpath = "src"\n'),
        ("pyproject.toml", '[tool.mypy]\nmypy_path = "src"\n'),
        ("pyproject.toml", '[tool.setuptools.packages.find]\nwhere = ["src"]\n'),
        ("pyproject.toml", '[tool.setuptools.package-dir]\n"" = "src"\n'),
        ("pyproject.toml", '[tool.poetry]\npackages = [{ include = "common", from = "src" }]\n'),
        ("pyproject.toml", '[[tool.poetry.packages]]\ninclude = "common"\nfrom = "src"\n'),
        ("pyrightconfig.json", '{"extraPaths": ["./src"]}'),
        (".vscode/settings.json", '{\n  // Pylance\n  "python.analysis.extraPaths": ["${workspaceFolder}/src"],\n}\n'),
    ],
)
def test_imports_from_a_folder_the_project_puts_on_the_path(tmp_path: Path, name: str, text: str, capsys) -> None:
    root = write(tmp_path / "repo", {**IMPORTED_FROM_SRC, name: text, ".git/HEAD": "ref: main\n"})
    project = read_project(root)
    assert project.paths == ["src/"] and "common" not in project.libraries()
    out = tmp_path / "page.html"
    assert main([str(root / "src/handlers/orders/app.py:handler"), "--no-open", "-o", str(out)]) == 0
    assert "app.handler: 2 functions, 1 AWS calls" in capsys.readouterr().out


def test_imports_from_a_folder_given_with_path(tmp_path: Path, capsys) -> None:
    root = write(tmp_path / "repo", {**IMPORTED_FROM_SRC, ".git/HEAD": "ref: main\n"})
    out = tmp_path / "page.html"
    file = str(root / "src/handlers/orders/app.py:handler")
    assert main([file, "--no-open", "-o", str(out)]) == 0
    assert "app.handler: 1 functions, 0 AWS calls" in capsys.readouterr().out  # common.db read as a library
    assert main([file, "--path", str(root / "src"), "--no-open", "-o", str(out)]) == 0
    assert "app.handler: 2 functions, 1 AWS calls" in capsys.readouterr().out
    assert main([file, "--path", str(tmp_path), "--no-open", "-o", str(out)]) == 2
    assert "isn't a folder in" in capsys.readouterr().err
    cmap = map_code(
        {path: text for path, text in IMPORTED_FROM_SRC.items()},
        "app.handler",
        file="src/handlers/orders/app.py",
        paths=["src/"],
    )
    assert {f.name for f in cmap.functions} >= {"app.handler", "common.db.save"}


def test_the_command_lists_entry_points_and_says_what_s_wrong(tmp_path: Path, capsys) -> None:
    root = write(tmp_path / "code", {"app.py": HANDLER})
    assert main([str(root), "--list"]) == 0
    assert "app.lambda_handler" in capsys.readouterr().out
    assert not list(root.glob("*.html"))  # --list stops before drawing
    assert main([str(tmp_path / "missing"), "--no-open"]) == 2
    assert "isn't a folder or a .py file" in capsys.readouterr().err
    out = tmp_path / "page.html"
    assert main([str(root), "-e", "nope.nothing", "--no-open", "-o", str(out)]) == 0  # said, and a page that says so
    assert "No file matches the entry point nope.nothing" in capsys.readouterr().out and out.exists()


# Each line would leave a file behind (or stop the process) if anything ran it
RUNS_IF_IMPORTED = {
    "app.py": (
        "import os\nimport subprocess\nimport sys\n\nopen('ran-at-import', 'w').write('x')\n"
        "os.system('touch ran-os-system')\n\n\ndef lambda_handler(event, context):\n"
        "    open('ran-handler', 'w').write('x')\n    subprocess.run(['touch', 'ran-subprocess'])\n    helper.go()\n"
        "    sys.exit(3)\n\n\nimport helper\n"
    ),
    "helper.py": "open('ran-helper', 'w').write('x')\n\n\ndef go():\n    raise SystemExit(4)\n",
    "setup.py": "open('ran-setup', 'w').write('x')\n",
    "conftest.py": "open('ran-conftest', 'w').write('x')\n",
}


def test_the_code_it_reads_is_never_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = write(tmp_path / "code", RUNS_IF_IMPORTED)
    monkeypatch.chdir(root)  # where the code's relative paths would land
    out = tmp_path / "page.html"
    assert main([str(root), "--no-open", "-o", str(out)]) == 0
    done = subprocess.run(
        [sys.executable, "-m", "code_node", str(root), "--no-open", "-o", str(out)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    assert sorted(p.name for p in root.iterdir()) == sorted(RUNS_IF_IMPORTED)  # nothing it would have made
    assert "app.helper" not in sys.modules and "helper" not in sys.modules
    page = out.read_text()
    assert "How app.lambda_handler works" in page and "go()" in page  # read, and followed into helper.py


def test_code_that_doesn_t_parse_still_gives_a_page(tmp_path: Path, capsys) -> None:
    root = write(
        tmp_path / "code",
        {
            "app.py": HANDLER.replace("import requests", "import requests\nimport broken"),
            "broken.py": "def oops(:\n",
            "binary.py": "\x00\x01not python",
        },
    )
    out = tmp_path / "page.html"
    assert main([str(root), "--no-open", "-o", str(out)]) == 0
    assert "Traceback" not in capsys.readouterr().err
    assert "How app.lambda_handler works" in out.read_text()


def test_the_command_runs_as_its_own_process(tmp_path: Path) -> None:
    """
    `python -m code_node` as a user runs it, in a process of its own: no state shared with the tests.
    """
    out = tmp_path / "page.html"
    env = {**os.environ, "NO_COLOR": "1", "XDG_CACHE_HOME": str(tmp_path / "cache")}
    done = subprocess.run(
        [sys.executable, "-m", "code_node", str(EXAMPLES / "orders-service"), "--no-open", "-o", str(out)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    assert "orders.handler.lambda_handler" in done.stdout and "Saved" in done.stdout
    assert (
        out.read_text().startswith("<!doctype html>") and "How orders.handler.lambda_handler works" in out.read_text()
    )
    # without -o it saves to the cache folder
    done = subprocess.run(
        [sys.executable, "-m", "code_node", str(EXAMPLES / "orders-service"), "--no-open"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    assert [p.suffix for p in (tmp_path / "cache" / "code-node").iterdir()] == [".html"]
    helped = subprocess.run([sys.executable, "-m", "code_node", "--help"], capture_output=True, text=True, timeout=60)
    assert helped.returncode == 0 and "--serve" in helped.stdout
    wrong = subprocess.run(
        [sys.executable, "-m", "code_node", "--depth", "lots"], capture_output=True, text=True, timeout=60
    )
    assert wrong.returncode == 2 and "invalid int value" in wrong.stderr
