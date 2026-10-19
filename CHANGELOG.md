# Changelog

Every change a user would notice, newest first ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)). Versions
follow [Semantic Versioning](https://semver.org/); before 1.0, a minor version may change what a command does.

## [Unreleased]

### Changed

- The page is only two tabs now, Graph and Step by step. The title, the cards of numbers, the findings and the tables
  under the graph (AWS calls and their IAM policy, environment variables, the event, functions, imports, HTTP
  requests) are gone. The entry point and the folder sit at the right of the tab bar, which stays at the top as you
  scroll. The graph still marks a warning on a box, such as an HTTP request with no timeout.
- The graph and the steps are in tabs, Graph and Step by step, instead of one under the other.
- Step by step is now a walk through the code in the order it runs, as a debugger steps: every step in a list, and
  beside it the function the current step is in, its line lit, with a card saying what the line does and which calls
  it's inside. Next goes into each function a line calls, Step over and Step out skip past them, and once a step is
  clicked the arrow keys step through the rest. Click any numbered line in the code to jump to it. Still no
  JavaScript, and a step is as quick on a page with thousands of them.
- The paragraph summing up the code under the numbers is gone: the numbers, the findings and the graph say it.
- Code on the page is set in Cascadia Mono when it's installed (the usual monospace font otherwise).
- `code-node --serve` keeps the open tab and step when the page redraws.
- The graph's code panel makes room beside the graph, rather than moving the whole page.

- `code-node --serve` without `--port` takes the first free port from 8765, so you can serve several folders at
  once instead of the second one failing. The served tab's title starts with the folder's name. `--port N` still
  means exactly that port.

- Lambda is now a platform plugin on top of a generic reader. Plain Python code no longer gets any Lambda check or
  wording (a file written outside `/tmp` used to be marked amber in the graph), and Lambda handlers get the same
  page as before.
- `--platform NAME` runs a platform's checks whatever the entry point is; `--lambda` is short for
  `--platform lambda`. `EntryPoint.is_lambda` and `PageOptions.is_lambda` are now `platform` (`"lambda"` or `""`).

### Added

- The pages have a tab icon (code-node's logo), saved and served.

- Click a box in the graph to read its code in a panel on the right: a function whole, with the lines that make
  its calls lit, or a few lines around each place the code uses a service, a variable or its input. No JavaScript:
  the panel opens with CSS (`:target`), and Back closes it. `GraphNode.code` lists the lines (`CodeSpan`), and
  `page_blocks(..., sources=...)` takes the files to show them from.
- Platforms: subclass `code_node.Platform` to say what another place code runs adds (its entry points, what
  they're called with, its findings and wording), and add it with `register_platform` or a `code_node.platforms`
  entry point in a package's `pyproject.toml`.

## [0.1.0] - 2026-10-19

### Added

- `code-node [folder]` reads a folder of Python code with `ast` (nothing is run) and opens a page showing how it works
  from an entry point: a graph of what comes in, who calls whom and what each path reaches (AWS calls with their IAM
  permissions, HTTP requests, environment variables), each call step by step, findings, and tables.
- Entry points are found for you: `pyproject.toml` console scripts, Lambda handlers, FastAPI / Flask apps (each
  route), Typer apps (each command), what runs under `if __name__ == "__main__":`, and functions named `main`.
  When there are several, it asks which one.
- Start from a file with `code-node path/to/main.py` or `code-node main.py:function` (or `Class.method`), from a
  dotted name with `-e pkg.cli.main`, or search by part of a name with `-e save`.
- `code-node --serve` puts the page on http://localhost:8765 and redraws it whenever a `.py` file changes. The
  browser reloads at the same scroll position, and a page that can't be drawn says why until the next save.
- `--all` draws every function however deep; `--depth` and `--functions` set the limits; `--mermaid` prints the
  graph as Mermaid; `--list` lists the entry points.

[Unreleased]: https://github.com/utkarsh5026/code-node/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/utkarsh5026/code-node/releases/tag/v0.1.0
