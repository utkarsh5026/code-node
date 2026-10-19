# code-node

**See how Python code works, without running it.** Point `code-node` at a repository. It opens a page that shows
where the code starts, which of its functions call which, and what each path ends up touching: AWS, the web,
environment variables.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/graph-dark.webp">
  <img alt="code-node's graph of a small Lambda function: an S3 event comes in, the handler calls its own functions, and they reach S3, DynamoDB, SNS and the web" src="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/graph-light.webp">
</picture>

```bash
pip install code-node-graph        # or: uv tool install code-node-graph
cd your/repo && code-node
```

Nothing is run. The code is read with Python's `ast` module, and AWS operations are named from botocore's service
models on disk. No module is imported and no request is made.

**[Docs](https://utkarsh5026.github.io/code-node/)** · [Changelog](CHANGELOG.md)

## What you get

- **A graph of the paths.** What comes in, who calls whom, and what each path reaches, arranged left to right. AWS
  calls are coloured by what they do (reads, writes, sends, runs) and a ↻ marks calls made in a loop. Point at a box
  to see only what it's joined to.
- **Every call, step by step.** The entry point's code line by line, with each function it calls folded under the
  line that calls it, and every line tagged with what it does.
- **What's worth fixing.** HTTP requests with no timeout, AWS list calls that only read the first page, errors that
  get dropped, secrets written in the code, AWS calls in a loop that a batch call would do in fewer requests.
- **The AWS side.** Every boto3 call it can follow with the IAM permission it needs, and a policy to start from.
- **Tables** of environment variables (names only), functions, and imports, plus the graph as Mermaid.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/summary-dark.webp">
  <img alt="The top of a page: cards with the numbers that matter, a summary in sentences, and the findings" src="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/summary-light.webp">
</picture>

## Pick where to start

Every page follows the code from one **entry point**.

```bash
code-node                              # finds the entry points in this folder, and asks which one
code-node --list                       # just list them

code-node src/app/main.py              # start from a file: what its __main__ block runs, or pick a function
code-node src/app/main.py:run          # a function in that file
code-node src/app/store.py:Store.save  # a method

code-node -e pkg.cli.main              # a dotted name
code-node -e save                      # part of a name: it lists the matches
```

It finds `pyproject.toml` console scripts, Lambda handlers, FastAPI / Flask apps (each route), Typer apps (each
command), what runs under `if __name__ == "__main__":`, and functions named `main`. Test files are skipped.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/outline-dark.webp">
  <img alt="The step-by-step outline: the handler's lines, each tagged with what it does, with the functions it calls folded under them" src="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/outline-light.webp">
</picture>

## Keep it open while you work

```bash
code-node --serve                      # http://localhost:8765, redrawn every time you save a .py file
code-node src/app/main.py --serve --port 9000
```

The server watches the folder. When a file changes it reads the code again, redraws the page, and the browser reloads
at the same scroll position. If the code can't be drawn, the page says why and comes back on the next save.

## Options

| Option | What it does |
| --- | --- |
| `path` | The folder to read, or a file to start from (`main.py`, `main.py:function`) |
| `-e`, `--entry` | Where to start: `module.function`, `module.Class.method`, `file.py[:function]`, or part of a name |
| `-l`, `--list` | List the entry points, then stop |
| `--all` | Draw every function, however deep (by default the graph shows the nearest 24, 5 calls deep) |
| `--depth N`, `--functions N` | Your own limits |
| `--serve`, `--port N` | Serve the page on localhost (8765) and redraw it whenever a `.py` file changes |
| `--mermaid` | Print the graph as Mermaid |
| `-o`, `--out`, `--no-open` | Where to save the page (default `~/.cache/code-node/`), and whether to open it |
| `--platform NAME`, `--lambda` | Run a platform's checks (`lambda`) on any entry point. A found Lambda handler sets it; anything else is plain Python |

## From Python

```python
from code_node import code_graph, map_code, read_project

project = read_project(".")
cmap = map_code(project.files, "pkg.cli.main", libraries=project.libraries())
print([call.label for call in cmap.aws])
print(code_graph(cmap).mermaid())
```

## What it can't see

Calls through values from outside the code it reads (a client a library hands back, a function picked at run time
from a registry), installed libraries' own code, and dynamic tricks like `getattr` with a computed name. A page can
miss calls, but everything it shows is in the code. [How it works](https://utkarsh5026.github.io/code-node/how-it-works.html)
explains the rest.

## Develop

```bash
uv venv && uv pip install -e . -r requirements-dev.txt
.venv/bin/python -m pytest && .venv/bin/ruff check .
.venv/bin/python scripts/shots.py      # remake the screenshots (needs Chrome)
```

code-node was extracted from [aws-analyzer](https://github.com/utkarsh5026/aws-analyzer)'s `how_it_works()`.
Apache 2.0.
