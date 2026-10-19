# Read the map

The answer is at the top. The details are below it.
{ .gist }

![The top of a page: numbers, a summary, the findings](images/summary-light.webp#only-light){ loading=lazy }
![The top of a page: numbers, a summary, the findings](images/summary-dark.webp#only-dark){ loading=lazy }

## Top to bottom { #order }

| Part | Tells you |
| --- | --- |
| Cards | Where it starts, how many functions, which AWS services |
| Summary | What it does, in a few sentences |
| Findings | What's worth fixing |
| Graph | The paths |
| Step by step | Every line that matters |
| Tables | AWS calls, env vars, functions, imports |

## The graph { #graph }

Read it left to right.

| Column | What's there |
| --- | --- |
| **Comes in** | What the code gets: its input, env vars |
| **Entry** | Where it starts, plus what runs at import |
| **Calls** | Your functions. Further right means deeper |
| **Reaches** | AWS services and the web |

![A code-node graph](images/graph-light.webp#only-light){ loading=lazy }
![A code-node graph](images/graph-dark.webp#only-dark){ loading=lazy }

### Arrow colours { #arrows }

| Arrow | Means |
| --- | --- |
| <span style="color:#9097a3">━━</span> grey | calls |
| <span style="color:#3b82f6">━━</span> blue | reads |
| <span style="color:#ea580c">━━</span> orange | writes |
| <span style="color:#db2777">━━</span> pink | sends, or an HTTP call (dashed) |
| <span style="color:#6b7cff">╍╍</span> dashed | an env var |
| ↻ | happens in a loop |
| <span style="color:#f59e0b">●</span> amber | a finding is about it |

!!! tip "Try this"
    Point at a box. Everything it isn't connected to fades out.

## Step by step { #outline }

The entry point's code, showing only the lines that do something. Click a function to open it. Tags say what each
line does.

![The step-by-step list](images/outline-light.webp#only-light){ loading=lazy }
![The step-by-step list](images/outline-dark.webp#only-dark){ loading=lazy }

## Findings { #findings }

| Finding | Why care |
| --- | --- |
| No timeout | The call can hang forever |
| First page only | `Scan`, `Query`, `ListObjectsV2` quietly stop at 1 MB or 1,000 keys |
| Errors dropped | `except: pass` hides real failures |
| Secret in code | Anyone with the code has it |
| AWS call in a loop | A batch call does it in fewer requests |
| File won't parse | Imports of it fail |

??? more "Lambda-only checks"
    These only run for Lambda handlers:

    - the handler can't take `(event, context)`
    - an `async def` handler
    - writing outside `/tmp`
    - a new client made on every call
