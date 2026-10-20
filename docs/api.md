# Python API

The functions behind the command, for your own scripts.
{ .gist }

```python
from code_node import code_graph, entry_points, map_code, read_project

project = read_project(".")                      # your .py files
starts = entry_points(project)                   # where the code starts, best first

cmap = map_code(project.files, starts[0].name, libraries=project.libraries())
print([call.label for call in cmap.aws])         # ['S3 GetObject', 'DynamoDB PutItem', ...]

print(code_graph(cmap).mermaid())                # the graph as Mermaid
```

## `map_code(files, entry)` { #map_code }

| Argument | What it is |
| --- | --- |
| `files` | `{path: source}` |
| `entry` | `module.function`, `module.Class.method` or `module.app` |
| `libraries` | installed packages (`project.libraries()`) |
| `file` | the entry's file, if more than one could match |
| `max_depth` | how deep to follow calls (8) |
| `platform` | where it runs: `"lambda"` for the Lambda checks, `""` (default) for plain Python |
| `deployment` | what a deploy file says about it (`find_deployment`), checked against the code |

You get a `CodeMap`:

| Field | Holds |
| --- | --- |
| `functions` | your functions that run |
| `aws` | AWS calls, with IAM permissions |
| `library_calls` | calls through the libraries plugins know: Redis, SQL, MongoDB, OpenAI... |
| `env` | env var names (never values) |
| `steps` | each call, step by step |
| `imports`, `routes` | imports, web routes, CLI commands |

An `EntryPoint` from `entry_points` has a `platform` too (`"lambda"` for a Lambda handler): pass it on with
`platform=start.platform`.

## `code_graph(cmap)` { #code_graph }

Boxes (`nodes`) and arrows (`edges`). `max_functions=24` and `max_depth=5` set how much it draws. `hidden` counts
what it left out. `.mermaid()` writes it as Mermaid.

## Platforms { #platforms }

Platforms are one of three kinds of plugin. Libraries and deploy files, which stack, are on [Plugins](plugins.md).

The reader, the findings and the graph are for any Python. A platform adds what's different where the code runs:
which functions are its entry points, what they're called with, its own findings, and the wording of the general
ones. AWS Lambda is one, in `code_node/platforms/aws_lambda.py`, and web apps (FastAPI, Flask, Django) another, in
`code_node/platforms/web.py`. Add your own by subclassing `Platform`:

```python
import ast

from code_node import Platform, register_platform


class Worker(Platform):
    name = "worker"                  # --platform worker
    title = "Job runner"
    inputs = ("event",)              # the entry point is called with one argument: its fields are read
    input_name = "the job"

    def find_entries(self, module: str, tree: ast.Module):
        return [(n.name, n.lineno, "a job") for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name.startswith("job_")]

    def findings(self, cmap):
        return [("info", "...")]


register_platform(Worker())
```

??? more "Every hook"
    | Override | What it says |
    | --- | --- |
    | `name`, `title` | Its `--platform` name, and how people call it |
    | `inputs`, `input_name`, `draws_input` | What the entry point is called with, and whether the graph draws it |
    | `input_word` | What a field of the input is said to be read from beside a step (`event`, `request`) |
    | `route_inputs(function, path, imports, bound)` | What each parameter of a function a route runs holds from the input: `{"order_id": ("path", "order_id")}` |
    | `input_objects`, `input_aliases` | Names from a library that hold the input (`flask.request`), and its methods that give back part of it (`get_json`) |
    | `started` | When code at import runs ("When Lambda starts it (once per cold start)") |
    | `web_apps` | App classes whose routes are entry points of this platform (`Chalice`, `FastAPI`) |
    | `find_entries(module, tree)` | Its entry points in a module |
    | `input_kind(fields)` | What sends the input ("an SQS batch") |
    | `hang`, `lost_error`, `import_error`, `install`, `missing_entry` | Wording of the general findings |
    | `entry_findings(cmap)`, `findings(cmap)` | Its own findings: about the entry point (marked on its box), and the rest |
    | `marks(cmap)` | Function boxes its findings mark amber |
    | `entry_icon(cmap)` | The logo on the entry point's box (`"fastapi-icon"`), from `report/logos/` |

!!! tip "Worth knowing"
    A package installed next to code-node adds its platform to the command, with no `register_platform` call, by
    naming it in its `pyproject.toml`:

    ```toml
    [project.entry-points."code_node.platforms"]
    worker = "my_package.worker:Worker"
    ```
