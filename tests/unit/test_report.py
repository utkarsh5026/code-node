"""
Drawing: the page's boxes, code panels, the step-by-step walk, logos and editor links.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from code_node.analysis.graph import code_graph
from code_node.analysis.mapping import map_code
from code_node.cli import main
from code_node.project import read_project
from code_node.report.style import render_page
from code_node.report.walk import _Walk, walk_stops

from support import HANDLER, STORES, page_blocks_for, write


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
    # a click outside the panel closes it, as its × does; without JavaScript the × still does
    assert page.count("<script>") == 1 and 'location.hash = "cn-closed"' in page and 'href="#cn-closed"' in page


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
    assert (
        '<label class="wbt" for="cw6" title="Run the rest of load() and go back to where it was called">'
        "Finish <code>load()</code>"
    ) in html  # from inside load()
    assert '<div class="whead">Makes an S3 client</div>' in html  # each step said in plain words
    assert 'id="cx1"' in html and 'id="cx0"' not in html  # lambda_handler() folds; the import line has nothing under it
    assert "#cx1:checked~.wu1" in html and 'class="wil k-def wu1 wu2 wu3"' in html  # load(), inside its caller's fold
    assert '<span class="wtx">Goes through each <code>record</code> in <code>event[&#x27;Records&#x27;]</code>' in html
    assert '<label class="sl" for="cw5"><span class="sn">10</span>' in html  # load()'s line 10 jumps to its step
    assert ".cnd #cw5:checked~.wf2{--k:1}" in html  # and lights the second line of load()
    out = tmp_path / "page.html"
    assert main([str(tmp_path / "code"), "--no-open", "-o", str(out)]) == 0
    page = out.read_text()
    assert '<input type="radio" class="tr" name="cnd-tab0" id="cnd-tab0-0" checked>' in page
    assert "Step by step<small>7 steps</small>" in page and page.count("<script>") == 1


def test_arrows_from_one_box_run_together_and_the_graph_zooms(tmp_path: Path) -> None:
    from code_node.report.graph import _g_cards, _graph_layout

    chain = (
        "import os\n\n\ndef main():\n    a()\n\n\ndef a():\n    b()\n\n\ndef b():\n    os.environ['B']\n    c()\n\n\n"
        "def c():\n    os.environ['C']\n"
    )
    project = read_project(write(tmp_path / "code", {"app.py": chain}))
    graph = code_graph(map_code(project.files, "app.main"))
    _, routes, *_ = _graph_layout(graph, _g_cards(graph))
    env = [routes[i] for i, e in enumerate(graph.edges) if e.kind == "env"]
    assert len(env) == 2 and env[0][:2] == env[1][:2]  # one line through the columns both cross, then they part
    out = tmp_path / "page.html"
    assert main([str(tmp_path / "code"), "--no-open", "-o", str(out)]) == 0
    page = out.read_text()
    assert 'class="cgs cgz-auto" name="cn-graph0-zoom" id="cn-graph0-auto" checked' in page
    assert 'class="cgs cgfs" id="cn-graph0-full"' in page and ">Full screen<" in page and page.count("<script>") == 1
    # with JavaScript it pans and zooms like a canvas, and says so; without it, it scrolls
    assert (
        'box.addEventListener("wheel"' in page
        and 'class="cgtm pzo"' in page
        and 'class="zi"' in page
        and "Drag to move about" in page
    )
    assert ".cnd .cgw:not(.pz) .pzo{display:none}" in page


def test_a_box_says_what_it_is_in_a_card_on_hover(tmp_path: Path) -> None:
    write(tmp_path / "code", {"app.py": HANDLER})
    out = tmp_path / "page.html"
    assert main([str(tmp_path / "code"), "--no-open", "-o", str(out)]) == 0
    page = out.read_text()
    assert '<g class="cn ' in page and not re.search(r'<g class="cn [^>]*><title>', page)  # not the plain tooltip
    assert '<foreignObject class="ctip tp-f0' in page and ":hover) .tp-f0{display:inline}" in page
    # its def as written, in colour
    assert (
        '<pre class="ctc"><span class="pk">def</span> <span class="pf">lambda_handler</span>(event, context):' in page
    )


def test_line_links_open_the_editor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from code_node.report.editor import editor_link, open_at

    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)

    link = editor_link("vscode", "/home/me/my code")
    assert open_at(link, "app/main.py", 12) == "vscode://file/home/me/my%20code/app/main.py:12"
    assert open_at(editor_link("cursor", "/home/me/code", wsl="Ubuntu"), "a.py", 3) == (
        "cursor://vscode-remote/wsl+Ubuntu/home/me/code/a.py:3"
    )
    assert open_at(editor_link("vscode", "C:\\code"), "a.py", 1) == "vscode://file/C:/code/a.py:1"
    assert editor_link("none", "/home/me/code") == ""
    write(tmp_path / "code", {"app.py": HANDLER})
    out = tmp_path / "page.html"
    assert main([str(tmp_path / "code"), "--no-open", "-o", str(out)]) == 0
    assert f'href="vscode://file{(tmp_path / "code").as_posix()}/app.py:' in out.read_text()
    assert main([str(tmp_path / "code"), "--no-open", "-o", str(out), "--editor", "none"]) == 0
    assert "vscode://" not in out.read_text()


def test_services_show_their_real_logos(tmp_path: Path) -> None:
    from code_node.report.brands import logo, logo_names
    from code_node.report.graph import _g_logo

    assert all(logo(name) is not None for name in logo_names())  # logos/ has a .svg for each one brands.py names
    project = read_project(write(tmp_path, {"app.py": STORES}))
    graph = code_graph(map_code(project.files, "app.handler", libraries=project.libraries(), platform="lambda"))
    boxes = {n.label: n for n in graph.nodes}
    assert _g_logo(boxes["Redis"]) == logo("redis") and _g_logo(boxes["SQLite"]) == logo("sqlite")
    assert _g_logo(boxes["handler()"]) is None  # its own functions keep their line drawing, a Lambda handler too
    page = render_page(page_blocks_for(project, "app.handler"), "x")
    assert page.count('<svg class="logo"') == 4  # SQLite, Redis, MongoDB, Anthropic
    assert 'id="cnl-sqlite-' in page  # each logo's gradient ids get its own prefix, so two logos never share one
    # the decisions tab draws them too, with ids of its own: a gradient found first in a hidden tab draws nothing
    assert page.count('<svg class="logo flg"') >= 4 and 'id="cnf-sqlite-' in page
    assert 'fill="#181818"' not in page  # Anthropic's black follows the text colour, for dark mode


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


DECIDES = """
import json
import os

