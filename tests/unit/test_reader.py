"""
The reader: what it follows from an entry point, and what each name holds.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_node.analysis.graph import code_graph
from code_node.analysis.mapping import map_code
from code_node.project import entry_points, read_project

from support import HANDLER, PACKAGE, write


def test_a_lambda_handler_is_found_and_mapped(tmp_path: Path) -> None:
    project = read_project(write(tmp_path, {"app.py": HANDLER}))
    found = entry_points(project)
    assert [(e.name, e.platform) for e in found] == [("app.lambda_handler", "lambda")]
    cmap = map_code(project.files, "app.lambda_handler", libraries=project.libraries(), platform="lambda")
    assert [c.operation for c in cmap.aws] == ["GetObject"]
    assert [e.name for e in cmap.env] == ["HOOK"]
    assert {i.top: i.source for i in cmap.imports}["requests"] == "package"
    kinds = {n.kind for n in code_graph(cmap).nodes}
    assert {"event", "env", "handler", "function", "aws", "http"} <= kinds


def test_a_method_can_be_the_entry_point(tmp_path: Path) -> None:
    project = read_project(write(tmp_path, PACKAGE))
    cmap = map_code(project.files, "tool.store.Store.save")
    assert cmap.entry == "tool.store.Store.save"
    assert [f.name for f in cmap.functions] == ["tool.store.Store.save", "tool.store.Store._write"]


def test_modules_beside_the_entry_point_are_its_own_code(tmp_path: Path) -> None:
    # a Lambda function's folder: its handler imports the files beside it by their own names, though the folder is
    # also a package from the project's root
    project = read_project(
        write(
            tmp_path,
            {
                "src/app/__init__.py": "",
                "src/app/handler.py": "from helpers import load\n\n\ndef lambda_handler(event, context):\n    load()\n",
                "src/app/helpers.py": (
                    "import boto3\n\n\ndef load():\n    boto3.client('s3').get_object(Bucket='b', Key='k')\n"
                ),
            },
        )
    )
    cmap = map_code(project.files, "app.handler.lambda_handler", libraries=project.libraries())
    assert [f.name for f in cmap.functions] == ["app.handler.lambda_handler", "helpers.load"]
    assert [(c.service, c.operation) for c in cmap.aws] == [("s3", "GetObject")]
    assert next(i for i in cmap.imports if i.module == "helpers").source == "own"
    assert cmap.other_files == 0  # helpers.py is read, though it has two names


def test_cli_commands_are_followed_from_the_app(tmp_path: Path) -> None:
    source = (
        "import typer\n\napp = typer.Typer()\n\n\ndef helper():\n    pass\n\n\n@app.command()\n"
        'def sync_all():\n    helper()\n\n\n@app.command("show")\ndef display():\n    pass\n\n\n'
        "def main():\n    app()\n"
    )
    project = read_project(write(tmp_path, {"pyproject.toml": '[project.scripts]\nt = "cli:main"\n', "cli.py": source}))
    assert entry_points(project)[0].name == "cli.app"
    cmap = map_code(project.files, "cli.app")
    assert [(method, path) for method, path, _ in cmap.routes] == [("CLI", "sync-all"), ("CLI", "show")]
    assert "cli.helper" in {f.name for f in cmap.functions}


IDIOMS = """
class Base:
    def __init__(self, name):
        self.setup(name)

    def setup(self, name):
        open(name, "w").write("x")


class Repo(Base):
    def __init__(self, name):
        super().__init__(name)

    @property
    def size(self):
        return count()

    @size.setter
    def size(self, value):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        close()

    def save(self, item):
        pass


def count():
    pass


def close():
    pass


def main(item):
    repo = Repo("x")
    n = repo.size
    with Repo("y") as r:
        r.save(item)
"""


def test_super_properties_and_with_blocks_are_followed(tmp_path: Path) -> None:
    project = read_project(write(tmp_path, {"app.py": IDIOMS}))
    cmap = map_code(project.files, "app.main")
    reached = {f.name for f in cmap.functions}
    assert {"app.Base.__init__", "app.Base.setup"} <= reached  # through super().__init__()
    assert {"app.Repo.size", "app.count"} <= reached  # repo.size runs its getter, not its setter
    # r is what __enter__ returns, and __exit__ runs after the block
    assert {"app.Repo.__enter__", "app.Repo.save", "app.Repo.__exit__", "app.close"} <= reached
    with_step = next(s for s in cmap.steps[0].steps if s.kind == "with")
    assert [s.code for s in with_step.steps] == ["r.save(item)", "# leaving the with block: __exit__ runs"]
    assert [c.name for c in with_step.calls] == ["app.Repo.__init__", "app.Repo.__enter__"]


DISPATCH = """
import os
import boto3

s3 = boto3.client("s3")


def init():
    pass


def deploy(name):
    s3.put_object(Bucket=os.environ["BUCKET"], Key=f"apps/{name}", Body=b"")


def main(command, names):
    if command == "init":
        init()
    elif command == "deploy":
        for name in names:
            if not name:
                continue
            deploy(name)
