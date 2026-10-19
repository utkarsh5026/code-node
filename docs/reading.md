# Read the map

What each part of the page shows. The numbers and findings are at the top and the detail is below them.
{ .gist }

![The top of a page: the numbers and the findings](images/summary-light.webp#only-light){ loading=lazy }
![The top of a page: the numbers and the findings](images/summary-dark.webp#only-dark){ loading=lazy }

## Top to bottom { #order }

| Part | Tells you |
| --- | --- |
| Cards | Where it starts, how many functions, which AWS services |
| Findings | What's worth fixing |
| Graph | The paths (a tab) |
| Step by step | Every line that matters, in the order it runs (the tab beside the graph) |
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

??? more "Click a box to read its code"
    A panel slides in from the right with the code the box is about, its lines numbered. A function shows whole,
    with the lines that make the calls its arrows show lit in amber. An AWS service, the web, the environment, the
    input and *At import* show a few lines around each place the code uses them. Close it with × or the browser's
    Back button. Like the rest of the page, it works without JavaScript.

## Step by step { #steps }

The tab beside the graph walks through the code in the order it runs, as a debugger steps through it.
{ .gist }

The list on the left has every line that does something: what runs when Python imports the code, then each call
from the entry point, with each of its own functions under the line that calls it. On the right is the function the
current step is in, with that line lit, and a card saying what the line does and which calls it's inside.

![The Step by step tab](images/steps-light.webp#only-light){ loading=lazy }
![The Step by step tab](images/steps-dark.webp#only-dark){ loading=lazy }

| Button | Goes to |
| --- | --- |
| Next | The next line that runs, into a function when the line calls one |
| Back | The step before |
| Step over | The next line in the same function, past what the line calls |
| Step out | Where the function returns to |

!!! tip "Worth knowing"
    Click a step, in the list or a numbered line in the code, then use the arrow keys to step through the rest.

??? more "How it works without JavaScript"
    Each step is a radio button and the buttons are its labels, so the arrow keys move between them as they do in any
    radio group. The CSS shows the card of the checked step and the code of the function it's in, and moves the lit
    line there, which slides when the next step is in the same function.

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
