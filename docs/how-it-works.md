# Under the hood

How code-node follows your code without running it, and what it can't see.
{ .gist }

## How it reads { #reader }

1. **Load** the entry point's file, the way Python imports it.
2. **Read** each line with Python's `ast` module.
3. **Remember** what each name holds: a boto3 client, one of your classes, an env var.
4. **Follow** calls into your own functions, up to 8 deep.
5. **Name** each AWS call from botocore's files on disk. No request is made.
6. **Ask** a [library plugin](plugins.md) about each call through a client it knows: a Redis GET, a SQL INSERT.

So `self.store.save()` opens `Store.save`. And `s3.get_object(...)` becomes **S3 GetObject**, which needs
`s3:GetObject`.

Along the way it knows what each name holds and why a line runs: the step-by-step card says `bucket` holds
`event Records[].s3.bucket.name`, that `put_object`'s `Bucket` comes from `env ARCHIVE_BUCKET`, and that
`store.save(order)` runs only when `check(order)` (it comes after `if not check(order): continue`). A function called
only under an `if` says so in its graph box.

It also follows what Python calls for you: `super().__init__()` opens the base class's method, reading `obj.size`
runs a `@property` getter, and `with Store() as s:` runs `Store.__enter__` (and `s` is what it returns), the block,
then `Store.__exit__`.

## What it can't see { #limits }

| Blind spot | Example |
| --- | --- |
| Values from outside | a client a library hands back |
| Run-time choices | a function picked from a dict |
| Library code | only your folder is read |
| Dynamic tricks | `getattr(obj, name)`, `exec` |

!!! tip "Worth knowing"
    A map can miss a call, but everything on it is really in your code. The note at the bottom of each page says
    when the map was cut short.

## The pieces { #layers }

| Step | Module | In → out |
| --- | --- | --- |
| Folder | `project` | path → files, deploy files, starts |
| Plugins | `platforms`, `libraries`, `deploys` | where it runs, what it calls through, how it's deployed |
| Reader | `analysis.reader` | files → `CodeMap` |
| Graph | `analysis.graph` | `CodeMap` → `CodeGraph` |
| Drawing | `report.graph` | `CodeGraph` → SVG |
| Page | `report.build` | everything → HTML |

??? more "Why two data types?"
    `CodeMap` is what the code does. `CodeGraph` is boxes and arrows. A new view (an editor panel, an interactive
    canvas) only needs a `CodeGraph`.

## Where it came from { #origin }

It started as `how_it_works()` in [aws-analyzer](https://github.com/utkarsh5026/aws-analyzer), which maps deployed
Lambda functions. code-node does the same for any Python repo.
