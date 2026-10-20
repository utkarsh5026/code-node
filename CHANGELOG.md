# Changelog

Every change a user would notice, newest first ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)). Versions
follow [Semantic Versioning](https://semver.org/); before 1.0, a minor version may change what a command does.

## [Unreleased]

### Added

- A web platform for FastAPI, Flask and Django (`--platform web`, set on its own for an app it finds). What a
  route is called with is the request, read like a Lambda handler's event: a FastAPI route's parameters (from the
  path, the query, the body, `Query()`, `Header()`, `Annotated[...]`; not `Depends()`), a Flask view's URL values
  and `flask.request` (`args`, `form`, `get_json()`), and a Django view's `request` (`GET`, `POST`, `body`) and URL
  values. So SQL or a shell command built from a query string is flagged as injection, and the graph's first box is
  "The request" with the fields the code reads (`path.order_id`, `query.q`, `json.team`).
- Django's URL confs are entry points: a `urls.py` with `urlpatterns`, its `path()` and `re_path()` routes,
  `include()` (routes come out under the path they're included at), class-based views (`View.as_view()`, a route
  for each method) and Django REST framework routers (`router.register()`, a route for each ViewSet action). The
  site's URL conf is offered before an app's it includes. `django.db.connection.cursor()` is read by the SQL plugin.
- A web app's box in the graph shows its framework's logo (FastAPI, Flask or Django), on a white tile as other
  logos are, and the docs' "What code-node knows" figure lists the three under "Runs on".
- `examples/books-api`, a FastAPI app with a mistake for each thing the web platform finds, and a snapshot of
  its page.
- A call that blocks inside an `async def` route (requests, urllib, `time.sleep()`, boto3) is flagged: it holds up
  every other request on the worker's event loop. A connection opened on every request is too.
- Plugins that mix. Besides a platform (one per entry point), two new kinds of plugin stack: libraries, each turned
  on when the code imports it, and deploy files, each read when it's in the folder. `code-node --plugins` lists
  them, and other packages add their own through the `code_node.libraries` and `code_node.deploys` entry point
  groups.
- Library plugins for Redis, SQL (sqlite3, psycopg2, psycopg, PyMySQL, mysql-connector, asyncpg, SQLAlchemy),
  MongoDB (PyMongo, Motor) and the OpenAI and Anthropic SDKs. The graph draws a box for each service they reach
  (Redis, PostgreSQL, OpenAI) with what each call does (`SELECT products`, `SETEX receipt:{customer}`,
  `chat.completions.create gpt-4o-mini`), and Step by step says it ("Reads from PostgreSQL (SELECT products)").
- Deploy plugins for SAM / CloudFormation templates and `serverless.yml`. A function they name is an entry point,
  whatever it's called, and the Lambda checks run against what the file says: environment variables that aren't
  set, the Python it runs on, layers, its timeout, and AWS calls its role doesn't allow (marked "not allowed" in the
  graph, with the SAM policy template that would allow them).
- It follows text built from the input: SQL put together from the event is flagged "SQL injection" where it runs,
  and so is a shell command (`shell=True`, `os.system`). A name set to such text says so in Step by step.
