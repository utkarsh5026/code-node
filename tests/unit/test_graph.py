"""
The graph: which boxes and arrows a map draws, and its limits.
"""

from __future__ import annotations

from pathlib import Path

from code_node.analysis.graph import code_graph, everything_graph, graph_views
from code_node.analysis.mapping import map_code
from code_node.project import read_project

from support import FAN, write


def test_graph_limits_and_all(tmp_path: Path) -> None:
    chain = "\n".join(f"def f{i}():\n    f{i + 1}()\n" for i in range(12)) + "\ndef f12():\n    pass\n"
    project = read_project(write(tmp_path, {"deep.py": chain}))
    cmap = map_code(project.files, "deep.f0")
    assert code_graph(cmap).hidden > 0
    assert code_graph(cmap, max_functions=100, max_depth=100).hidden == 0


def test_a_function_whose_calls_are_left_out_has_a_graph_of_its_own(tmp_path: Path) -> None:
    project = read_project(write(tmp_path, {"app.py": FAN}))
    cmap = map_code(project.files, "app.lambda_handler", platform="lambda")
    graph = code_graph(cmap, max_functions=4)
    route = next(n for n in graph.nodes if n.name == "app.route")
    assert route.more and graph.hidden and not graph.too_deep
    # from route(): every call it makes, though that's past max_functions, and nothing from above it
    opened = code_graph(cmap, max_functions=4, focus="app.route")
    names = {n.name for n in opened.nodes if n.kind in ("handler", "function")}
    assert {"app.route", *(f"app.step{i}" for i in range(8))} <= names and "app.lambda_handler" not in names
    assert next(n for n in opened.nodes if n.name == "app.route").kind == "handler"
    assert not any(n.kind in ("event", "start") for n in opened.nodes)
    assert [n.label for n in opened.nodes if n.kind == "aws"] == ["S3"]  # what's below it still reaches S3
    views = graph_views(cmap, graph, max_functions=4)
    assert views[0].name == "app.route" and views[0].path == ["app.lambda_handler", "app.route"]
    everything = everything_graph(cmap, graph)
    assert everything is not None and everything.hidden == 0


ENGINE = """
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
""" + "".join(f"    step{i} = {i}\n" for i in range(30))


def test_the_graph_draws_the_functions_that_do_the_work(tmp_path: Path) -> None:
    project = read_project(write(tmp_path, {"app.py": ENGINE}))
    cmap = map_code(project.files, "app.main")
    graph = code_graph(cmap, max_functions=3)
    # run() only passes on to work(): work() takes the box, joined to main() through it, and tidy() the one left
    assert [n.label for n in graph.nodes if n.kind in ("handler", "function")] == ["main()", "tidy()", "work()"]
    labels = {n.id: n.label for n in graph.nodes}
    via = [(labels[e.source], labels[e.target], e.label) for e in graph.edges if e.indirect]
    assert via == [("main()", "work()", "via run()")]
    main_box = next(n for n in graph.nodes if n.label == "main()")
    assert main_box.more == ["note()"]  # said in its box, rather than looking like it does nothing
    everything = code_graph(cmap)  # when they all fit, none is passed through
    assert "run()" in [n.label for n in everything.nodes] and not any(e.indirect for e in everything.edges)


def test_pointing_at_a_box_keeps_the_paths_through_it(tmp_path: Path) -> None:
    from code_node.report.graph import _g_lineage

    code = (
        "import os\nimport boto3\n\n\ndef main():\n    load()\n    other()\n\n\ndef load():\n    os.environ['A']\n"
        "    save()\n\n\ndef save():\n    boto3.client('s3').put_object(Bucket='b', Key='k', Body=b'')\n\n\n"
        "def other():\n    pass\n"
    )
    project = read_project(write(tmp_path / "code", {"app.py": code}))
    graph = code_graph(map_code(project.files, "app.main"))
    ids = {n.label: n.id for n in graph.nodes}
    boxes, arrows = _g_lineage(graph)
    # S3: every box on the way down to it, but not other(), nor the environment past the box that reads it
    assert boxes[ids["S3"]] == {ids["main()"], ids["load()"], ids["save()"]}
    assert ids["Environment"] in boxes[ids["load()"]] and ids["Environment"] not in boxes[ids["save()"]]
    on_path = {(e.source, e.target) for e, lit in zip(graph.edges, arrows) if ids["S3"] in lit}
    assert on_path == {(ids["main()"], ids["load()"]), (ids["load()"], ids["save()"]), (ids["save()"], ids["S3"])}


RUNS = """
import boto3

s3 = boto3.client("s3")


def main(items):
    setup()
    for x in items:
        if x:
            work(x)
        tidy(x)
    s3.put_object(Bucket="b", Key="k", Body=b"")
    s3.put_object(Bucket="b", Key="j", Body=b"")


def setup():
    pass


def work(x):
    pass


def tidy(x):
    pass
"""


def test_a_function_box_lists_what_it_does_in_the_order_it_runs(tmp_path: Path) -> None:
    from code_node.report.graph import _g_cards, _g_rows, _graph_layout

    project = read_project(write(tmp_path, {"app.py": RUNS}))
    graph = code_graph(map_code(project.files, "app.main"))
    box = next(n for n in graph.nodes if n.label == "main()")
    rows = [(s.text, s.depth, s.loop, s.when) for s in box.steps]
    assert rows == [
        ("setup()", 0, False, ""),
        ("work()", 2, True, "x"),  # in the loop, under its if
        ("tidy()", 1, True, ""),
        ("S3 PutObject (+1)", 0, False, ""),  # two in a row to one service, one row
    ]
    ids = {n.label: n.id for n in graph.nodes}
    assert [s.target for s in box.steps] == [ids["setup()"], ids["work()"], ids["tidy()"], ids["S3"]]
    cards = _g_cards(graph)
    boxes, *_ = _graph_layout(graph, cards)
    called = sorted(["setup()", "work()", "tidy()"], key=lambda label: boxes[ids[label]][1])
    assert called == ["setup()", "work()", "tidy()"]  # the boxes it calls, top to bottom in the order it calls them
    to_work = next(e for e in graph.edges if e.target == ids["work()"])
    assert _g_rows(cards[box.id], to_work) == [cards[box.id].rows[1]]  # its arrow leaves from its row
