"""
code-node end to end on small folders written into tmp_path: entry points found, the map, the graph and the page.
"""

from __future__ import annotations

from pathlib import Path

from code_node.analysis.graph import code_graph
from code_node.analysis.mapping import map_code
from code_node.cli import main
from code_node.project import entry_points, read_project

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
    finally:
        live.stop()
        server.shutdown()
        server.server_close()


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
