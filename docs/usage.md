# Start

Install it. Run it in any Python repo. Get a map.
{ .gist }

## Install { #install }

```bash
pip install code-node-graph
```

Want it in every repo? Use `uv tool install code-node-graph` (or `pipx`). Needs Python 3.10+.

## Run it { #run }

```bash
cd your/repo
code-node
```

It finds where your code starts, asks which one, and opens the map. That's it.

## Pick where to start { #entry }

| You type | It starts at |
| --- | --- |
| `code-node` | It finds the starts and asks you |
| `code-node app/main.py` | That file's `main()` |
| `code-node app/main.py:run` | `run()` in that file |
| `code-node app/store.py:Store.save` | A method |
| `code-node -e pkg.cli.main` | A dotted name |
| `code-node -e save` | Anything with "save" in its name |
| `code-node --list` | Nothing. It just lists the starts |

??? more "What it finds on its own"
    Best first:

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

Opens `localhost:8765`. Save a `.py` file and the map redraws. Your scroll position stays put.

!!! tip "Worth knowing"
    Broke the code mid-edit? The page tells you what's wrong, then comes back on your next save.

??? more "How it watches"
    It checks file times twice a second. That's plain Python, and it works on WSL too. It only listens on
    127.0.0.1. The live page has a tiny script for the reload. Saved pages have none.

## Big repo? { #limits }

The graph shows the nearest 24 functions, 5 calls deep. The step-by-step list always has all of them.

```bash
code-node --all                     # draw everything
code-node --depth 8 --functions 60  # your own limits
```

## Save it, share it { #output }

```bash
code-node -o map.html --no-open     # save the page somewhere
code-node --mermaid > graph.md      # Mermaid, for a README or a PR
```

Pages land in `~/.cache/code-node/` by default. On WSL they open in your Windows browser.

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
| `--lambda` | Run the Lambda checks |
