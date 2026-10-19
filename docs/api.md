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
| `platform` | `"lambda"` for the Lambda checks |

You get a `CodeMap`:

| Field | Holds |
| --- | --- |
| `functions` | your functions that run |
| `aws` | AWS calls, with IAM permissions |
| `env` | env var names (never values) |
| `steps` | each call, step by step |
| `imports`, `routes` | imports, web routes, CLI commands |

## `code_graph(cmap)` { #code_graph }

Boxes (`nodes`) and arrows (`edges`). `max_functions=24` and `max_depth=5` set how much it draws. `hidden` counts
what it left out. `.mermaid()` writes it as Mermaid.