- Findings across plugins: a client that has no timeout, worded for where it runs ("Lambda stops it at its 15 s
  timeout"); a connection opened on every call of a Lambda handler; a call in a loop that a batch call would do
  (`executemany()`, `mget()`, `insert_many()`, the Batch API); Redis `KEYS`.
- Logos are sharp on an ordinary (1x) screen. They come in two sizes, as favicons do: AWS's detailed service
  icons have a small mark too (the service's colour with a bold white symbol), which the page shows on a 1x screen,
  and the full art on a 2x one. Badges are 32 px, AWS's icons fill theirs instead of sitting small on a white tile,
  and other logos have less padding. The docs' figures, the home page graph and the screenshots pick the size they
  draw at.
- Real logos in the graph. AWS services (S3, DynamoDB, SNS, SQS, Lambda and about sixty more) and the services
  libraries reach (Redis, PostgreSQL, MySQL, SQLite, MongoDB, OpenAI, Anthropic, Kafka...) show their own logo in
  their box, in light and dark mode, where they had a line drawing; anything without one keeps it. The logos are
  gilbarbara/logos (CC0), kept as .svg files in the package (`src/code_node/report/logos/`), and a page embeds
  the ones it uses, so it still works offline. A library plugin can name one as
  its icon (`icon = "kafka-icon"`).
- Two new figures in the docs and the README, drawn with those logos: how the plugins mix on the cart example
  (each finding marked with the plugins that found it together), and every service, platform and deploy file
  code-node knows. Logos sit on a white tile in dark mode too, as they're drawn for one.
- `examples/cart-service`, a Lambda function in a SAM template that uses PostgreSQL, Redis, OpenAI and boto3, and a
  Plugins page in the docs drawn from it.

### Changed

- A web app's own class (`FastAPI()`, `Flask()`, `APIRouter()`, `Blueprint()`) now comes from the web platform, so
  an app found runs its checks. The summary no longer says "Each call runs app()" for an app object. Beside a step,
  a field of the input is said in its platform's word (`event body.id` for Lambda, `request query.q` for a web
  app), and the graph's input box is named for it when the kind of event can't be told ("The event", not "Its
  input").
- The graph has room to breathe and is drawn at its real size, no longer squeezed to the page's width. Gaps between
  columns widen with the arrows through them, boxes are spaced further apart, columns are wider so names show whole
  (a long method's name breaks after its class: `PluginManager.` / `_load_plugin()`), and the order with the fewest
  crossing arrows is kept. Arrows that skip columns from one box (the environment's, start-up's) or into one run as
  one line and part near the end, instead of each taking its own path, and the environment's and clients' arrows
  are quieter until you point at a box. A column too tall to take in is split into lanes side by side, so a big
  graph (`--functions 100`) is wide, not one long strip. Buttons over the graph zoom it (Auto, Fit, 100%, 150%)
  and open it full screen, without JavaScript.
- code-node now depends on PyYAML, to read deploy files.
- `--serve` also redraws when a deploy file (`template.yaml`, `serverless.yml`) changes.

- Step by step is easier to read. Each step in the list says what it does in plain words ("Takes `bucket` from the
  event", "Reads from S3 (GetObject)", "Goes into `read_orders()`") instead of a cut-off line of code, with step
  numbers in place of line numbers that jumped between files, and each function as a heading over its steps. A dot
  marks the steps that reach AWS or the web. The card is roomier: that sentence as its headline, then where it is
  and what it touches. Next is the one filled button, and Step over and Step out are now Skip call and Finish
  `read_orders()`.
- The graph picks its boxes by how much code each one leads to, not by how near it is: from the entry point it
  keeps taking the function that leads to the most lines (and AWS calls, HTTP requests and environment variables)
  below it. On code-node's own command it now draws `make_page`, `map_code`, `page_blocks` and `render_page`
  instead of small helpers, and the graph is less than half as tall.
- A box whose calls the graph leaves out says "+3 calls not drawn", and its code panel names them, instead of
  looking like it does nothing.
- It follows what Python calls for you: `super().__init__()` and other `super()` calls open the base class's method,
  reading a `@property` (or `cached_property`) runs its getter, and a `with` block on one of your classes runs its
  `__enter__` (what `as` names is what that returns) and, after the block, its `__exit__`.
- Console scripts come from every `pyproject.toml` in the folder, not only the root's, so a monorepo's commands
  (`libs/cli/pyproject.toml`) are found before its CI scripts.
- SyntaxWarnings from the code being read (`"\d"` in a plain string) no longer show in the terminal.
- It shows what it already knew about values. In Step by step, a line's card says what the names it sets now hold
  (`store` holds an OrderStore, `self.table` a DynamoDB Table) and where its AWS call's arguments come from
  (`Bucket ← env ARCHIVE_BUCKET`, `Key ← event Records[].s3.object.key`). A call's card says when it runs
  ("only when `check(order)`"). The text and Mermaid output say the same, and the graph's AWS boxes list the sources
  on hover.
- A function called only under an `if` says so in its graph box ("when args.serve"), from the `if` nearest around
  the call. Lines after `if not check(order): continue` (or `return`, `raise`, `break`) count as running only when
  `check(order)`, rather than always.

- The page is only two tabs now, Graph and Step by step. The title, the cards of numbers, the findings and the tables
  under the graph (AWS calls and their IAM policy, environment variables, the event, functions, imports, HTTP
  requests) are gone. The entry point and the folder sit at the right of the tab bar, which stays at the top as you
  scroll. The graph still marks a warning on a box, such as an HTTP request with no timeout.
- The graph and the steps are in tabs, Graph and Step by step, instead of one under the other.
- Step by step is now a walk through the code in the order it runs, as a debugger steps: every step in a list, and
  beside it the function the current step is in, its line lit, with a card saying what the line does and which calls
  it's inside. Next goes into each function a line calls, Step over and Step out skip past them, and once a step is
  clicked the arrow keys step through the rest. Click any numbered line in the code to jump to it. Still no
  JavaScript, and a step is as quick on a page with thousands of them.
- The paragraph summing up the code under the numbers is gone: the numbers, the findings and the graph say it.
- Code on the page is set in Cascadia Mono when it's installed (the usual monospace font otherwise).
- `code-node --serve` keeps the open tab and step when the page redraws.
- The graph's code panel makes room beside the graph, rather than moving the whole page.

- `code-node --serve` without `--port` takes the first free port from 8765, so you can serve several folders at
  once instead of the second one failing. The served tab's title starts with the folder's name. `--port N` still
  means exactly that port.

- Lambda is now a platform plugin on top of a generic reader. Plain Python code no longer gets any Lambda check or
  wording (a file written outside `/tmp` used to be marked amber in the graph), and Lambda handlers get the same
  page as before.
- `--platform NAME` runs a platform's checks whatever the entry point is; `--lambda` is short for
  `--platform lambda`. `EntryPoint.is_lambda` and `PageOptions.is_lambda` are now `platform` (`"lambda"` or `""`).

### Added

- Line links to your editor: each step's card ("line 36 ↗") and each place in a box's code panel ("open ↗") opens
  that line in VS Code, or in Cursor with `--editor cursor`. Inside WSL they open the Windows editor on the WSL
  files. `--editor none` leaves them out, and the folder's full path with them.

- The pages have a tab icon (code-node's logo), saved and served.

- Click a box in the graph to read its code in a panel on the right: a function whole, with the lines that make
  its calls lit, or a few lines around each place the code uses a service, a variable or its input. No JavaScript:
  the panel opens with CSS (`:target`), and Back closes it. `GraphNode.code` lists the lines (`CodeSpan`), and
  `page_blocks(..., sources=...)` takes the files to show them from.
- Platforms: subclass `code_node.Platform` to say what another place code runs adds (its entry points, what
  they're called with, its findings and wording), and add it with `register_platform` or a `code_node.platforms`
  entry point in a package's `pyproject.toml`.

## [0.1.0] - 2026-10-19

### Added

- `code-node [folder]` reads a folder of Python code with `ast` (nothing is run) and opens a page showing how it works
  from an entry point: a graph of what comes in, who calls whom and what each path reaches (AWS calls with their IAM
  permissions, HTTP requests, environment variables), each call step by step, findings, and tables.
- Entry points are found for you: `pyproject.toml` console scripts, Lambda handlers, FastAPI / Flask apps (each
  route), Typer apps (each command), what runs under `if __name__ == "__main__":`, and functions named `main`.
  When there are several, it asks which one.
- Start from a file with `code-node path/to/main.py` or `code-node main.py:function` (or `Class.method`), from a
  dotted name with `-e pkg.cli.main`, or search by part of a name with `-e save`.
- `code-node --serve` puts the page on http://localhost:8765 and redraws it whenever a `.py` file changes. The
  browser reloads at the same scroll position, and a page that can't be drawn says why until the next save.
- `--all` draws every function however deep; `--depth` and `--functions` set the limits; `--mermaid` prints the
  graph as Mermaid; `--list` lists the entry points.

[Unreleased]: https://github.com/utkarsh5026/code-node/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/utkarsh5026/code-node/releases/tag/v0.1.0
