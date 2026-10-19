# Read the map

What each part of the page shows. The summary is at the top and the detail is below it.
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

!!! tip "Worth knowing"
    Point at a box and everything it isn't connected to fades out.

## Step by step { #outline }

The entry point's code, with only the lines that do something. Click a function to open it. The tag on each line
says what it does.

![The step-by-step list](images/outline-light.webp#only-light){ loading=lazy }
![The step-by-step list](images/outline-dark.webp#only-dark){ loading=lazy }

## Findings { #findings }

| Finding | Why it matters |
| --- | --- |
| No timeout | The call can hang forever |
| First page only | `Scan`, `Query`, `ListObjectsV2` quietly stop at 1 MB or 1,000 keys |
| Errors dropped | `except: pass` hides real failures |
| Secret in code | Anyone with the code has it |
| AWS call in a loop | A batch call does it in fewer requests |
| File won't parse | Imports of it fail |

??? more "Lambda-only checks"
    These come from the Lambda platform, so they run for a found Lambda handler, or any entry point with
    `--platform lambda`. Plain Python never gets them:

    - the handler can't take `(event, context)`
    - an `async def` handler
    - writing outside `/tmp`
    - a new client made on every call
    - sleeping, which Lambda bills for

    The other findings are worded for where the code runs: an HTTP request without a timeout "hangs" in plain Python,
    and on Lambda "waits until Lambda stops it at its timeout".
