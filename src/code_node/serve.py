"""
code-node --serve: the page on a local server, made again whenever a .py file (or a deploy file, like template.yaml)
under the folder changes, and the browser told to reload (keeping its scroll position, and the tab and step that were
open). Standard library only: a polling watcher thread, a threaded HTTP server, and Server-Sent Events for the reload.

The saved pages have no JavaScript; the served one gets a few lines (_LIVE_SCRIPT) to reload and to say when the
server has stopped.
"""

from __future__ import annotations

import html
import os
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from .deploys import deploy_file_names
from .pages import PageOptions, make_page
from .project import _SKIPPED_FOLDERS, EntryPoint
from .report.style import FAVICON_LINK, FAVICON_SVG

DEFAULT_PORT = 8765  # without --port, the first free port from here on is used, so several folders can be served

PORTS_TRIED = 20  # how many ports from DEFAULT_PORT are tried before letting the system pick any free one

POLL_SECONDS = 0.5  # how often the folder is checked for changes

SETTLE_SECONDS = 0.3  # a change waits this long for the rest of a save (editors write files in steps)

HEARTBEAT_SECONDS = 15  # an idle event stream sends a comment this often, so proxies don't close it

_LIVE_SCRIPT = """
<div id="cn-live" style="position:fixed;right:14px;bottom:14px;z-index:9;font:12px/1.4 system-ui,sans-serif;
padding:6px 10px;border-radius:999px;background:rgba(127,127,127,.14);backdrop-filter:blur(6px)">● live</div>
<script>
(() => {
  const key = "code-node-scroll:" + location.pathname;
  const saved = JSON.parse(sessionStorage.getItem(key) || "null");
  sessionStorage.removeItem(key);
  if (saved) {  // the tab and the step that were open, where the list of steps was, then the page
    for (const id of saved.picked || []) { const radio = document.getElementById(id); if (radio) radio.checked = true; }
    document.querySelectorAll(".walk .wl").forEach((list, i) => { list.scrollTop = (saved.lists || [])[i] || 0; });
    window.scrollTo(0, saved.y || 0);
  }
  const badge = document.getElementById("cn-live");
  const events = new EventSource("/events");
  let version = null;
  events.onmessage = (e) => {
    if (version !== null && e.data !== version) {
      sessionStorage.setItem(key, JSON.stringify({
        y: window.scrollY,
        picked: [...document.querySelectorAll("input[type=radio]:checked")].map((radio) => radio.id),
        lists: [...document.querySelectorAll(".walk .wl")].map((list) => list.scrollTop),
      }));
      location.reload();
    }
    version = e.data;
    badge.textContent = "● live";
    badge.style.color = "";
  };
  events.onerror = () => { badge.textContent = "○ server stopped"; badge.style.color = "#d97706"; };
})();
</script>
"""


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """
    Every .py file under root (skipping what read_project skips), and every deploy file (template.yaml,
    serverless.yml), with its modified time and size.
    """
    found: dict[str, tuple[int, int]] = {}
    deploy_names = deploy_file_names()
    for folder, subfolders, names in os.walk(root):
        subfolders[:] = [d for d in subfolders if d not in _SKIPPED_FOLDERS and not d.endswith(".egg-info")]
        for name in names:
            if not name.endswith(".py") and name not in deploy_names:
                continue
            path = os.path.join(folder, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            found[path] = (stat.st_mtime_ns, stat.st_size)
    return found


def changed_files(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]]) -> list[str]:
    """
    The files added, removed or changed between two snapshots.
    """
    return sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))


def _error_page(message: str, entry: EntryPoint) -> str:
    return (f"<!doctype html><meta charset='utf-8'>{FAVICON_LINK}<title>code-node</title><body style='font:15px system-ui;"
            f"margin:40px;color-scheme:light dark'><h2>Couldn't draw {html.escape(entry.name)}</h2>"
            f"<p>{html.escape(message)}</p><p>Fix it and save: the page comes back by itself.</p></body>")


