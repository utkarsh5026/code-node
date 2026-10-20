# Read the map

What each tab of the page shows. The page is two tabs, with the entry point and the folder at the right of them.
{ .gist }

## The tabs { #order }

| Tab | Tells you |
| --- | --- |
| Graph | The paths: what comes in, who calls whom, and what it reaches |
| Step by step | Every line that matters, in the order it runs |

## The graph { #graph }

Read it left to right.

| Column | What's there |
| --- | --- |
| **Comes in** | What the code gets: its input, env vars |
| **Entry** | Where it starts, plus what runs at import |
| **Calls** | Your functions. Further right means deeper |
| **Reaches** | AWS services, the services its libraries reach (Redis, PostgreSQL, OpenAI), and the web |

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
| <span style="color:#f59e0b">●</span> amber | a warning is about it, such as an HTTP request with no timeout |

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

The list on the left has every line that does something, each said in a few plain words ("Takes `bucket` from the
event", "Reads from S3 (GetObject)"): what runs when Python imports the code, then each call from the entry point,
with each of its own functions as a heading over its steps. A dot marks the steps that reach AWS or the web, in the
graph's colours. On the right is a card saying what the current step does and which calls it's inside, and under it
the function's code with that line lit.

![The Step by step tab](images/steps-light.webp#only-light){ loading=lazy }
![The Step by step tab](images/steps-dark.webp#only-dark){ loading=lazy }

| Button | Goes to |
| --- | --- |
| Next | The next line that runs, into a function when the line calls one |
| Back | The step before |
| Skip call | The next line in the same function, past what the line calls (a debugger's step over) |
| Finish | Where the function returns to (step out) |

!!! tip "Worth knowing"
    Click a step, in the list or a numbered line in the code, then use the arrow keys to step through the rest.

??? more "How it works without JavaScript"
    Each step is a radio button and the buttons are its labels, so the arrow keys move between them as they do in any
    radio group. The CSS shows the card of the checked step and the code of the function it's in, and moves the lit
    line there, which slides when the next step is in the same function.
