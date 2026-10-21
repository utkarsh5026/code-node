# Start

Installing it, choosing where it starts, and every option.
{ .gist }

## Install { #install }

```bash
pip install code-node-graph
```

To have it in every project, install it as a tool: `uv tool install code-node-graph` or
`pipx install code-node-graph`. It needs Python 3.10 or newer.

## Run it { #run }

```bash
cd your/repo
code-node
```

It looks for the places your code starts, asks which one you want if there's more than one, and opens the page
in your browser.

## Pick where to start { #entry }

| You type | It starts at |
| --- | --- |
| `code-node` | Wherever you pick from what it finds |
| `code-node app/main.py` | That file's `main()` |
| `code-node app/main.py:run` | `run()` in that file |
| `code-node app/store.py:Store.save` | A method |
| `code-node -e pkg.cli.main` | A dotted name |
| `code-node -e save` | Anything with "save" in its name |
| `code-node --list` | Nowhere: it lists the entry points it found |

??? more "What it finds on its own"
    In this order:

    - console scripts in every `pyproject.toml` (the root's first, then a monorepo's `libs/*/pyproject.toml`)
    - Lambda handlers: `def handler(event, context)`
    - FastAPI / Flask apps, and Django's `urls.py`: every route, called with the request
    - Typer apps: every command
    - whatever runs under `if __name__ == "__main__":`
    - functions called `main`, `run`, `cli` or `app`

    Tests, virtual envs and build folders are skipped.

## Go live { #serve }

```bash
code-node --serve
```

This serves the page at `localhost:8765` and redraws it whenever a `.py` file changes. You keep your place on the
page. Serve another folder at the same time and it takes the next free port (8766, 8767, ...); the tab's title starts
with the folder's name, so you can tell them apart.

!!! tip "Worth knowing"
    If a save leaves a file that won't parse, the page shows the error, and the map comes back on the next good save.

??? more "How it watches"
    It checks file times twice a second, in plain Python, so it works on WSL too. It only listens on 127.0.0.1.
    The served page has a short script for the reload; saved pages have none.

## Large projects { #limits }

The graph shows 14 functions, 5 calls deep: starting from the entry point, it keeps taking the function that leads to
the most code (and to AWS, the web and environment variables), so the boxes are the ones doing the work, not the
nearest helpers. A function that only passes on to another one doesn't take a box: the arrow goes past it, dashed, and
says so ("via load_config()"). Each function's box lists up to 6 of its calls in the order they run; past 10
functions the boxes drop their docstrings, which are in the card that shows when you point at a box. A call not drawn
is dimmed in its box: click it, or **Open its calls ›**, and the graph starts from that function instead, with every
call it makes, and a path above it back up to the whole graph. **All** in
the graph's bar draws every function at once, for up to 150 of them. The step-by-step list always has all of them.

```bash
code-node --all                     # draw everything
code-node --depth 8 --functions 60  # your own limits
```

## Saving and sharing { #output }

```bash
code-node -o map.html --no-open     # save the page somewhere
code-node --mermaid > graph.md      # Mermaid, for a README or a PR
```

Without `-o`, pages are saved in `~/.cache/code-node/`. On WSL they open in your Windows browser.

Each step's card and each place in a box's code panel links to that line in VS Code (`--editor cursor` for Cursor).
The links hold the folder's full path, so pass `--editor none` for a page you'll share.

When the folder is in git, each function's hover card, code panel and step card say who changed it last, when, and in
which commit (a link to it on GitHub or GitLab), how many commits and people its lines come from, and how many of its
lines have changed since the last commit. The code panel also says it line by line, beside the code: point at a line
to see its commit. The gear in the panel's head turns that off. It's read with `git blame`, once per file;
`--no-git` leaves it out.

## Every option { #options }

| Option | Does |
| --- | --- |
| `path` | A folder, or a file to start from |
| `-e`, `--entry` | Where to start |
| `-l`, `--list` | List the starts |
| `--plugins` | List the plugins |
| `--serve`, `--port` | Live page (8765, or the next free port) |
| `--all` | Draw every function |
| `--depth`, `--functions` | Graph limits (5, 14) |
| `--mermaid` | Print Mermaid |
| `-o`, `--out` | Where to save |
| `--no-open` | Don't open a browser |
| `--platform`, `--lambda` | Run a platform's checks |
| `--editor` | What line links open: `vscode`, `cursor` or `none` |
| `--no-git` | Leave out who changed each function, and when |