@dataclass
class LivePage:
    """
    The latest page, its version, and a condition the event streams wait on for the next one.
    """

    root: Path
    entry: EntryPoint
    options: PageOptions
    log: Callable[[str], None] = field(default=lambda line: print(line, flush=True))
    page: str = ""
    version: int = 0
    changed: threading.Condition = field(default_factory=threading.Condition)
    stopping: threading.Event = field(default_factory=threading.Event)

    def build(self, reason: str = "") -> None:
        """
        Makes the page again. When that fails, the error is shown in the page instead, and the server keeps going.
        """
        started = time.monotonic()
        try:
            page, cmap = make_page(self.root, self.entry, self.options)
            said = f"{len(cmap.functions)} functions, {len(cmap.aws)} AWS calls"
        except Exception as exc:  # noqa: BLE001  any failure becomes the page, never a dead server
            page, said = _error_page(f"{type(exc).__name__}: {exc}", self.entry), f"failed: {type(exc).__name__}"
        # the folder's name leads the tab title, to tell apart the tabs of several servers
        page = page.replace("<title>", f"<title>{html.escape(self.root.name)} · ", 1)
        page = page.replace("</body>", _LIVE_SCRIPT + "</body>", 1) if "</body>" in page else page + _LIVE_SCRIPT
        with self.changed:
            self.page = page
            self.version += 1
            self.changed.notify_all()
        took = time.monotonic() - started
        self.log(f"{time.strftime('%H:%M:%S')}  {reason or 'drawn'}: {said} ({took:.1f}s)")

    def wait_for_change(self, version: int, timeout: float) -> int:
        """
        The version after `version`, once there is one, or `version` again after timeout.
        """
        with self.changed:
            self.changed.wait_for(lambda: self.version != version or self.stopping.is_set(), timeout)
            return self.version

    def watch(self) -> None:
        """
        Checks the folder every POLL_SECONDS and builds the page again when a .py file changes.
        """
        before = snapshot(self.root)
        while not self.stopping.wait(POLL_SECONDS):
            after = snapshot(self.root)
            if after == before:
                continue
            time.sleep(SETTLE_SECONDS)
            after = snapshot(self.root)
            changed = changed_files(before, after)
            before = after
            if changed:
                names = [os.path.relpath(path, self.root) for path in changed]
                self.build(", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else ""))

    def stop(self) -> None:
        self.stopping.set()
        with self.changed:
            self.changed.notify_all()


def _handler(live: LivePage) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802  the name http.server calls
            if self.path.split("?")[0] == "/events":
                self._events()
            elif self.path.split("?")[0] in ("/", "/index.html"):
                body = live.page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path.split("?")[0] in ("/favicon.ico", "/favicon.svg"):
                body = FAVICON_SVG.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml")
                self.send_header("Cache-Control", "max-age=86400")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def _events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            version = live.version
            try:
                self.wfile.write(f"data: {version}\n\n".encode())
                self.wfile.flush()
                while not live.stopping.is_set():
                    newer = live.wait_for_change(version, HEARTBEAT_SECONDS)
                    message = f"data: {newer}\n\n" if newer != version else ": still here\n\n"
                    self.wfile.write(message.encode())
                    self.wfile.flush()
                    version = newer
            except (BrokenPipeError, ConnectionResetError):
                return

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002  quiet: the watcher says what matters
            return

    return Handler


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # on Windows, SO_REUSEADDR lets a second server take a port that's in use, so one folder would hide another
    allow_reuse_address = os.name != "nt"


def listen(handler: type[BaseHTTPRequestHandler], port: int | None = None) -> ThreadingHTTPServer:
    """
    A server on 127.0.0.1: on `port` when one is given (0 is any free port), or else the first free port from
    DEFAULT_PORT, so another code-node --serve already running elsewhere doesn't stop this one.
    """
    if port is not None:
        return _Server(("127.0.0.1", port), handler)
    for candidate in range(DEFAULT_PORT, DEFAULT_PORT + PORTS_TRIED):
        try:
            return _Server(("127.0.0.1", candidate), handler)
        except OSError:
            continue
    return _Server(("127.0.0.1", 0), handler)


def serve(root: Path, entry: EntryPoint, options: PageOptions, *, port: int | None = None,
          open_page: Callable[[str], None] | None = None) -> int:
    """
    Serves the page on http://localhost:<port> until Ctrl-C, drawing it again on every change under root. Without a
    port, it's the first free one from DEFAULT_PORT.
    """
    live = LivePage(root, entry, options)
    live.build()
    try:
        server = listen(_handler(live), port)
    except OSError as exc:
        print(f"Can't listen on port {port if port is not None else DEFAULT_PORT} ({exc.strerror}): pick another with "
              "--port.")
        return 1
    url = f"http://localhost:{server.server_address[1]}/"
    watcher = threading.Thread(target=live.watch, name="code-node-watch", daemon=True)
    watcher.start()
    print(f"Serving {entry.name} at {url}  (watching {root}; Ctrl-C to stop)", flush=True)
    if open_page is not None:
        open_page(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        live.stop()
        server.server_close()
    return 0
