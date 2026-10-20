<div align="center">

<img src="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/logo.svg" width="72" alt="">

# code-node

**See how Python code works, without running it.**

[![PyPI](https://img.shields.io/pypi/v/code-node-graph)](https://pypi.org/project/code-node-graph/)
[![Python](https://img.shields.io/pypi/pyversions/code-node-graph)](https://pypi.org/project/code-node-graph/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

[Docs](https://utkarsh5026.github.io/code-node/) · [Plugins](https://utkarsh5026.github.io/code-node/plugins.html) · [How it works](https://utkarsh5026.github.io/code-node/how-it-works.html) · [Changelog](CHANGELOG.md)

</div>

Point it at a repo. Get a page showing where the code starts, who calls whom, and what each path touches: AWS, HTTP,
environment variables.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/graph-dark.webp">
  <img alt="code-node's graph of a small Lambda function: an S3 event comes in, the handler calls its own functions, and they reach S3, DynamoDB, SNS and the web" src="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/graph-light.webp">
</picture>

## Install

```bash
pip install code-node-graph        # or: uv tool install code-node-graph
cd your/repo && code-node
```

> [!NOTE]
> Nothing is run. Code is read with `ast`, AWS operations come from botocore's models on disk. No imports, no requests.

## What you get

| | |
| --- | --- |
| 🗺️ **Graph** | What comes in, who calls whom, what each path reaches. AWS calls coloured by kind (read, write, send, run); ↻ marks loops |
| 👣 **Step by step** | Walk the code in run order, like a debugger: Next, Skip call, Finish, arrow keys |
| 🔌 **Plugins** | boto3, Redis, SQL (sqlite3, psycopg, PyMySQL, asyncpg, SQLAlchemy), MongoDB, OpenAI, Anthropic |
| 📄 **Deploy checks** | Reads SAM `template.yaml` / `serverless.yml`: unset variables, IAM calls the role won't allow, timeouts that don't fit |
| 🚨 **Findings** | SQL or shell commands built from input, clients with no timeout, queries in loops |
| 🧜 **Mermaid** | Paste the graph into Markdown, a wiki or a PR |
| 🔁 **Live** | `--serve` redraws on every save |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/steps-dark.webp">
  <img alt="The Step by step tab: every step in the order the code runs on the left, and on the right the function the current one is in, its line lit" src="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/steps-light.webp">
</picture>

## Usage

```bash
code-node                              # find entry points and pick one
code-node --list                       # just list them
code-node src/app/main.py:run          # start from a function
code-node src/app/store.py:Store.save  # ...or a method
code-node -e save                      # part of a name
code-node --serve                      # live page on localhost:8765
code-node --mermaid                    # print the graph as Mermaid
```

<details>
<summary><b>Entry points it finds</b></summary>

Console scripts in any `pyproject.toml` (monorepos too), functions named in SAM / Serverless files, Lambda handlers,
FastAPI / Flask routes, Django `urls.py` files, Typer commands, `if __name__ == "__main__":` blocks, and functions named
`main`. Test files are skipped. A web app's routes are read as called with the request, so SQL built from a query
string is flagged.

</details>

<details>
<summary><b>All options</b></summary>

| Option | What it does |
| --- | --- |
| `path` | Folder to read, or a file to start from (`main.py`, `main.py:function`) |
| `-e`, `--entry` | `module.function`, `module.Class.method`, `file.py[:function]`, or part of a name |
| `-l`, `--list` | List entry points and stop |
| `--plugins` | List platforms, libraries and deploy files and stop |
| `--all` | Draw every function (default: 24 functions, 5 calls deep) |
| `--depth N`, `--functions N` | Your own limits |
| `--serve`, `--port N` | Serve on localhost, redraw on change |
| `--mermaid` | Print the graph as Mermaid |
| `-o`, `--out`, `--no-open` | Where to save (default `~/.cache/code-node/`), and whether to open it |
| `--platform NAME`, `--lambda` | Run a platform's checks on any entry point |
| `--editor vscode\|cursor\|none` | Editor the line links open (default `vscode`, WSL-aware) |
| `--no-git` | Leave out what git says about each function (who changed it last, when, in which commit) |

</details>

<details>
<summary><b>From Python</b></summary>

```python
from code_node import code_graph, map_code, read_project

project = read_project(".")
cmap = map_code(project.files, "pkg.cli.main", libraries=project.libraries())
print([call.label for call in cmap.aws])
print(code_graph(cmap).mermaid())
```

</details>

## Plugins that mix

One platform, any number of libraries and deploy files, checked together. On
[`examples/cart-service`](examples/cart-service):

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/plugins-mix-dark.svg">
  <img alt="The cart example: template.yaml, AWS Lambda and its libraries read on_checkout(), and together find a role that doesn't allow two AWS calls, two unset variables, SQL injection, a client with no timeout, a connection on every call and a query run once per item" src="https://raw.githubusercontent.com/utkarsh5026/code-node/main/docs/images/plugins-mix-light.svg">
</picture>

## Limits

It can't follow values from outside the code (a client a library hands back, a function picked from a registry at
run time), installed libraries' own code, or `getattr` with a computed name. **A page can miss calls, but everything
it shows is in the code.**

## Develop

```bash
make install    # .venv with the dev tools (needs uv)
make check      # everything CI runs
make shots      # remake screenshots (needs Chrome)
```

`python makefile.py <task>` does the same on any OS.

---

<sub>Extracted from [aws-analyzer](https://github.com/utkarsh5026/aws-analyzer)'s `how_it_works()`. Apache 2.0.</sub>
