"""
--serve: the live page over real HTTP, redrawn when the code changes.
"""

from __future__ import annotations

from pathlib import Path

from support import HANDLER, write


def test_the_live_server_redraws_when_the_code_changes(tmp_path: Path, monkeypatch) -> None:
    import threading
    import urllib.request

    from code_node import serve as servemod
    from code_node.pages import PageOptions
    from code_node.project import EntryPoint

    monkeypatch.setattr(servemod, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(servemod, "SETTLE_SECONDS", 0.05)
    root = write(tmp_path, {"app.py": HANDLER})
    live = servemod.LivePage(
        root, EntryPoint("app.lambda_handler", "", "app.py", 0, "lambda"), PageOptions(), log=lambda line: None
    )
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


def test_the_page_s_event_stream_says_each_new_version(tmp_path: Path, monkeypatch) -> None:
    """
    /events over a real connection, as the served page's EventSource reads it: the version now, then each new one.
    """
    import http.client
    import threading

    from code_node import serve as servemod
    from code_node.pages import PageOptions
    from code_node.project import EntryPoint

    monkeypatch.setattr(servemod, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(servemod, "SETTLE_SECONDS", 0.05)
    root = write(tmp_path, {"app.py": HANDLER})
    live = servemod.LivePage(
        root, EntryPoint("app.lambda_handler", "", "app.py", 0, "lambda"), PageOptions(git=False), log=lambda line: None
    )
    live.build()
    server = servemod.listen(servemod._handler(live), port=0)
    assert server.server_address[0] == "127.0.0.1"  # never on another interface
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=live.watch, daemon=True).start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    try:
        connection.request("GET", "/events")
        response = connection.getresponse()
        assert response.status == 200 and response.headers["Content-Type"] == "text/event-stream"
        assert response.readline() == b"data: 1\n"
        (root / "app.py").write_text(HANDLER + "\n\ndef more():\n    pass\n")
        response.readline()  # the blank line that ends an event
        assert response.readline() == b"data: 2\n"
        (root / "app.py").write_text("def lambda_handler(event, context):\n    return (\n")  # mid-edit
        response.readline()
        assert response.readline() == b"data: 3\n"  # still serving, with the error as the page
        other = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        other.request("GET", "/nothing-here")
        assert other.getresponse().status == 404
        other.close()
    finally:
        connection.close()
        live.stop()
        server.shutdown()
        server.server_close()
