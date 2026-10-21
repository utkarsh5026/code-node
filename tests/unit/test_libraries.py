"""
Library plugins: the clients they follow and what they flag.
"""

from __future__ import annotations

from pathlib import Path

from code_node.analysis.graph import code_graph
from code_node.analysis.mapping import map_code
from code_node.project import read_project

from support import STORES, write


def test_library_plugins_follow_their_clients_and_flag_what_the_input_reaches(tmp_path: Path) -> None:
    from code_node.analysis.findings import code_map_findings

    project = read_project(write(tmp_path, {"app.py": STORES}))
    cmap = map_code(project.files, "app.handler", libraries=project.libraries(), platform="lambda")
    calls = {(c.service, c.operation, c.target): c for c in cmap.library_calls}
    assert set(calls) == {
        ("SQLite", "SELECT", "users"),
        ("SQLite", "DELETE", "sessions"),
        ("Redis", "KEYS", "session:*"),
        ("Redis", "DELETE", "key"),
        ("MongoDB", "insert_one", "orders"),
        ("MongoDB", "find_one", "users"),
        ("Anthropic", "messages.create", "claude-sonnet-5-5"),
    }
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
    code = (
        "from kafka import KafkaProducer\n\nproducer = KafkaProducer()\n\n\n"
        "def main():\n    producer.send('orders', b'1')\n"
    )
    project = read_project(write(tmp_path, {"app.py": code}))
    cmap = map_code(project.files, "app.main", libraries=project.libraries())
    assert [(c.service, c.operation, c.access, c.target) for c in cmap.library_calls] == [
        ("Kafka", "send", "sends", "orders")
    ]
    box = next(n for n in code_graph(cmap).nodes if n.kind == "service")
    assert (box.label, box.icon, box.lines) == ("Kafka", "queue", ["send orders"])
