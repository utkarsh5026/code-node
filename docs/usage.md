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

    - console scripts in `pyproject.toml`
    - Lambda handlers: `def handler(event, context)`
    - FastAPI / Flask apps: every route
    - Typer apps: every command
    - whatever runs under `if __name__ == "__main__":`
    - functions called `main`, `run`, `cli` or `app`

    Tests, virtual envs and build folders are skipped.

## Go live { #serve }

```bash
code-node --serve
```

This serves the page at `localhost:8765` and redraws it whenever a `.py` file changes. You keep your place on the
page.

!!! tip "Worth knowing"
    If a save leaves a file that won't parse, the page shows the error, and the map comes back on the next good save.

??? more "How it watches"
    It checks file times twice a second, in plain Python, so it works on WSL too. It only listens on 127.0.0.1.
    The served page has a short script for the reload; saved pages have none.

## Large projects { #limits }

The graph shows the nearest 24 functions, 5 calls deep. The step-by-step list always has all of them.

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

## Every option { #options }

| Option | Does |
| --- | --- |
| `path` | A folder, or a file to start from |
| `-e`, `--entry` | Where to start |
| `-l`, `--list` | List the starts |
| `--serve`, `--port` | Live page (8765) |
| `--all` | Draw every function |
| `--depth`, `--functions` | Graph limits (5, 24) |
| `--mermaid` | Print Mermaid |
| `-o`, `--out` | Where to save |
| `--no-open` | Don't open a browser |
| `--platform`, `--lambda` | Run a platform's checks |