import boto3
import requests

sqs = boto3.client("sqs")
table = boto3.resource("dynamodb").Table(os.environ["TABLE"])


def lambda_handler(event, context):
    body = json.loads(event["body"])
    kind = body.get("type")
    if kind == "refund":
        table.delete_item(Key={"id": body["id"]})
    elif kind == "charge":
        charge(body)
    else:
        raise ValueError(kind)
    for item in body["items"]:
        if not item.get("sku"):
            continue
        table.put_item(Item=item)
    return {"statusCode": 200}


def charge(body):
    for attempt in range(3):
        try:
            answer = requests.post(os.environ["PSP_URL"], json=body, timeout=5)
        except requests.Timeout:
            continue
        if answer.ok:
            break
    else:
        sqs.send_message(QueueUrl=os.environ["RETRY_QUEUE"], MessageBody=json.dumps(body))
"""


def _decisions_page(tmp_path: Path, files: dict[str, str], entry: str = "app.lambda_handler") -> str:
    project = read_project(write(tmp_path / "code", files))
    return render_page(page_blocks_for(project, entry), "x")


def _flow_part(page: str) -> str:
    return page[page.index('<div class="cdf"') : page.index('<div class="fkey">')]


def test_the_decisions_tab_draws_each_question_and_where_its_answers_go(tmp_path: Path) -> None:
    page = _decisions_page(tmp_path, {"app.py": DECIDES})
    assert '<label class="tl" for="cnd-tab0-1">Decisions<small>5 decisions</small></label>' in page
    flow = _flow_part(page)
    # an elif is the next question on the no path, and else's raise sits beside it
    assert "kind == &#x27;refund&#x27;?" in flow and "kind == &#x27;charge&#x27;?" in flow
    assert "Raises ValueError(kind)" in flow and "Deletes" not in flow and "Writes to DynamoDB (DeleteItem)" in flow
    # `if not x: continue` is asked as x, and its no answer goes on to the next item
    assert "item.get(&#x27;sku&#x27;)?" in flow and "skips to the next item" in flow
    assert ">next item</text>" in flow and ">when every one is done</text>" in flow  # the arrow back, and out
    assert '<g class="fw fwyes">' in flow and '<g class="fw fwno">' in flow
    assert "Returns {&#x27;statusCode&#x27;: 200}" in flow
    # charge() decides too, so it's opened in place: its try, the way taken when it raises, the loop's else
    assert '<g class="fx fcall">' in flow and "charge()" in flow
    assert "if it raises requests.Timeout" in flow and "skips to the next attempt" in flow
    assert "leaves the loop" in flow and "If the loop ran to its end, with no break" in flow
    assert "Sends a message with SQS" in flow
    assert "<script" not in flow  # drawn whole: it needs no JavaScript


def test_a_call_too_deep_to_open_in_place_gets_a_flow_of_its_own(tmp_path: Path) -> None:
    deep = "".join(
        f"def {name}(x):\n    if x:\n        return {after}(x)\n    return None\n\n\n"
        for name, after in zip("abcd", ["b", "c", "d", "int"])
    )
    page = _decisions_page(tmp_path, {"app.py": deep + "def lambda_handler(event, context):\n    return a(event)\n"})
    flow = page[page.index('<div class="cdf"') :]
    first, own = flow.split('<div class="cdf" id="cnd-flow0-0">')
    assert first.count('<g class="fx fcall">') == 2  # a() and b(), opened in place; c() is a box linking to its flow
    assert 'href="#cnd-flow0-0"' in first and "2 decisions inside · its flow ↓" in first  # its own, and d()'s
    assert "Inside <code>c()</code>" in own and own.count('<g class="fx fcall">') == 1  # d(), opened in c()'s


def test_each_route_of_a_web_app_has_a_flow(tmp_path: Path) -> None:
    app = """
