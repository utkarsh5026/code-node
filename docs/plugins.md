# Plugins

How code-node mixes plugins: one for where the code runs, one for each library it calls through, one for each deploy
file in the folder, and how to write your own.
{ .gist }

## Three kinds { #kinds }

| Kind | How many | Answers | Built in |
| --- | --- | --- | --- |
| **Platform** | one per entry point | where it runs: its entry points, what they're called with, its checks | AWS Lambda |
| **Library** | every one the code imports | what a library's calls reach: a box for each service, with what each call does | Redis, SQL (sqlite3, psycopg2, psycopg, PyMySQL, mysql-connector, asyncpg, SQLAlchemy), MongoDB (PyMongo, Motor), OpenAI and Anthropic |
| **Deploy file** | every one in the folder | what the deploy says: the handler, the Python, the timeout, the variables, what the role allows | AWS SAM / CloudFormation (`template.yaml`), Serverless Framework (`serverless.yml`) |

None of them needs a flag. A library plugin turns on when the code imports one of its modules, and a deploy plugin
when its file is in the folder. `code-node --plugins` lists what's installed.

![What code-node knows: AWS through boto3, PostgreSQL, MySQL, SQLite, MongoDB, Redis, OpenAI, Anthropic, AWS Lambda,
plain Python, AWS SAM and Serverless](images/reaches-light.svg#only-light){ .cn-figure loading=lazy }
![What code-node knows: AWS through boto3, PostgreSQL, MySQL, SQLite, MongoDB, Redis, OpenAI, Anthropic, AWS Lambda,
plain Python, AWS SAM and Serverless](images/reaches-dark.svg#only-dark){ .cn-figure loading=lazy }

## What they find together { #together }

Each plugin adds to the same map, so the checks see all of it. These come from
[`examples/cart-service`](https://github.com/utkarsh5026/code-node/tree/main/examples/cart-service), a Lambda
function declared in `template.yaml` that uses PostgreSQL, Redis, OpenAI and boto3. Each finding is marked with the
plugins that found it together:

![The cart example: template.yaml, AWS Lambda and its libraries read on_checkout(), and together find six
problems](images/plugins-mix-light.svg#only-light){ .cn-figure loading=lazy }
![The cart example: template.yaml, AWS Lambda and its libraries read on_checkout(), and together find six
problems](images/plugins-mix-dark.svg#only-dark){ .cn-figure loading=lazy }

```console
$ code-node examples/cart-service --list
1 entry point in examples/cart-service:
   1. cart.app.on_checkout  CheckoutFunction in template.yaml  (cart/app.py:20)
$ code-node examples/cart-service --no-open
cart.app.on_checkout: 5 functions, 2 AWS calls, 4 through libraries (PostgreSQL, OpenAI, Redis)
Deployed as CheckoutFunction in template.yaml
```

| Plugins | What they find |
| --- | --- |
| SAM + Lambda | `on_checkout()` is an entry point, though it isn't called `handler()` |
| SAM + Lambda | `RECEIPTS_TABLE` and `TOPIC_ARN` aren't set on CheckoutFunction, and the code reads them with `os.environ[...]` |
| SAM + Lambda + boto3 | Its role has only DynamoDBReadPolicy, so DynamoDB PutItem and SNS Publish fail with AccessDenied: add DynamoDBWritePolicy and SNSPublishMessagePolicy |
| SQL + the event | The DELETE in `clear_cart()` puts `event body (JSON).customer` into the SQL text: SQL injection |
| SQL + a loop | The SELECT in `price()` runs once per item in the cart |
| OpenAI + SAM + Lambda | The OpenAI client has no timeout, so it waits up to 10 minutes a try, and Lambda stops the run at its 15 s timeout |
| SQL + Lambda | It opens a new PostgreSQL connection on every call, instead of once for warm calls to reuse |

![The cart example's graph](images/plugins-light.webp#only-light){ loading=lazy }
![The cart example's graph](images/plugins-dark.webp#only-dark){ loading=lazy }

The graph marks each one where it is: PutItem and Publish say "not allowed", the variables say "not set", and the
DELETE says "SQL injection". In Step by step, a name set to text built from the input says so (`query` holds "text
built from event body (JSON).user"), and each step it reaches is flagged.

!!! tip "Worth knowing"
    A role code-node can't read (one made elsewhere, a managed policy it doesn't know, a SAM connector) leaves
    permissions unchecked rather than guessed: it never says a call is denied unless the file says so.

## Write a library plugin { #library }

A library plugin says what the library's functions give the code (a `Handle` the reader then tracks through names,
arguments and attributes) and what each call on one does (a `Use`):

```python
from code_node.libraries import Handle, Library, Use, register_library


class Kafka(Library):
    name = "kafka"
    title = "Kafka"
    modules = ("kafka",)            # turns on when the code imports kafka
    icon = "queue"

    def make(self, name, call):     # kafka.KafkaProducer(...)
        if name == "kafka.KafkaProducer":
            return Handle("producer", "Kafka", opens=True)

    def call(self, handle, method, call):   # producer.send("orders", ...)
        if method == "send":
            return Use("send", "sends", call.shown(0, "topic"))


register_library(Kafka())
```

??? more "Every hook"
    | Hook | What it says |
    | --- | --- |
    | `make(name, call)` | What a function or class of its modules gives (`Handle`) or does (`Use`) |
    | `attribute(handle, name)`, `item(handle, key)` | Part of a handle: `client.shop`, `client["shop"]` |
    | `call(handle, method, call)` | What a method does, or the handle it gives (a cursor) |
    | `describe(handle)` | What a name holding it holds: "a Redis client" |
    | `findings(cmap, calls)` | Its own findings |

    A `Use` can set `flag` and `why` (a warning on the call, its box and its step), `batch` (what to use instead
    when it runs in a loop) and `gives` (the handle it returns). A `Handle` can set `opens` (better made once) and
    `waits` and `fix` (it has no timeout). `call` tells it the arguments: `value()` for a literal, `shown()` for
    how a box lists it, `text()` and `built()` for SQL and other text, and `inputs()` for what from the entry
    point's input reached that argument, through any names on the way.

## Write a deploy plugin { #deploy }

A deploy plugin reads its files and returns a `Deployment` for each function: the Python file and function it starts
from, and what the file says about it. Its platform's checks run against that.

```python
from code_node.analysis.model import Deployment
from code_node.deploys import Deploy, register_deploy


class Zappa(Deploy):
    name = "zappa"
    title = "Zappa"
    files = ("zappa_settings.json",)

    def deployments(self, files, code):
        ...  # [Deployment("api", "zappa_settings.json", "zappa", "app.py", "handler", runtime="python3.12")]


register_deploy(Zappa())
```

Platforms are on the [Python API](api.md#platforms) page.

!!! tip "Worth knowing"
    A package installed next to code-node adds its plugins to the command by naming them in its `pyproject.toml`:

    ```toml
    [project.entry-points."code_node.libraries"]
    kafka = "my_package.kafka:Kafka"

    [project.entry-points."code_node.deploys"]
    zappa = "my_package.zappa:Zappa"
    ```