"""


def test_what_names_hold_where_arguments_come_from_and_when_calls_run(tmp_path: Path) -> None:
    project = read_project(write(tmp_path, {"app.py": DISPATCH}))
    cmap = map_code(project.files, "app.main")
    steps = list(cmap.steps[0].walk())
    calls = {s.name: s.when for s in steps if s.kind == "def" and s.name != "app.main"}
    # the if around each call; `if not name: continue` makes the rest of the loop run only when name
    assert calls == {"app.init": ["command == 'init'"], "app.deploy": ["command == 'deploy'", "name"]}
    put = next(c for c in cmap.aws if c.operation == "PutObject")
    assert put.args == [("Bucket", "env BUCKET"), ("Key", "f'apps/{name}'"), ("Body", "b''")]
    line = next(s for s in steps if s.given)
    assert line.given[:2] == [("S3 PutObject Bucket", "env BUCKET"), ("S3 PutObject Key", "f'apps/{name}'")]
    holds = next(s for s in cmap.startup[0].walk() if s.holds)
    assert holds.holds == [("s3", "an S3 client")]
    graph = code_graph(cmap)
    deploy = next(n for n in graph.nodes if n.label == "deploy()")
    assert deploy.when == "command == 'deploy'"  # the graph says the if nearest around the call
    assert any(e.kind == "call" and e.when == deploy.when for e in graph.edges)
    assert "|\"when command == 'deploy'\"|" in graph.mermaid()


LATE = {
    "pkg/__init__.py": "",
    "pkg/app.py": (
        "from .util import *\nfrom . import store\ntry:\n    import ujson as json\nexcept ImportError:\n"
        "    import json\n\n\ndef main():\n    import boto3\n    helper()\n    _hidden()\n    store.save()\n"
        "    boto3.client('sqs').send_message(QueueUrl='q', MessageBody='x')\n    other()\n\n\n"
        "def other():\n    boto3.client('s3').get_object(Bucket='b', Key='k')\n"
    ),
    "pkg/util.py": "def helper():\n    pass\n\n\ndef _hidden():\n    pass\n",
    "pkg/store.py": "def save():\n    from pkg.db import put\n    put()\n",
    "pkg/db.py": "import boto3\n\n\ndef put():\n    boto3.client('dynamodb').put_item(TableName='t', Item={})\n",
}


def test_imports_inside_a_function_are_followed_and_said_to_run_late() -> None:
    cmap = map_code(LATE, "pkg.app.main")
    # store.save() imports pkg.db only when it runs, and its call to DynamoDB is still followed
    assert [f.name for f in cmap.functions] == [
        "pkg.app.main",
        "pkg.util.helper",
        "pkg.store.save",
        "pkg.db.put",
        "pkg.app.other",
    ]
    aws = {(c.service, c.operation): c for c in cmap.aws}
    assert aws[("dynamodb", "PutItem")].function == "pkg.db.put" and not aws[("dynamodb", "PutItem")].guessed
    assert not aws[("sqs", "SendMessage")].guessed  # boto3 is what main() imported
    # other() has no boto3 of its own: Python would raise NameError, so its call is only guessed from its shape
    assert aws[("s3", "GetObject")].guessed
    imports = {(i.module, i.file, i.line): i for i in cmap.imports}
    assert not imports[("boto3", "pkg/app.py", 10)].startup and not imports[("pkg.db", "pkg/store.py", 2)].startup
    assert imports[("boto3", "pkg/db.py", 1)].startup and imports[("pkg.util", "pkg/app.py", 1)].startup
    assert imports[("ujson", "pkg/app.py", 4)].optional and not imports[("json", "pkg/app.py", 6)].optional
    assert imports[("pkg.db", "pkg/store.py", 2)].source == "own"


def test_code_it_cant_follow_gives_a_partial_map_not_a_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_node.analysis import reader

    assert "doesn't name a module and a function" in map_code({"a.py": "def main():\n    pass\n"}, "main").note
    assert "No file matches the entry point nope.main" in map_code({"a.py": ""}, "nope.main").note
    # a module that doesn't parse is left out; what imports it is still read
    files = {"broken.py": "def oops(:\n", "ok.py": "import broken\n\n\ndef main():\n    broken.oops()\n"}
    cmap = map_code(files, "ok.main")
    assert [f.name for f in cmap.functions] == ["ok.main"] and not cmap.limited
    calls = []

    def fails(self, entry: str) -> None:
        calls.append(entry)
        raise ValueError("something new")

    monkeypatch.setattr(reader._CodeReader, "read", fails)
    cmap = map_code(LATE, "pkg.app.main")
    assert calls == ["pkg.app.main"]
    assert cmap.limited == "stopped partway, at code it couldn't follow (ValueError: something new)"


def test_the_entry_point_s_file_is_found_from_its_name() -> None:
    from code_node.analysis.mapping import entry_file

    names = ["src/tool/__init__.py", "src/tool/cli.py", "tests/tool/cli.py", "app.py"]
    assert entry_file("tool.cli.main", names) == ("src/tool/cli.py", "src/")  # the shortest path that matches
    assert entry_file("tool.cli.App.run", names) == ("src/tool/cli.py", "src/")  # a method
    assert entry_file("tool.main", names) == ("src/tool/__init__.py", "src/")  # a package's __init__
    assert entry_file("app.handler", names) == ("app.py", "")
    assert entry_file("missing.main", names) is None