from fastapi import FastAPI

app = FastAPI()


@app.get("/books/{book_id}")
def get_book(book_id: int):
    if book_id < 0:
        raise ValueError(book_id)
    return {"id": book_id}


@app.get("/health")
def health():
    return {"ok": True}
"""
    project = read_project(write(tmp_path / "code", {"main.py": app}))
    from code_node.report.build import page_blocks

    cmap = map_code(project.files, "main.app", libraries=project.libraries(), platform="web")
    blocks = page_blocks(cmap, project="x", max_functions=24, max_depth=5, sources=project.files)
    page = render_page(blocks, "x")
    assert "How each route decides what to do" in page
    assert "<code>get_book()</code> · GET /books/{book_id}" in page and "<code>health()</code> · GET /health" in page
    assert "book_id &lt; 0?" in page and "Raises ValueError(book_id)" in page


def test_the_decisions_in_text_say_where_each_answer_goes(tmp_path: Path) -> None:
    from code_node.kit.render import _render_text

    project = read_project(write(tmp_path / "code", {"app.py": DECIDES}))
    lines = _render_text(page_blocks_for(project, "app.lambda_handler"), 100)
    said = lines[lines.index("-- How lambda_handler() decides") : lines.index("-- When Python imports it")]
    assert "kind == 'refund'?  yes: writes to DynamoDB (DeleteItem) · no: asks the next question" in said
    assert "kind == 'charge'?  yes: calls charge() · no: raises ValueError(kind)" in said
    assert "item.get('sku')?  yes: goes on · no: skips to the next item" in said
    assert "↳ charge()  app.py line" in said and "except requests.Timeout: skips to the next item" in said
