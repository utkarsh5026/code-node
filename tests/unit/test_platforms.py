"""
Platforms: Lambda, the web frameworks, and a platform plugin.
"""

from __future__ import annotations

from pathlib import Path

from code_node.analysis.graph import code_graph
from code_node.analysis.mapping import map_code
from code_node.cli import main
from code_node.project import entry_points, read_project

from support import write


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


FASTAPI = """
import sqlite3
import time
from typing import Annotated, Optional

import requests
from fastapi import Depends, FastAPI, Query, Request
from pydantic import BaseModel

app = FastAPI()
db = sqlite3.connect("shop.db")


class OrderIn(BaseModel):
    item: str


def user():
    return "me"


@app.get("/orders/{order_id}")
def get_order(order_id: int, fields: str = "id", who=Depends(user)):
    return db.execute(f"SELECT {fields} FROM orders WHERE id = {order_id}").fetchone()


@app.get("/search")
async def search(q: Annotated[str, Query(alias="term")], limit: Optional[int] = None):
    requests.get("https://example.com/search", timeout=5)
    time.sleep(1)


@app.post("/orders")
async def create(order: OrderIn, request: Request):
    note = (await request.json())["note"]
    db.execute("INSERT INTO orders (item, note) VALUES (?, ?)", (order.item, note))
"""


def test_a_fastapi_routes_parameters_are_the_request(tmp_path: Path) -> None:
    from code_node.analysis.findings import code_map_findings

    project = read_project(write(tmp_path / "code", {"main.py": FASTAPI}))
    assert [(e.name, e.platform) for e in entry_points(project)] == [("main.app", "web")]
    cmap = map_code(project.files, "main.app", libraries=project.libraries(), platform="web")
    assert {f.label: f.required for f in cmap.event} == {
        "path.order_id": True,
        "query.fields": False,
        "query.term": True,
        "query.limit": False,
        "body": True,
        "body.item": True,
        "json": True,
        "json.note": True,
    }  # who=Depends(...) isn't from the request
    said = [message for _, message in code_map_findings(cmap)]
    assert any("puts request query.fields, request path.order_id into the SQL text itself" in m for m in said)
    assert any(
        "requests.get() at main.py line 29 and time.sleep() at main.py line 30 wait without await inside "
        "async def search()" in m
        for m in said
    )
    assert not any("create()" in m for m in said)  # its SQL takes parameters
    assert next(n for n in code_graph(cmap).nodes if n.kind == "event").label == "The request"
    assert next(n for n in code_graph(cmap).nodes if n.kind == "handler").icon == "fastapi-icon"  # the app's logo
    plain = map_code(project.files, "main.app", libraries=project.libraries())  # plain Python: no request
    assert not plain.event and not any("SQL injection" in m for _, m in code_map_findings(plain))


def test_a_flask_views_url_values_and_request_are_the_input(tmp_path: Path) -> None:
    from code_node.analysis.findings import code_map_findings

    source = (
        "import os\nimport sqlite3\nfrom flask import Flask, request\n\napp = Flask(__name__)\n"
        'db = sqlite3.connect("x.db")\n\n\n@app.route("/users/<int:user_id>")\ndef user(user_id):\n'
        '    return db.execute("SELECT * FROM users WHERE id = %s" % user_id).fetchone()\n\n\n'
        '@app.post("/search")\ndef search():\n    q = request.args.get("q", "")\n'
        '    team = request.get_json()["team"]\n'
        "    db.execute(f\"SELECT * FROM users WHERE name = '{q}' AND team = '{team}'\")\n"
        '    os.system("grep " + request.form["pattern"] + " app.log")\n'
    )
    project = read_project(write(tmp_path / "code", {"app.py": source}))
    entry = entry_points(project)[0]
    assert (entry.name, entry.platform) == ("app.app", "web")
    cmap = map_code(project.files, entry.name, libraries=project.libraries(), platform=entry.platform)
    assert [f.label for f in cmap.event] == [
        "path.user_id",
        "args",
        "args.q",
        "json",
        "json.team",
        "form",
        "form.pattern",
    ]
    said = [message for _, message in code_map_findings(cmap)]
    assert any("puts request path.user_id into the SQL text" in m for m in said)
    assert any("puts request args.q, request json.team into the SQL text" in m for m in said)
    assert any("shell command with request form.pattern in it" in m for m in said)


def test_django_urls_are_followed_through_include_views_and_routers(tmp_path: Path) -> None:
    from code_node.analysis.findings import code_map_findings

    views = (
        "import json\nfrom django.db import connection\nfrom django.views import View\n"
        "from django.views.decorators.http import require_GET\nfrom rest_framework import viewsets\n\n\n"
        '@require_GET\ndef order_list(request):\n    status = request.GET.get("status")\n'
        "    with connection.cursor() as cursor:\n"
        "        cursor.execute(f\"SELECT * FROM orders WHERE status = '{status}'\")\n\n\n"
        "class OrderDetail(View):\n    def get(self, request, pk):\n        return pk\n\n"
        '    def post(self, request, pk):\n        note = json.loads(request.body)["note"]\n\n\n'
        "class ItemViewSet(viewsets.ViewSet):\n    def retrieve(self, request, pk=None):\n        return pk\n"
    )
    urls = (
        "from django.urls import include, path\nfrom rest_framework.routers import DefaultRouter\n"
        'from . import views\n\nrouter = DefaultRouter()\nrouter.register("items", views.ItemViewSet)\n\n'
        'urlpatterns = [\n    path("orders/", views.order_list),\n'
        '    path("orders/<int:pk>/", views.OrderDetail.as_view()),\n    path("", include(router.urls)),\n]\n'
    )
    project = read_project(
        write(
            tmp_path / "code",
            {
                "shop/__init__.py": "",
                "shop/urls.py": (
                    'from django.urls import include, path\n\nurlpatterns = [path("api/", include("orders.urls"))]\n'
                ),
                "orders/__init__.py": "",
                "orders/urls.py": urls,
                "orders/views.py": views,
            },
        )
    )
    found = entry_points(project)  # the site's URLs first: they include the app's
    assert [(e.name, e.platform) for e in found] == [
        ("shop.urls.urlpatterns", "web"),
        ("orders.urls.urlpatterns", "web"),
    ]
    cmap = map_code(project.files, found[0].name, libraries=project.libraries(), platform="web")
    assert [(method, path) for method, path, _ in cmap.routes] == [
        ("GET", "/api/items/<pk>/"),
        ("GET", "/api/orders/"),
        ("GET", "/api/orders/<int:pk>/"),
        ("POST", "/api/orders/<int:pk>/"),
    ]
    assert {"path.pk", "GET.status", "body (JSON).note"} <= {f.label for f in cmap.event}
    said = [message for _, message in code_map_findings(cmap)]
    assert any("puts request GET.status into the SQL text" in m for m in said)
    assert next(n for n in code_graph(cmap).nodes if n.kind == "handler").icon == "django-icon"


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
            return [
                (n.name, n.lineno, "a job")
                for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name.startswith("job_")
            ]

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
