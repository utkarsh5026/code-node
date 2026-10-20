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
uv sync                                                   # .venv with every dependency group
uv run pytest                                             # tests
uv run ruff check .                                       # lint
uv run ruff format .                                      # format (examples/ and docs/ are left as they are)
uv run code-node examples/orders-service --no-open -o /tmp/page.html   # try it
uv run python scripts/shots.py                            # remake docs/images/ (needs Chrome)
uv run mkdocs build --strict                              # the docs site
uv run python -m build && uv run twine check --strict dist/*   # the package (make package also installs the wheel as your code-node)
uv tool install -e .                                      # put code-node on your PATH, live-edited
```

Every dependency, the dev tools included, is in `pyproject.toml`: `[project] dependencies` for the package, and
`[dependency-groups]` (`dev`, `package`, `docs`) for working on it, all installed by `uv sync` and locked in `uv.lock`.
Change them there (`uv add --group dev x`), never with `uv pip install`, and commit `uv.lock` with it. `uv run` syncs
`.venv` before each command, so a stale or stripped venv fixes itself.

The `Makefile` has each of these by name (`make` lists them): `make install` (`uv sync`), `make test`, `make lint`,
`make try` (`REPO=<folder>` for another repo), `make serve`, `make shots`, `make docs`, `make package`, and `make check` for
all of what CI runs. `makefile.py` has the same tasks in Python with rich (`python makefile.py check`), for
Windows and for coloured output; a new task goes in both.

Slash commands in `.claude/commands/`: `/check` (lint, tests, docs, package), `/shots` (screenshots), `/map <repo>`
(run it on a repo and review the page), `/release` (publish to PyPI).

## Layout

| Path | What it is |
|---|---|
| `src/code_node/cli.py` | The command: argument parsing, picking the entry point (asking on a TTY), saving and opening the page (WSL-aware) |
| `src/code_node/project.py` | A folder: `read_project` (files, module names Python would use, trees parsed lazily), `entry_points`, `entries_in_file`, `project_root`, `Project.libraries()` |
| `src/code_node/analysis/` | **Pure, no I/O.** `reader.py` (`_CodeReader`, follows code from the entry point, tracking what each name holds as a `_Sym`), `mapping.py` (`map_code`), `model.py` (`CodeMap` and its dataclasses), `graph.py` (`code_graph` → `CodeGraph`), `findings.py`, `aws_model.py` (botocore service models), `syntax.py`, `terms.py` (constants and limits) |
| `src/code_node/platforms/` | **Pure, no I/O.** `Platform` (plain Python: the base a plugin overrides), the registry (`register_platform`, `get_platform`, the `code_node.platforms` entry point group), `aws_lambda.py` (`LambdaPlatform`: handlers, the event, its findings and wording, IAM drift against a `Deployment`), and `web.py` (`WebPlatform`: FastAPI, Flask and Django apps and URL confs, a route's parameters and `flask.request` as the request, blocking calls in async routes) |
| `src/code_node/libraries/` | **Pure, no I/O.** `Library` (a library's clients: `make`, `attribute`, `item`, `call`), `Handle` (what a name holds), `Use` (what a call does), `Call` (the call as a plugin sees it), the registry (`code_node.libraries`), and `redis.py`, `sql.py`, `mongo.py`, `llm.py` |
| `src/code_node/deploys/` | **Pure, no I/O.** `Deploy` (a kind of deploy file: `deployments(files, code)` → `Deployment`s, `grant`), the registry (`code_node.deploys`), YAML with CloudFormation tags, IAM policy helpers, and `sam.py`, `serverless.py` |
| `src/code_node/pages.py` | `PageOptions`, `make_page` / `make_mermaid`: read the folder, map, draw (what the command and the server share) |
| `src/code_node/serve.py` | `--serve`: `LivePage` (the latest page, a version, a Condition), a polling watcher thread, `ThreadingHTTPServer` with `/` and `/events` (Server-Sent Events) |
| `src/code_node/report/` | Drawing: `brands.py` (which logo each AWS service and library service gets, read from `logos/*.svg` and, for AWS's, a small mark in `logos/small/` for 16 to 32 px; `logo_for(name, pixels)` picks, and the page's graph has both and picks by screen density. Written by `scripts/logos.py`: never edit them), `graph.py` (the SVG layout), `walk.py` (Step by step: the steps in run order beside their code), `tabs.py` (the Graph / Step by step tabs), `outline.py` (the step tree, for text), `build.py` (`page_blocks`, the page), `style.py` (CSS, `render_page`) |
| `src/code_node/kit/` | Report blocks (`_Title`, `_Cards`, `_Table`, `_Findings`, ...) and the HTML/text renderer, copied from aws-analyzer's `_kit` |
| `examples/orders-service/` | A small Lambda service the screenshots and the CI smoke test run on. Never run |
| `examples/books-api/` | A FastAPI app on the web platform (routes on an `APIRouter`, PostgreSQL, Redis, S3), with a mistake for each web finding, for `tests/snapshots/books-api.txt` and the Plugins page's web apps. Never run |
| `examples/cart-service/` | A Lambda function in a SAM template using PostgreSQL, Redis, OpenAI and boto3: every kind of plugin at once, for `tests/snapshots/cart-service.txt` and the Plugins page. Never run |
| `Makefile`, `makefile.py` | The commands below by name; `makefile.py` is the same tasks in Python with rich, for any OS |
| `scripts/shots.py` | Makes `docs/images/<figure>-{light,dark}.webp` |
| `scripts/site_graph.py` | Makes the home page's graph (`docs/snippets/graph-trace.svg`) |
| `scripts/docs_figures.py` | Draws the docs' plugin figures with the logos (`docs/images/plugins-mix-*.svg`, `reaches-*.svg`), light and dark. It checks each finding it shows is still one `examples/cart-service` makes; rerun it (`make figures`) after changing that example or the plugins |
| `scripts/logos.py` | Downloads the pinned `@iconify-json/logos` (checked against its hash) and writes the logos `brands.py` names to `report/logos/`, one `.svg` each. Run it (`make logos`) after naming a new one |
| `docs/`, `mkdocs.yml` | The docs site (MkDocs Material), published by `.github/workflows/pages.yml` |

The two contracts are `CodeMap` (what the code does) and `CodeGraph` (boxes and arrows). Keep `analysis/` free of
rendering and I/O (it uses `platforms/`, which is pure too) so another front end only needs those two.

## Rules

- **Never run the code being read.** No `import`, `exec` or subprocess on it. botocore is read for its service models
  only, and it stays optional at run time (`_aws_model` returns None without it).
- **Generic first, platforms as plugins.** The reader, findings, graph and page are for any Python. What's
  different where the code runs (entry points, what they're called with, findings, wording) is a `Platform` in
  `platforms/`, looked up with `get_platform(cmap.platform)`. `cmap.platform` comes from the entry point a platform
  found (`EntryPoint.platform`), a deploy file's `Deployment.platform`, or `--platform` / `--lambda`. Never test
  `cmap.platform == "lambda"` outside `platforms/aws_lambda.py`: add a hook to `Platform` instead, with plain-Python
  wording as its default.
- **Plugins mix.** One platform per map, but libraries (`libraries/`) and deploy files (`deploys/`) stack. What
  one library knows goes in its plugin, never in the reader: the reader only tracks `Handle`s and asks the plugin
  (`_outside` → `make`, `_attribute` → `attribute`, `_call` → `call`). Checks that need two kinds at once (a
  client's timeout against the platform's, permissions against the deploy file) go in `findings.py` or the
  platform, through hooks (`Platform.hang`, `Platform.denied`), so any plugin of each kind gets them.
- **Partial, never a traceback.** `map_code` catches what the reader can't follow and records it in `cmap.limited`.
  The page says what was cut short.
- **The page works without JavaScript; JavaScript only adds to it.** What every reader needs is CSS (`:has()`,
  `<details>`, radio buttons), so a page opened where scripts are stripped still works. A script may add what CSS
  can't (`report/graph.py`'s `_G_SCRIPT` opens a box's calls not drawn as a graph of their own, from `<template>`s),
  with its controls hidden until it has run (`.cgw.js`). `serve.py`'s `_LIVE_SCRIPT` is added only to the served page.
- **No `:has()` on an ancestor of the walk's radio buttons** (`.cnd`, `.tabs`, `body`). Chrome then restyles the
  whole page on every step, which takes seconds on a big one; use sibling selectors, or `:has()` on a box that
  doesn't hold the walk (the graph's are on `.cgw`).
- **The server never dies on bad code.** `LivePage.build` turns any failure into the page and keeps watching. It
  listens on 127.0.0.1 only.
- Python 3.10 floor (CI runs 3.10–3.14), `from __future__ import annotations`, lines up to 120 characters.
- Code from aws-analyzer keeps its style: docstrings open and close on their own lines, and names in full words.
- A user-visible change adds a bullet under `## [Unreleased]` in `CHANGELOG.md`. Remake the screenshots
  (`scripts/shots.py`) when the page's look changes, and update `README.md` and `docs/` with the command.

## The docs site

`docs/` is MkDocs Material (`mkdocs.yml`). It is plain on purpose, and it sells the tool by showing its real output:

- **Look**: white paper (dark slate in dark mode), black type, one link blue, IBM Plex Sans and IBM Plex Mono. The
  only colour is the graph's, where it means something (calls grey, reads blue, writes orange, sends pink); amber
  is for warnings and the lit code line. No gradients, glows, shadows, pills, eyebrow labels or numbered sections.
  All of it is in `docs/stylesheets/extra.css`.
- **Home page** (`docs/index.md`): one figure, `orders/handler.py`'s `lambda_handler` next to its graph. Then the
  example's real output: AWS calls with permissions, findings, the page screenshot, a terminal transcript. Keep
  every line number, count and output on it true to `examples/orders-service` and the command. The graph is inline
  SVG from `scripts/site_graph.py` (`docs/snippets/graph-trace.svg`, included with `--8<--`). Rerun it after
  changing the example's shape.
- **Motion** (`docs/javascripts/graph.js`): only the figure. Selecting a code line (`data-on="a>b c>d"` names the
  edges it lights) shows its path; until someone does, it steps through the lines, unless the reader asked for
  less motion. Nothing else animates or hides on scroll.
- **Copy**: plain, specific sentences, as a person would write a README. Say what it does with real names, not
  slogans or fragments ("Point. Run. Look."). Every page opens with a one-line `{ .gist }` (on its own line, under
  the sentence) saying what the page covers. Tables beat prose. Detail goes in `??? more "..."` folds, and the one
  thing worth knowing goes in `!!! tip "Worth knowing"`.

## Tests

`tests/test_code_node.py` writes small projects into `tmp_path` and checks entry point discovery, the map (functions,
AWS calls, imports), the graph's limits, plain Python against `platform="lambda"`, a plugin platform, and the
command end to end (`main([...])` with `--no-open -o`). Add a test
there for each new kind of entry point or anything new the reader follows.

## Releasing

`/release`: bump `__version__` in `src/code_node/__init__.py`, move `## [Unreleased]` under the new version in
`CHANGELOG.md`, merge, then publish a GitHub release tagged `v<version>`. `.github/workflows/release.yml` builds,
checks that the tag matches `__version__`, and uploads with PyPI trusted publishing (no token). This needs a one-time
setup, written at the top of `release.yml`.
