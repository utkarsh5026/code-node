"""
code-node end to end on small folders written into tmp_path: entry points found, the map, the graph and the page.
"""

from __future__ import annotations

import os
from pathlib import Path

from code_node.analysis.graph import code_graph
from code_node.analysis.mapping import map_code
from code_node.cli import main
from code_node.project import entry_points, read_project
from code_node.report.style import render_page
from code_node.report.walk import _Walk, walk_stops

HANDLER = '''
import os
import boto3
import requests

s3 = boto3.client("s3")


def load(bucket, key):
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def lambda_handler(event, context):
    for record in event["Records"]:
        load(record["s3"]["bucket"]["name"], record["s3"]["object"]["key"])
    requests.post(os.environ["HOOK"], json={})
'''

PACKAGE = {
    "pyproject.toml": '[project]\nname = "tool"\n[project.scripts]\ntool = "tool.cli:main"\n',
    "src/tool/__init__.py": "",
    "src/tool/cli.py": "from .store import Store\n\n\ndef main():\n    Store().save('x')\n",
    "src/tool/store.py": ("class Store:\n    def save(self, item):\n        self._write(item)\n\n"
                          "    def _write(self, item):\n        open('out.txt', 'w').write(item)\n"),
    "tests/test_cli.py": "def main():\n    pass\n",
}


