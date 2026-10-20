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
  to see only what it's joined to; click it to read its code in a panel on the right.
- **Every call, step by step.** In a tab beside the graph, walk through the code in the order it runs, as a
  debugger steps: every line that does something in a list, said in plain words, and the function it's in with that
  line lit. Next goes into each function it calls, Skip call and Finish skip past them, and once you've clicked a
  step the arrow keys move through the rest.
- **The graph as Mermaid**, to paste in a Markdown file, a wiki or a pull request.
- **Plugins that mix.** Besides boto3, it follows Redis, SQL databases (sqlite3, psycopg, PyMySQL, asyncpg,
  SQLAlchemy), MongoDB, and the OpenAI and Anthropic SDKs, a box for each service they reach. It reads a SAM
  `template.yaml` or a `serverless.yml` in the folder, and checks the code against it: a variable that isn't set,
  an AWS call the role doesn't allow, a client that waits longer than the function's timeout. SQL or a shell
  command built from the input is flagged wherever it's run. [Plugins](https://utkarsh5026.github.io/code-node/plugins.html)
  shows them on [`examples/cart-service`](examples/cart-service), and how to write your own.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/page-dark.webp">
  <img alt="A code-node page: the graph in its tab, with Step by step beside it" src="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/page-light.webp">
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

It finds console scripts in every `pyproject.toml` (a monorepo's too), the functions a SAM template or
`serverless.yml` names, Lambda handlers, FastAPI / Flask apps (each route), Typer apps (each command), what runs under
`if __name__ == "__main__":`, and functions named `main`. Test files are skipped.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/steps-dark.webp">
  <img alt="The Step by step tab: every step in the order the code runs on the left, and on the right the function the current one is in, its line lit, with Back, Next and Finish" src="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/steps-light.webp">
</picture>

## Plugins that mix

A platform says where the code runs; library plugins (Redis, SQL, MongoDB, OpenAI and Anthropic) and deploy files
(SAM, Serverless) stack on top, and the checks see all of them at once. On
[`examples/cart-service`](examples/cart-service):

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/plugins-mix-dark.svg">
  <img alt="The cart example: template.yaml, AWS Lambda and its libraries read on_checkout(), and together find a role that doesn't allow two AWS calls, two unset variables, SQL injection, a client with no timeout, a connection on every call and a query run once per item" src="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/plugins-mix-light.svg">
</picture>

## Keep it open while you work

```bash
code-node --serve                      # http://localhost:8765 (or the next free port), redrawn on every save
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
| `--plugins` | List the platforms, libraries and deploy files it reads code with, then stop |
| `--all` | Draw every function, however deep (by default the graph shows 24, 5 calls deep: the ones that lead to the most code) |
| `--depth N`, `--functions N` | Your own limits |
| `--serve`, `--port N` | Serve the page on localhost (8765, or the next free port) and redraw it whenever a `.py` file (or a deploy file) changes |
| `--mermaid` | Print the graph as Mermaid |
| `-o`, `--out`, `--no-open` | Where to save the page (default `~/.cache/code-node/`), and whether to open it |
| `--platform NAME`, `--lambda` | Run a platform's checks (`lambda`) on any entry point. A found Lambda handler (or one a deploy file names) sets it; anything else is plain Python |
| `--editor vscode\|cursor\|none` | The editor the page's line links open (default `vscode`; links into WSL open in Windows' editor) |

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
make install    # .venv with code-node and the dev tools (needs uv)
make check      # lint, tests, the example, the docs build and the package, as CI runs them
make shots      # remake the screenshots (needs Chrome)
```

`make` alone lists the rest. `python makefile.py` has the same tasks, drawn with rich, and runs on Windows too
(`python makefile.py check`; with no `.venv` yet, `uv run makefile.py install`).

code-node was extracted from [aws-analyzer](https://github.com/utkarsh5026/aws-analyzer)'s `how_it_works()`.
Apache 2.0.
