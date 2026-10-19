# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this is

`code-node` is a command (`pip install code-node-graph`) that reads a folder of Python code with `ast`, never running
it, and opens an HTML page showing how the code works from one entry point. The page has a graph of what comes in, who
calls whom and what each path reaches (AWS calls with IAM permissions, HTTP, environment variables), each call step by
step, findings, and tables. It was extracted from aws-analyzer's `LambdaView.how_it_works()`
(`~/projects/aws-analyzer/src/aws_analyzer/lambda_functions/analysis/codemap/` and `blocks/graph.py`).

The PyPI name is `code-node-graph`, because PyPI refuses `code-node` as too close to the existing `codenode`. The
command is `code-node` and the import is `code_node`.

## Commands

```bash
uv venv && uv pip install -e . -r requirements-dev.txt   # once
.venv/bin/python -m pytest                                # tests
.venv/bin/ruff check .                                    # lint
.venv/bin/code-node examples/orders-service --no-open -o /tmp/page.html   # try it
.venv/bin/python scripts/shots.py                         # remake docs/images/ (needs Chrome + pillow)
uv pip install -r requirements-docs.txt && .venv/bin/mkdocs build --strict   # the docs site
.venv/bin/python -m build && .venv/bin/twine check --strict dist/*         # the package
uv tool install -e .                                      # put code-node on your PATH, live-edited
```

Slash commands in `.claude/commands/`: `/check` (lint, tests, docs, package), `/shots` (screenshots), `/map <repo>`
(run it on a repo and review the page), `/release` (publish to PyPI).

## Layout

| Path | What it is |
|---|---|
| `src/code_node/cli.py` | The command: argument parsing, picking the entry point (asking on a TTY), saving and opening the page (WSL-aware) |
| `src/code_node/project.py` | A folder: `read_project` (files, module names Python would use, trees parsed lazily), `entry_points`, `entries_in_file`, `project_root`, `Project.libraries()` |
| `src/code_node/analysis/` | **Pure, no I/O.** `reader.py` (`_CodeReader`, follows code from the entry point, tracking what each name holds as a `_Sym`), `mapping.py` (`map_code`), `model.py` (`CodeMap` and its dataclasses), `graph.py` (`code_graph` → `CodeGraph`), `findings.py`, `aws_model.py` (botocore service models), `syntax.py`, `terms.py` (constants and limits) |
| `src/code_node/pages.py` | `PageOptions`, `make_page` / `make_mermaid`: read the folder, map, draw (what the command and the server share) |
| `src/code_node/serve.py` | `--serve`: `LivePage` (the latest page, a version, a Condition), a polling watcher thread, `ThreadingHTTPServer` with `/` and `/events` (Server-Sent Events) |
| `src/code_node/report/` | Drawing: `graph.py` (the SVG layout), `outline.py` (the step tree), `build.py` (`page_blocks`, the page), `style.py` (CSS, `render_page`) |
| `src/code_node/kit/` | Report blocks (`_Title`, `_Cards`, `_Table`, `_Findings`, ...) and the HTML/text renderer, copied from aws-analyzer's `_kit` |
| `examples/orders-service/` | A small Lambda service the screenshots and the CI smoke test run on. Never run |
| `scripts/shots.py` | Makes `docs/images/<figure>-{light,dark}.webp` |
| `scripts/site_graph.py` | Makes the home page's animated graphs (`docs/snippets/`) |
| `docs/`, `mkdocs.yml` | The docs site (MkDocs Material), published by `.github/workflows/pages.yml` |

The two contracts are `CodeMap` (what the code does) and `CodeGraph` (boxes and arrows). Keep `analysis/` free of
rendering and I/O so another front end only needs those two.

## Rules

- **Never run the code being read.** No `import`, `exec` or subprocess on it. botocore is read for its service models
  only, and it stays optional at run time (`_aws_model` returns None without it).
- **The entry point decides the platform.** Lambda-only findings and the event box are gated on
  `cmap.platform == "lambda"`, set when the entry point is a found Lambda handler or with `--lambda`. Write new
  wording for any code, and keep Lambda wording behind that gate.
- **Partial, never a traceback.** `map_code` catches what the reader can't follow and records it in `cmap.limited`.
  The page says what was cut short.
- **No JavaScript in the page.** Interactivity is CSS (`:has()`, `<details>`), as in aws-analyzer. The one exception
  is `serve.py`'s `_LIVE_SCRIPT`, which is added only to the served page, for the reload.
- **The server never dies on bad code.** `LivePage.build` turns any failure into the page and keeps watching. It
  listens on 127.0.0.1 only.
- Python 3.10 floor (CI runs 3.10–3.14), `from __future__ import annotations`, lines up to 120 characters.
- Code from aws-analyzer keeps its style: docstrings open and close on their own lines, and names in full words.
- A user-visible change adds a bullet under `## [Unreleased]` in `CHANGELOG.md`. Remake the screenshots
  (`scripts/shots.py`) when the page's look changes, and update `README.md` and `docs/` with the command.

## The docs site

`docs/` is MkDocs Material (`mkdocs.yml`). Its personality is the graph itself:

- **Look**: ink header with a blue → violet → pink "edge" line under it, a dotted canvas like the graph's, Space
  Grotesk headings over Inter, JetBrains Mono for code. The accents are the graph's edge colours (calls grey, reads
  blue, writes orange, sends pink). Amber is only for warnings. No green or teal in the chrome. All of it is in
  `docs/stylesheets/extra.css`.
- **Home page** (`docs/index.md`): sections named after the graph's columns (COMES IN, ENTRY → CALLS, REACHES, LIVE).
  The two graphs are inline SVG from `scripts/site_graph.py` (`docs/snippets/graph-hero.svg`, `graph-trace.svg`,
  included with `--8<--`). Rerun it after changing the example's shape.
- **Motion** (`docs/javascripts/graph.js`): it puts `.cn-motion` on `<html>`. Without that class, or with
  `prefers-reduced-motion`, nothing animates and nothing is hidden. Graphs draw in and pulses flow (SMIL
  `animateMotion`), the terminal types, and the trace steps through the code lines (`data-on="a>b c>d"` names the
  edges each line lights). Sections rise in on scroll, and a progress "edge" runs along the top.
- **Copy**: short and simple, for someone skimming on a phone. One idea per line, no paragraph over about two
  sentences. Every page opens with a one-line `{ .gist }` (on its own line, under the sentence). Tables beat prose.
  Detail goes in `??? more "..."` folds, and the one thing worth knowing goes in `!!! tip "Worth knowing"`.

## Tests

`tests/test_code_node.py` writes small projects into `tmp_path` and checks entry point discovery, the map (functions,
AWS calls, imports), the graph's limits, and the command end to end (`main([...])` with `--no-open -o`). Add a test
there for each new kind of entry point or anything new the reader follows.

## Releasing

`/release`: bump `__version__` in `src/code_node/__init__.py`, move `## [Unreleased]` under the new version in
`CHANGELOG.md`, merge, then publish a GitHub release tagged `v<version>`. `.github/workflows/release.yml` builds,
checks that the tag matches `__version__`, and uploads with PyPI trusted publishing (no token). This needs a one-time
setup, written at the top of `release.yml`.