def write(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


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


def test_a_console_script_in_a_src_layout_follows_methods(tmp_path: Path) -> None:
    project = read_project(write(tmp_path, PACKAGE))
    found = entry_points(project)
    assert found[0].name == "tool.cli.main"
    assert all("tests/" not in e.file for e in found)
    cmap = map_code(project.files, found[0].name, file=found[0].file)
    assert [f.name for f in cmap.functions] == ["tool.cli.main", "tool.store.Store.save", "tool.store.Store._write"]
    assert not any(n.kind == "event" for n in code_graph(cmap).nodes)


def test_a_method_can_be_the_entry_point(tmp_path: Path) -> None:
    project = read_project(write(tmp_path, PACKAGE))
    cmap = map_code(project.files, "tool.store.Store.save")
    assert cmap.entry == "tool.store.Store.save"
    assert [f.name for f in cmap.functions] == ["tool.store.Store.save", "tool.store.Store._write"]


def test_graph_limits_and_all(tmp_path: Path) -> None:
    chain = "\n".join(f"def f{i}():\n    f{i + 1}()\n" for i in range(12)) + "\ndef f12():\n    pass\n"
    project = read_project(write(tmp_path, {"deep.py": chain}))
    cmap = map_code(project.files, "deep.f0")
    assert code_graph(cmap).hidden > 0
    assert code_graph(cmap, max_functions=100, max_depth=100).hidden == 0


def test_the_command_saves_a_page(tmp_path: Path, capsys) -> None:
    write(tmp_path / "code", {"app.py": HANDLER})
    out = tmp_path / "page.html"
    assert main([str(tmp_path / "code"), "--no-open", "-o", str(out)]) == 0
    page = out.read_text()
    assert "How app.lambda_handler works" in page and "<svg" in page
    # the page is its tabs, the entry point beside them, with no cards or findings
    assert '<div class="cnd"><div class="tabs">' in page and '<code>app.lambda_handler</code>' in page
    assert all(f">{tab}<small>" in page for tab in ("Graph", "Step by step"))
    assert 'class="cards"' not in page and 'class="fd"' not in page and ">Findings<" not in page and 'class="t"' not in page
    assert main([str(tmp_path / "code"), "--mermaid"]) == 0
    assert "flowchart LR" in capsys.readouterr().out


def test_clicking_a_box_shows_its_code(tmp_path: Path) -> None:
    project = read_project(write(tmp_path / "code", {"app.py": HANDLER}))
    cmap = map_code(project.files, "app.lambda_handler", libraries=project.libraries(), platform="lambda")
    graph = code_graph(cmap)
    load = next(n for n in graph.nodes if n.label == "load()")
    assert [(s.file, s.start, s.end, s.lit) for s in load.code] == [("app.py", 9, 10, [10])]
    s3 = next(n for n in graph.nodes if n.kind == "aws")
    assert [(s.start, s.end, s.lit) for s in s3.code] == [(9, 10, [10])]  # kept within load()
    out = tmp_path / "page.html"
    assert main([str(tmp_path / "code"), "--no-open", "-o", str(out)]) == 0
    page = out.read_text()
    assert f'<a class="cl" href="#cn-code-{load.id}"' in page and f'id="cn-code-{load.id}"' in page
    assert '<span class="sl lit"><span class="sn">10</span>' in page
    assert "<script" not in page


def test_the_steps_are_walked_in_the_order_the_code_runs(tmp_path: Path) -> None:
    project = read_project(write(tmp_path / "code", {"app.py": HANDLER}))
    cmap = map_code(project.files, "app.lambda_handler", libraries=project.libraries(), platform="lambda")
    walk = _Walk(cmap.startup, cmap.steps, functions=cmap.functions, sources=project.files)
    assert [(line, stack) for line, _, stack in walk_stops(walk)] == [
        (6, ["app.py, imported"]),  # s3 = boto3.client("s3"), when it's imported
        (13, ["lambda_handler()"]),
        (14, ["lambda_handler()"]),  # for record in event["Records"]:
        (15, ["lambda_handler()"]),  # load(...)
        (9, ["lambda_handler()", "load()"]),  # into load()
        (10, ["lambda_handler()", "load()"]),
        (16, ["lambda_handler()"]),  # back out: requests.post(...)
    ]
    html = render_page([walk], "walk")
    assert 'id="cw0" checked' in html and html.count('name="cnd-walk"') == 7
    assert '<label class="wbt" for="cw6" title="Run what this line calls without going in' in html  # Skip call
    assert ('<label class="wbt" for="cw6" title="Run the rest of load() and go back to where it was called">'
            "Finish <code>load()</code>") in html  # from inside load()
    assert '<div class="whead">Makes an S3 client</div>' in html  # each step said in plain words
    assert '<span class="wtx">Goes through each <code>record</code> in <code>event[&#x27;Records&#x27;]</code>' in html
    assert '<label class="sl" for="cw5"><span class="sn">10</span>' in html  # load()'s line 10 jumps to its step
    assert ".cnd #cw5:checked~.wf2{--k:1}" in html  # and lights the second line of load()
    out = tmp_path / "page.html"
    assert main([str(tmp_path / "code"), "--no-open", "-o", str(out)]) == 0
    page = out.read_text()
    assert '<input type="radio" class="tr" name="cnd-tab0" id="cnd-tab0-0" checked>' in page
    assert "Step by step<small>7 steps</small>" in page and "<script" not in page


def test_starting_from_a_file(tmp_path: Path, capsys) -> None:
    root = write(tmp_path / "repo", {**PACKAGE, ".git/HEAD": "ref: main\n"})
    out = tmp_path / "page.html"
    assert main([str(root / "src/tool/cli.py"), "--no-open", "-o", str(out)]) == 0
    assert "tool.cli.main: 3 functions" in capsys.readouterr().out
    assert main([f"{root / 'src/tool/store.py'}:Store.save", "--no-open", "-o", str(out)]) == 0
    assert "tool.store.Store.save: 2 functions" in capsys.readouterr().out
    assert main([str(root), "-e", str(root / "src/tool/store.py"), "--no-open", "-o", str(out)]) == 0
    assert "tool.store.Store.save" in capsys.readouterr().out


def test_cli_commands_are_followed_from_the_app(tmp_path: Path) -> None:
    source = ('import typer\n\napp = typer.Typer()\n\n\ndef helper():\n    pass\n\n\n@app.command()\n'
              'def sync_all():\n    helper()\n\n\n@app.command("show")\ndef display():\n    pass\n\n\n'
              'def main():\n    app()\n')
    project = read_project(write(tmp_path, {"pyproject.toml": '[project.scripts]\nt = "cli:main"\n',
                                            "cli.py": source}))
    assert entry_points(project)[0].name == "cli.app"
    cmap = map_code(project.files, "cli.app")
    assert [(method, path) for method, path, _ in cmap.routes] == [("CLI", "sync-all"), ("CLI", "show")]
    assert "cli.helper" in {f.name for f in cmap.functions}


def test_the_live_server_redraws_when_the_code_changes(tmp_path: Path, monkeypatch) -> None:
    import threading
    import urllib.request

    from code_node import serve as servemod
    from code_node.pages import PageOptions
    from code_node.project import EntryPoint

    monkeypatch.setattr(servemod, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(servemod, "SETTLE_SECONDS", 0.05)
    root = write(tmp_path, {"app.py": HANDLER})
    live = servemod.LivePage(root, EntryPoint("app.lambda_handler", "", "app.py", 0, "lambda"), PageOptions(),
                             log=lambda line: None)
    live.build()
    assert live.version == 1 and "EventSource" in live.page and "GetObject" in live.page
    server = servemod.ThreadingHTTPServer(("127.0.0.1", 0), servemod._handler(live))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=live.watch, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        assert "GetObject" in urllib.request.urlopen(url).read().decode()
        (root / "app.py").write_text(HANDLER.replace("s3.get_object", "s3.head_object"))
        assert live.wait_for_change(1, timeout=5) == 2
        page = urllib.request.urlopen(url).read().decode()
        assert "HeadObject" in page  # its IAM permission is still s3:GetObject
        assert f"<title>{root.name} · " in page and 'rel="icon"' in page
        icon = urllib.request.urlopen(url + "/favicon.ico")
        assert icon.headers["Content-Type"] == "image/svg+xml" and b"<svg" in icon.read()
    finally:
        live.stop()
        server.shutdown()
        server.server_close()


def test_a_second_server_takes_the_next_free_port() -> None:
    from code_node import serve as servemod

    first = servemod.listen(servemod.BaseHTTPRequestHandler)
    try:
        second = servemod.listen(servemod.BaseHTTPRequestHandler)
        try:
            assert second.server_address[1] != first.server_address[1]
        finally:
            second.server_close()
    finally:
        first.server_close()


def test_a_broken_build_shows_in_the_page(tmp_path: Path, monkeypatch) -> None:
    from code_node import serve as servemod
    from code_node.pages import PageOptions
    from code_node.project import EntryPoint

    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(servemod, "make_page", broken)
    live = servemod.LivePage(tmp_path, EntryPoint("app.main", "", "app.py", 0), PageOptions(), log=lambda line: None)
    live.build()
    assert "Couldn't draw app.main" in live.page and "RuntimeError: boom" in live.page


def test_plain_python_has_no_lambda_checks_until_asked(tmp_path: Path) -> None:
    source = 'import requests\n\n\ndef main():\n    open("out.txt", "w")\n    requests.get("https://example.com")\n'
    project = read_project(write(tmp_path / "code", {"app.py": source}))
    plain = map_code(project.files, "app.main", libraries=project.libraries())
    as_lambda = map_code(project.files, "app.main", libraries=project.libraries(), platform="lambda")
    from code_node.analysis.findings import code_map_findings

    said = " ".join(message for _, message in code_map_findings(plain))
    assert "Lambda" not in said and "/tmp" not in said and "hangs" in said
    assert not any(n.kind == "event" for n in code_graph(plain).nodes)
    said = " ".join(message for _, message in code_map_findings(as_lambda))
    assert "Lambda passes two" in said and "outside /tmp" in said
    assert any(n.kind == "event" for n in code_graph(as_lambda).nodes)
    out = tmp_path / "page.html"
    assert main([str(tmp_path / "code"), "-e", "app.main", "--platform", "lambda", "--no-open", "-o", str(out)]) == 0
    assert "Lambda passes two" in out.read_text()


def test_a_platform_plugin_finds_its_entry_points_and_adds_findings(tmp_path: Path, monkeypatch) -> None:
    import ast

    from code_node import platforms as platformsmod
    from code_node.platforms import Platform

    class Worker(Platform):
        name = "worker"
        title = "Job runner"
        inputs = ("event",)
        input_name = "the job"

        def find_entries(self, module: str, tree: ast.Module) -> list[tuple[str, int, str]]:
            return [(n.name, n.lineno, "a job") for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name.startswith("job_")]

        def findings(self, cmap) -> list[tuple[str, str]]:
            return [("info", f"{len(cmap.event)} fields of the job are read.")]

    platformsmod.platforms()  # the built-in ones first
    monkeypatch.setitem(platformsmod._platforms, "worker", Worker())
    project = read_project(write(tmp_path, {"jobs.py": "def job_resize(job):\n    return job['size']\n"}))
    found = entry_points(project)
    assert [(e.name, e.platform) for e in found] == [("jobs.job_resize", "worker")]
    cmap = map_code(project.files, found[0].name, platform=found[0].platform)
    assert [f.label for f in cmap.event] == ["size"]
    from code_node.analysis.findings import _code_summary, code_map_findings

    assert ("info", "1 fields of the job are read.") in code_map_findings(cmap)
    assert "It reads size from the job." in _code_summary(cmap)


SNAPSHOT = Path(__file__).parent / "snapshots" / "orders-service.txt"


def test_the_example_page_matches_its_snapshot(monkeypatch) -> None:
    """
    The example's page as text, against tests/snapshots/orders-service.txt, so a change to what the page says shows
    as a readable diff. UPDATE_SNAPSHOTS=1 uv run pytest writes it anew.
    """
    from code_node.kit.render import _render_text
    from code_node.pages import PageOptions, map_entry
    from code_node.report.build import page_blocks

    root = Path(__file__).parent.parent / "examples" / "orders-service"
    entry = entry_points(read_project(root))[0]
    cmap, project = map_entry(root, entry, PageOptions())
    text = _render_text(page_blocks(cmap, project=root.name, max_functions=24, max_depth=5,
                                    sources=project.files), 100) + "\n"
    if os.environ.get("UPDATE_SNAPSHOTS"):
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(text)
    # code is shown as ast.unparse writes it, whose quotes differ between Pythons (f'{a['b']}' from 3.12 only)
    assert text.replace("'", '"') == SNAPSHOT.read_text().replace("'", '"')


ENGINE = '''
def main():
    tidy()
    note()
    run()


def tidy():
    pass


def note():
    pass


def run():
    work()


def work():
''' + "".join(f"    step{i} = {i}\n" for i in range(30))


def test_the_graph_draws_the_functions_that_do_the_work(tmp_path: Path) -> None:
    project = read_project(write(tmp_path, {"app.py": ENGINE}))
    cmap = map_code(project.files, "app.main")
    graph = code_graph(cmap, max_functions=3)
    assert [n.label for n in graph.nodes if n.kind in ("handler", "function")] == ["main()", "run()", "work()"]
    main_box = next(n for n in graph.nodes if n.label == "main()")
    assert main_box.more == ["tidy()", "note()"]  # said in its box, rather than looking like it does nothing


def test_arrows_from_one_box_run_together_and_the_graph_zooms(tmp_path: Path) -> None:
    from code_node.report.graph import _g_cards, _graph_layout

    chain = ("import os\n\n\ndef main():\n    a()\n\n\ndef a():\n    b()\n\n\ndef b():\n    os.environ['B']\n    c()\n\n\n"
             "def c():\n    os.environ['C']\n")
    project = read_project(write(tmp_path / "code", {"app.py": chain}))
    graph = code_graph(map_code(project.files, "app.main"))
    _, routes, *_ = _graph_layout(graph, _g_cards(graph))
    env = [routes[i] for i, e in enumerate(graph.edges) if e.kind == "env"]
    assert len(env) == 2 and env[0][:2] == env[1][:2]  # one line through the columns both cross, then they part
    out = tmp_path / "page.html"
    assert main([str(tmp_path / "code"), "--no-open", "-o", str(out)]) == 0
    page = out.read_text()
    assert 'class="cgs cgz-auto" name="cn-graph0-zoom" id="cn-graph0-auto" checked' in page
    assert 'class="cgs cgfs" id="cn-graph0-full"' in page and ">Full screen<" in page and "<script" not in page


def test_line_links_open_the_editor(tmp_path: Path) -> None:
    from code_node.report.editor import editor_link, open_at

    link = editor_link("vscode", "/home/me/my code")
    assert open_at(link, "app/main.py", 12) == "vscode://file/home/me/my%20code/app/main.py:12"
    assert open_at(editor_link("cursor", "/home/me/code", wsl="Ubuntu"), "a.py", 3) == (
        "cursor://vscode-remote/wsl+Ubuntu/home/me/code/a.py:3")
    assert open_at(editor_link("vscode", "C:\\code"), "a.py", 1) == "vscode://file/C:/code/a.py:1"
    assert editor_link("none", "/home/me/code") == ""
    write(tmp_path / "code", {"app.py": HANDLER})
    out = tmp_path / "page.html"
    assert main([str(tmp_path / "code"), "--no-open", "-o", str(out)]) == 0
    assert f'href="vscode://file{(tmp_path / "code").as_posix()}/app.py:' in out.read_text()
    assert main([str(tmp_path / "code"), "--no-open", "-o", str(out), "--editor", "none"]) == 0
    assert "vscode://" not in out.read_text()


IDIOMS = '''
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
'''


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


def test_syntax_warnings_stay_out_of_the_terminal(tmp_path: Path) -> None:
    import warnings

    code = 'import re\n\n\ndef main():\n    return re.match("\\d+", "1")\n'  # '\\d' in a plain string: a SyntaxWarning
    project = read_project(write(tmp_path, {"app.py": code}))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert "app.py" in project.trees
        map_code(project.files, "app.main")
    assert not caught


def test_console_scripts_come_from_every_pyproject(tmp_path: Path) -> None:
    project = read_project(write(tmp_path, {
        "pyproject.toml": '[project]\nname = "workspace"\n',
        "libs/cli/pyproject.toml": '[project]\nname = "tool"\n[project.scripts]\ntool = "tool.main:run"\n',
        "libs/cli/tool/__init__.py": "",
        "libs/cli/tool/main.py": "def run():\n    pass\n",
        "scripts/release.py": "def main():\n    pass\n\n\nif __name__ == '__main__':\n    main()\n",
    }))
    assert project.configs == ["pyproject.toml", "libs/cli/pyproject.toml"]
    first = entry_points(project)[0]
    assert (first.name, first.why) == ("tool.main.run", "the tool command in libs/cli/pyproject.toml")


DISPATCH = '''
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
'''


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
    assert '|"when command == \'deploy\'"|' in graph.mermaid()


STORES = '''
import json
import os
import subprocess

import pymongo
import redis
import sqlite3
from anthropic import Anthropic

cache = redis.Redis(host="cache")
mongo = pymongo.MongoClient(os.environ["MONGO_URL"])
orders = mongo.shop["orders"]
claude = Anthropic(timeout=20)
LOOKUP = "SELECT name FROM users WHERE id = ?"


def handler(event, context):
    body = json.loads(event["body"])
    user = body["user"]
    db = sqlite3.connect("/tmp/app.db")
    name = db.execute(LOOKUP, (user,)).fetchone()
    query = "DELETE FROM sessions WHERE user = '" + user + "'"
    db.execute(query)
    for key in cache.keys("session:*"):
        cache.delete(key)
    orders.insert_one({"user": user})
    found = mongo.get_database("shop").users.find_one({"id": user})
    claude.messages.create(model="claude-sonnet-5-5", max_tokens=200, messages=[])
    subprocess.run(f"echo {body['note']}", shell=True)
    return name, found
'''


def test_library_plugins_follow_their_clients_and_flag_what_the_input_reaches(tmp_path: Path) -> None:
    from code_node.analysis.findings import code_map_findings

    project = read_project(write(tmp_path, {"app.py": STORES}))
    cmap = map_code(project.files, "app.handler", libraries=project.libraries(), platform="lambda")
    calls = {(c.service, c.operation, c.target): c for c in cmap.library_calls}
    assert set(calls) == {
        ("SQLite", "SELECT", "users"), ("SQLite", "DELETE", "sessions"), ("Redis", "KEYS", "session:*"),
        ("Redis", "DELETE", "key"), ("MongoDB", "insert_one", "orders"), ("MongoDB", "find_one", "users"),
        ("Anthropic", "messages.create", "claude-sonnet-5-5")}
    # the user id went from the event, through a name and a + on text, into the SQL: flagged where it's run
    assert calls[("SQLite", "DELETE", "sessions")].flag == "SQL injection"
    assert not calls[("SQLite", "SELECT", "users")].flag  # a parameter, in a constant statement
    assert calls[("Redis", "KEYS", "session:*")].flag == "KEYS blocks Redis"
    assert calls[("Redis", "DELETE", "key")].loop == "for key in cache.keys('session:*'):"
    assert cmap.plugins == ["SQL", "Redis", "MongoDB", "OpenAI and Anthropic"]
    said = " ".join(message for _, message in code_map_findings(cmap))
    assert "puts event body (JSON).user into the SQL text itself" in said
    assert "shell command with event body (JSON).note in it" in said
    assert "The Redis client made at app.py line 11 has no timeout" in said  # Anthropic's has one
    assert "a new SQLite connection" not in said  # a file on disk: nothing to reuse
    graph = code_graph(cmap)
    boxes = {n.label: n for n in graph.nodes if n.kind == "service"}
    assert set(boxes) == {"SQLite", "Redis", "MongoDB", "Anthropic"}
    assert boxes["SQLite"].flags == {"DELETE sessions": "SQL injection"} and boxes["SQLite"].tone == "warn"
    assert boxes["Anthropic"].icon == "spark" and boxes["Anthropic"].sub == "runs"
    step = next(s for s in cmap.steps[0].walk() if s.code.startswith("query ="))
    assert step.holds == [("query", "text built from event body (JSON).user")]


def test_a_library_plugin_from_another_package(tmp_path: Path, monkeypatch) -> None:
    from code_node import libraries as librariesmod
    from code_node.libraries import Handle, Library, Use

    class Kafka(Library):
        name = "kafka"
        title = "Kafka"
        modules = ("kafka",)
        icon = "queue"

        def make(self, name, call):
            return Handle("producer", "Kafka", opens=True) if name == "kafka.KafkaProducer" else None

        def call(self, handle, method, call):
            return Use("send", "sends", call.shown(0, "topic")) if method == "send" else None

    librariesmod.libraries()
    monkeypatch.setitem(librariesmod._libraries, "kafka", Kafka())
    code = ("from kafka import KafkaProducer\n\nproducer = KafkaProducer()\n\n\n"
            "def main():\n    producer.send('orders', b'1')\n")
    project = read_project(write(tmp_path, {"app.py": code}))
    cmap = map_code(project.files, "app.main", libraries=project.libraries())
    assert [(c.service, c.operation, c.access, c.target) for c in cmap.library_calls] == [
        ("Kafka", "send", "sends", "orders")]
    box = next(n for n in code_graph(cmap).nodes if n.kind == "service")
    assert (box.label, box.icon, box.lines) == ("Kafka", "queue", ["send orders"])


SAM = {
    "template.yaml": '''
Transform: AWS::Serverless-2016-10-31
Globals:
  Function:
    Runtime: python3.13
    Environment:
      Variables:
        STAGE: prod
Resources:
  ResizeFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: images.resize.run
      Timeout: 20
      Layers:
        - !Ref PillowLayer
      Policies:
        - S3ReadPolicy:
            BucketName: !Ref Uploads
        - Statement:
            - Effect: Allow
              Action: sqs:SendMessage
              Resource: "*"
  Uploads:
    Type: AWS::S3::Bucket
''',
    "src/images/__init__.py": "",
    "src/images/resize.py": '''
import os
import boto3
import PIL

s3 = boto3.client("s3")


def run(event, context):
    s3.get_object(Bucket=os.environ["BUCKET"], Key="a")
    s3.put_object(Bucket=os.environ["STAGE"], Key="b", Body=b"")
    boto3.client("sqs").send_message(QueueUrl="q", MessageBody="done")
''',
}


def test_a_sam_template_names_the_entry_point_and_what_its_role_allows(tmp_path: Path) -> None:
    from code_node.analysis.findings import code_map_findings
    from code_node.pages import PageOptions, map_entry

    root = write(tmp_path, SAM)
    project = read_project(root)
    assert list(project.deploy_files) == ["template.yaml"]
    found = entry_points(project)
    # run() isn't named like a handler: the template is what says it is one
    assert [(e.name, e.why, e.platform) for e in found] == [
        ("images.resize.run", "ResizeFunction in template.yaml", "lambda")]
    cmap, _ = map_entry(root, found[0], PageOptions())
    fn = cmap.function
    assert (fn.name, fn.runtime, fn.timeout, fn.env_names, fn.layers) == (
        "ResizeFunction", "python3.13", 20, {"STAGE"}, ["PillowLayer"])
    assert {i.top: i.source for i in cmap.imports}["PIL"] == "package"
    said = " ".join(message for _, message in code_map_findings(cmap))
    assert "BUCKET isn't set on ResizeFunction" in said and "STAGE isn't" not in said
    assert ("ResizeFunction's role in template.yaml (it has S3ReadPolicy and an inline statement) doesn't allow "
            "s3:PutObject") in said
    assert "Add S3WritePolicy to ResizeFunction's Policies in template.yaml" in said
    s3 = next(n for n in code_graph(cmap).nodes if n.label == "S3")
    assert s3.flags == {"PutObject": "not allowed"} and s3.tone == "warn"
    assert next(n for n in code_graph(cmap).nodes if n.label == "SQS").tone == ""  # the inline statement allows it


def test_a_role_it_cant_read_leaves_permissions_unchecked(tmp_path: Path) -> None:
    from code_node.analysis.findings import code_map_findings
    from code_node.pages import PageOptions, map_entry

    files = dict(SAM)
    files["template.yaml"] = files["template.yaml"].replace(
        "      Policies:", "      Role: arn:aws:iam::123456789012:role/shared\n      Policies:")
    root = write(tmp_path, files)
    cmap, _ = map_entry(root, entry_points(read_project(root))[0], PageOptions())
    assert cmap.function.permissions is None
    assert "doesn't allow" not in " ".join(message for _, message in code_map_findings(cmap))


def test_serverless_yml_names_the_entry_point(tmp_path: Path) -> None:
    from code_node.analysis.findings import code_map_findings
    from code_node.pages import PageOptions, map_entry

    root = write(tmp_path, {
        "serverless.yml": '''
service: jobs
provider:
  name: aws
  runtime: python3.12
  environment:
    TABLE: jobs
  iam:
    role:
      statements:
        - Effect: Allow
          Action: [dynamodb:GetItem, dynamodb:Query]
          Resource: "*"
functions:
  sweep:
    handler: jobs/sweep.go
''',
        "jobs/__init__.py": "",
        "jobs/sweep.py": ('import os\nimport boto3\n\n\ndef go(event, context):\n'
                          '    boto3.resource("dynamodb").Table(os.environ["TABLE"]).delete_item(Key={})\n'),
    })
    found = entry_points(read_project(root))
    assert [(e.name, e.why) for e in found] == [("jobs.sweep.go", "sweep in serverless.yml")]
    cmap, _ = map_entry(root, found[0], PageOptions())
    assert (cmap.function.timeout, cmap.function.env_names) == (6, {"TABLE"})
    said = " ".join(message for _, message in code_map_findings(cmap))
    assert "sweep's role in serverless.yml" in said and "dynamodb:DeleteItem" in said
    assert "Add a statement that allows dynamodb:DeleteItem to provider.iam.role.statements" in said


def test_the_command_lists_its_plugins(capsys) -> None:
    assert main(["--plugins"]) == 0
    out = capsys.readouterr().out
    assert "lambda  AWS Lambda" in out and "redis    Redis  (redis)" in out and "sam         AWS SAM" in out


CART_SNAPSHOT = Path(__file__).parent / "snapshots" / "cart-service.txt"


def test_the_cart_example_matches_its_snapshot() -> None:
    """
    The cart example, which every kind of plugin reads (its SAM template, Redis, PostgreSQL, OpenAI and boto3 on
    Lambda): its page as text, then its findings, against tests/snapshots/cart-service.txt.
    UPDATE_SNAPSHOTS=1 uv run pytest writes it anew.
    """
    from code_node.analysis.findings import code_map_findings
    from code_node.kit.render import _render_text
    from code_node.pages import PageOptions, map_entry
    from code_node.report.build import page_blocks

    root = Path(__file__).parent.parent / "examples" / "cart-service"
    entry = entry_points(read_project(root))[0]
    cmap, project = map_entry(root, entry, PageOptions())
    text = _render_text(page_blocks(cmap, project=root.name, max_functions=24, max_depth=5,
                                    sources=project.files), 100)
    text += "\n\n-- Findings --\n" + "\n".join(f"{level}: {message}" for level, message in code_map_findings(cmap))
    text += "\n"
    if os.environ.get("UPDATE_SNAPSHOTS"):
        CART_SNAPSHOT.write_text(text)
    assert text.replace("'", '"') == CART_SNAPSHOT.read_text().replace("'", '"')


def test_services_show_their_real_logos(tmp_path: Path) -> None:
    from code_node.report.brands import logo, logo_names
    from code_node.report.graph import _g_logo

    assert all(logo(name) is not None for name in logo_names())  # logos/ has a .svg for each one brands.py names
    project = read_project(write(tmp_path, {"app.py": STORES}))
    graph = code_graph(map_code(project.files, "app.handler", libraries=project.libraries(), platform="lambda"))
    boxes = {n.label: n for n in graph.nodes}
    assert _g_logo(boxes["Redis"]) == logo("redis") and _g_logo(boxes["SQLite"]) == logo("sqlite")
    assert _g_logo(boxes["handler()"]) is None  # its own functions keep their line drawing
    page = render_page(page_blocks_for(project, "app.handler"), "x")
    assert page.count('<svg class="logo"') == 4  # SQLite, Redis, MongoDB, Anthropic
    assert 'id="cnl-sqlite-' in page  # each logo's gradient ids get its own prefix, so two logos never share one
    assert "fill=\"#181818\"" not in page  # Anthropic's black follows the text colour, for dark mode


def test_logos_come_in_two_sizes_as_favicons_do(tmp_path: Path) -> None:
    from code_node.report.brands import AWS_GLYPHS, fills, logo, logo_for, small_logo

    # AWS's detailed icons have a small mark for 16 to 32 px; other brands' logos are simple enough as they are
    assert all(small_logo(name) is not None for name in AWS_GLYPHS if logo(name) is not None and fills(logo(name)))
    assert small_logo("redis") is None and logo_for("redis", 16) == logo("redis")
    assert logo_for("aws-s3", 24) == small_logo("aws-s3") and logo_for("aws-s3", 64) == logo("aws-s3")
    project = read_project(write(tmp_path, {"app.py": HANDLER}))
    page = render_page(page_blocks_for(project, "app.lambda_handler"), "x")
    assert page.count('class="logo lgs"') == page.count('class="logo lgf"') == 1  # S3: both, the screen picks
    assert "@media (min-resolution:2dppx)" in page


def page_blocks_for(project, entry: str) -> list:
    from code_node.report.build import page_blocks

    cmap = map_code(project.files, entry, libraries=project.libraries(), platform="lambda")
    return page_blocks(cmap, project="x", max_functions=24, max_depth=5, sources=project.files)
