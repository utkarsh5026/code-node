# Plugin roadmap

What each of code-node's plugins knows today, what each could add, and which new plugins would let it read more of
the Python repos people have. Written from the code at `131c53d`; file references are to `src/code_node/`.

Each idea says what it would find and why that matters, and is sized **S** (a hook already exists; a day or less),
**M** (a new hook or a new plugin of a kind that exists), or **L** (a new ecosystem, or a change to the reader).

## The short version

The ten that would do the most, best first:

| # | What | Kind | Why | Size |
| --- | --- | --- | --- | --- |
| 1 | A web platform: FastAPI, Flask, Django | Platform | Most Python services aren't Lambda handlers. Routes are already found (`project.py` `_WEB_APPS`, the reader's `routes`), but they're read as plain Python, so a route's parameters aren't "the input" and SQL injection from a query string is never flagged | M |
| 2 | Lambda checks that catch real outages: SQS partial batch failures, API Gateway's response shape, S3 keys that aren't unquoted, a function that triggers itself, deprecated runtimes | Platform (Lambda) | The reader already records everything these need; each is a few lines in `platforms/aws_lambda.py` | S |
| 3 | Batch calls that report failures in their answer, not by raising (`batch_write_item`, `send_message_batch`, `put_records`, `put_events`) | boto3 (reader) | Writes are lost without an error, the same family as the existing "reads only its first page" finding | S |
| 4 | HTTP as a library plugin | Library | Today it's hard-coded in the reader (`_http`). As a plugin each host gets a box, and it can flag SSRF (a URL built from the input) and `verify=False` the way SQL flags injection | M |
| 5 | Celery, Kafka and RabbitMQ | Library + platform | Queues are the other half of most backends. The Kafka and RabbitMQ logos are already in `report/logos/` | M |
| 6 | AWS CDK (Python) | Deploy | The most common way to deploy Lambda now, and it's Python, so `ast` reads it without running it, which fits the rules exactly | L |
| 7 | Terraform | Deploy | The other common way. `aws_lambda_function` and its IAM policy documents map straight onto `Deployment` | L |
| 8 | Resource-level IAM: which table, which bucket | boto3 + SAM | Today a role is checked for the action (`dynamodb:PutItem`). With resource names it can say "allowed on OrdersTable, not on ReceiptsTable" | M |
| 9 | Stripe, Twilio, Slack, Elasticsearch, Supabase, Firebase, Snowflake | Library | Each is small, and every one already has its logo in `report/brands.py` `SERVICE_LOGOS` | S each |
| 10 | `--json`, SARIF and `--fail-on` | Command | Lets other repos run code-node in CI and see findings in GitHub code scanning; `CodeMap` and the findings are already the contract | M |

## Hooks to add first

A few places in the generic code are shaped like AWS or Lambda, and would get in the way of a second platform or
deploy reader. Fixing these first keeps "generic first, platforms as plugins" true as plugins arrive.

| Where | What's AWS-shaped | Change |
| --- | --- | --- |
| `analysis/findings.py` (the secret finding) | Says "Keep them in Secrets Manager or Parameter Store" for any code, Lambda or not | A `Platform.secret_store()` hook: Lambda keeps that wording, plain Python says "an environment variable or your secret store" |
| `Platform.denied`, `AwsCall.permission`, `deploys.allowed` | Permissions are IAM actions matched with `fnmatch` | Give `Use` a `permission` (a library can say Cloud Storage needs `storage.objects.get`, PynamoDB needs `dynamodb:PutItem`), and let `Deploy` say whether a permission is allowed. Then GCP, Azure and Kubernetes RBAC fit the same check |
| `analysis/model.py` `Deployment` | Fields are Lambda's: runtime, timeout, memory, layers, `platform="lambda"` | Add `facts` (as `Handle` has) for what other platforms have: concurrency, min instances, service account, image, command. Default `platform` to `""` |
| `analysis/model.py` `Deployment.env_names` | Names only | Keep values that are literals or references (`!Ref OrdersTable`), so code reading `os.environ["TABLE"]` can be tied to the resource it names. Needed for resource-level IAM |
| `Deploy.deployments(files, code)` | `code` is the Python files' names, not their text, and `files` are matched by basename | CDK and Pulumi apps are Python files with any name. Pass the parsed trees (or texts), and let a deploy plugin claim a file by a predicate, not only a name |
| `Platform.inputs` | The input is a parameter named `event` | A hook that says which parameters of an entry function are the input: for FastAPI, every parameter; for Flask, `request.args` / `request.json`; for Celery, the task's arguments |
| `Library` hooks | No hook for decorators or for calls on the code's own functions | Celery's `@app.task` then `send_email.delay(...)`, Powertools' `@event_source`, Kafka consumers and FastAPI's `Depends` hang on decorators. Add `Library.decorated(function, decorator)` and let a library answer for a call on a function it marked |
| `analysis/aws_model.py` `_event_kind` | Lambda's event shapes, in the generic layer | Move it into `platforms/aws_lambda.py`; only `LambdaPlatform.input_kind` calls it |
| The reader | It doesn't note when a call's answer is thrown away | Mark a call made as a statement (`table.batch_write_item(...)` with nothing kept), for the "failures in the answer" checks below |
| `project.py` | Nothing reads what versions the code depends on | `Project.pins` from `requirements*.txt`, `pyproject.toml`, `uv.lock` and `poetry.lock`, passed to plugins, so each can check APIs a version removed (PyMongo 4, openai 1.0, SQLAlchemy 2.0, Pydantic 2) |

## Each plugin today, and what it could add

### AWS through boto3 (in the reader)

**Today.** Clients, resources and sessions; each operation named from botocore's own models with its IAM action;
paginators, waiters, presigned links, S3 transfers, resource collections and `batch_writer()`; a guess for a client
it can't follow; batch hints for eleven calls; and lists that read only their first page.

**What it could add:**

| Service | Finding | Why it matters | Size |
| --- | --- | --- | --- |
| Any | The resource each call is on: `Bucket=`, `TableName=`, `QueueUrl=`, `TopicArn=`, `Table(name)` | The box lists "orders table", and with a deploy file's env values, IAM is checked per resource | M |
| Any | A client without a `Config(read_timeout=..., retries=...)` | botocore waits 60 s per try and retries; on Lambda that outlives a short timeout. Same check the library plugins have (`Handle.waits`) | S |
| Any | `endpoint_url="http://localhost:4566"` left in | LocalStack settings shipped to production fail every call | S |
| Any | Access keys passed to `boto3.client(...)` on Lambda | They override the function's role, so the IAM checks are wrong and the keys leak | S |
| DynamoDB | `batch_write_item` / `batch_get_item` whose `UnprocessedItems` / `UnprocessedKeys` isn't read | Throttled items are dropped without an error | S |
| DynamoDB | A float from `json.loads(...)` put in an `Item` through the resource API | `TypeError: Float types are not supported. Use Decimal types instead`. The cart example does exactly this. Fix: `json.loads(body, parse_float=Decimal)` | M |
| DynamoDB | `Scan` reached from an entry point that serves requests | Reads the whole table on every call: slow and billed per item read | S |
| DynamoDB | `UpdateExpression` / `FilterExpression` built from the input | Expression injection; use `ExpressionAttributeValues` | S |
| DynamoDB | `transact_write_items` with a list that can pass 100 items | `ValidationException` | S |
| S3 | A key read from an S3 event without `unquote_plus` | Keys arrive URL-encoded (`my+file.csv`), so any key with a space gives `NoSuchKey`. The reader already passes `unquote_plus` through, so it can tell when it's missing | S |
| S3 | `ACL="public-read"` | Makes the object public | S |
| S3 | `generate_presigned_url` with `ExpiresIn` over 604,800, or a `Key` from the input | Over seven days the link is refused; a key from the input signs any object | S |
| S3 | `get_object()["Body"].read()` on Lambda with little memory | The object is held in memory whole | S |
| SQS | `receive_message` without `WaitTimeSeconds` | Short polling: many empty, billed requests | S |
| SQS | `receive_message` with no `delete_message` after it | Every message comes back after its visibility timeout | M |
| SQS | `send_message` to a `.fifo` queue without `MessageGroupId` | Fails every time | S |
| SQS, SNS, Kinesis, Firehose, EventBridge | `send_message_batch` / `publish_batch` / `put_records` / `put_record_batch` / `put_events` whose `Failed` / `FailedRecordCount` / `FailedEntryCount` isn't read | Part of the batch fails and the call still returns | S |
| Secrets Manager, SSM | `get_secret_value` / `get_parameter` on every call, not at start-up or cached | Latency and cost on every run; read once, or use the Parameters and Secrets Lambda extension | S |
| Bedrock | The model ID on `invoke_model` / `converse` as the box's target, and the timeout check | Puts Bedrock next to the LLM plugin's OpenAI and Anthropic boxes | S |
| RDS | `generate_db_auth_token` as the IAM action `rds-db:connect` | IAM database auth needs it, and the role check misses it today | S |
| Other libraries | `aioboto3`, `aiobotocore`, `awswrangler` (`wr.s3.read_parquet`, `wr.athena.read_sql_query`), `s3fs`, `smart_open`, and pandas writes to `s3://` (`to_parquet`, `to_csv`; only `read_*` is followed today) | All of these reach S3, Athena and Glue with the same IAM actions | M |

### AWS Lambda (platform)

**Today.** `lambda_handler` / `handler` with two arguments, and Chalice and Powertools resolvers as web apps; an
async handler; the wrong number of arguments; environment variables that aren't set; layers; writes outside
`/tmp`; a client or connection made on every call; IAM actions the role doesn't allow; sleeping while billed.

**What it could add:**

| Finding | What it needs | Size |
| --- | --- | --- |
| **SQS partial batch failures.** An SQS handler that raises for one record retries the whole batch; one that returns `batchItemFailures` without `FunctionResponseTypes: [ReportBatchItemFailures]` on its event source has that answer ignored | `input_kind` is already "an SQS batch"; the deploy readers add the event's settings | S |
| **API Gateway's response shape.** Behind an HTTP event, returning a dict whose `body` isn't a string, or with no `statusCode`, gives the caller a 502 | The return statements are already read (`findings._returned`) | S |
| **A function that triggers itself.** An S3 event on a bucket the code writes to, an SQS event on a queue it sends to, or `lambda.invoke` with its own name: an endless loop and a large bill | The event's bucket or queue from the deploy file, against the calls' resources | M |
| **Deprecated runtimes.** `python3.8` and `python3.9` can no longer be created or updated | A dated table next to `LATEST_RUNTIMES` in `analysis/terms.py` | S |
| **A CloudFormation custom resource that never answers.** A handler reading `RequestType` and `ResponseURL` that never sends to `ResponseURL` (or uses `cfnresponse` only on success) leaves the stack waiting for an hour | A new `input_kind` and the reader's HTTP calls | S |
| **API Gateway's 29 s limit.** A function behind an API event with a timeout over 29 s: the caller gets a 504 while it keeps running and billing | Event type plus `Deployment.timeout` | S |
| **SQS visibility timeout.** A queue in the same template whose `VisibilityTimeout` is under the function's timeout: messages are delivered twice | The template's queue resource | S |
| **No failure destination.** Async event sources (S3, SNS, EventBridge) with no `DeadLetterQueue` or `OnFailure` destination: the event is dropped after two retries | The deploy file | S |
| **State kept between calls.** A module-level list or dict the handler appends to grows on every warm call, and can leak one caller's data to the next | The reader already tells start-up from per-call code | M |
| **Heavy imports on 128 MB.** pandas, numpy or pyarrow on the default memory: slow cold starts, or out of memory | `Deployment.memory` and the imports | S |
| **Powertools.** Read `@event_source(data_class=SQSEvent)` and `parse(event, model=Order)` for the event's fields; `BatchProcessor` / `process_partial_response` as the fix for partial failures; `parameters.get_secret` as `secretsmanager:GetSecretValue`; `@idempotent` as a DynamoDB table it writes | Mostly the decorator hook above | M |
| **Mangum.** `handler = Mangum(app)` makes the FastAPI app's routes the entry point (`mangum` is already listed in `_LIBRARIES`) | Add Mangum to `web_apps` | S |
| **Container image functions.** `PackageType: Image` is skipped today; the handler is in the Dockerfile's `CMD` | The Dockerfile reader below | M |
| **More event kinds** for `input_kind` and the sample event: Cognito triggers (`triggerSource`), ALB, Function URLs, AppSync (`info.fieldName`), MSK and self-managed Kafka (`eventSource: aws:kafka`), S3 Batch Operations, Step Functions task tokens | `_event_kind` | S |
| **Lambda@Edge.** No environment variables allowed, 5 s / 30 s limits, us-east-1 only | A small subclass of `LambdaPlatform` | S |

### Redis (library)

**Today.** Clients, cluster clients and pools; pipelines, pub/sub and locks; every command as a read, write, send
or script; `KEYS` and `FLUSHALL`; batch hints (`mget`, a pipeline); a client without `socket_timeout`.

| Finding | Why it matters | Size |
| --- | --- | --- |
| `lock()` without `timeout` | If the holder dies, the lock is held forever | S |
| `blpop` / `brpop` / `xread(block=0)` with no timeout | Blocks forever; on Lambda until the function's timeout | S |
| `pubsub.listen()` or a `while True` read loop in a Lambda handler | Runs until Lambda stops it, every time | S |
| `set` of a per-user or per-request key (`cart:{user}`) with no `ex` / `px` | Keys never expire and memory grows until eviction | S |
| `eval` with a script built from the input | Lua injection, the same check as SQL's | S |
| More clients: `redis.asyncio`, `valkey` (the fork, same API), `upstash_redis`, `django-redis` and `django.core.cache` | Same plugin, more module names | S |
| ElastiCache as the box's name and logo when the host comes from an `AWS::ElastiCache` resource in the template | The logo `aws-elasticache` is already there | S |

### SQL (library)

**Today.** sqlite3, psycopg2, psycopg, PyMySQL, MySQLdb, mysql-connector, asyncpg and SQLAlchemy Core: connections,
pools, engines, `text()`; each statement read for its verb and table; SQL injection from the input; `executemany()`
and N+1 hints; connections without a timeout.

| Finding | Why it matters | Size |
| --- | --- | --- |
| `UPDATE` or `DELETE` with no `WHERE` | Changes every row. The statement's text is already parsed | S |
| Writes on a psycopg2 / PyMySQL connection with no `commit()`, no `with conn:` and no `autocommit` | The writes are rolled back when the connection closes, without an error | M |
| `fetchall()` on a `SELECT` with no `LIMIT` | Loads every row into memory | S |
| A password written into a DSN (`postgresql://user:secret@host/db`) | Feeds the existing secret finding | S |
| `psycopg.sql.SQL(...).format(sql.Identifier(...))` not flagged as injection | It's the safe way, and should stay quiet | S |
| **SQLAlchemy ORM:** `Session`, `select(Model)`, `session.query(Model)`, `session.add()` and `commit()`, each model's `__tablename__` as the table; a relationship read in a loop (lazy-loading N+1) | Most SQLAlchemy code is ORM, which is read as nothing today | L |
| **Django ORM:** `Model.objects.filter/get/create/update/delete`, `raw()` / `extra()` / `connection.cursor()` with f-strings (injection), loops without `select_related` | As its own `django` library plugin, with the web platform | L |
| More drivers: `aiosqlite`, `aiomysql`, `pyodbc` (SQL Server), `oracledb`, `snowflake.connector`, `redshift_connector`, `duckdb`, `clickhouse_connect` | Each is a few names in `_CONNECT`; Snowflake and Redshift already have logos | S |
| SQL that isn't a driver: `pandas.read_sql(f"...")`, BigQuery's `client.query(f"...")`, the RDS Data API's `execute_statement(sql=...)`, Athena's `start_query_execution(QueryString=f"...")` | The same injection check, on calls the SQL plugin doesn't see today | M |
| SQLAlchemy 2.0 removals: `engine.execute()`, a plain string passed to `conn.execute()` | `AttributeError` / `ObjectNotExecutableError` after upgrading; needs `Project.pins` | S |

### MongoDB (library)

**Today.** PyMongo and Motor clients, databases and collections by attribute or by name; each method as a read or a
write; `$where` built from the input; batch hints.

| Finding | Why it matters | Size |
| --- | --- | --- |
| A filter value taken straight from the input (`find({"user": body["user"]})`, or `find(body)`) | Operator injection: `{"$ne": null}` matches every user | S |
| `MongoClient` without `serverSelectionTimeoutMS` / `socketTimeoutMS` | Waits 30 s to find a server, then a socket can wait forever. Give the handle `waits` and `fix`, as Redis does | S |
| `count()`, `insert()`, `update()`, `remove()`, `save()`, `find_and_modify()`, `ensure_index()` | PyMongo 4 removed them: `AttributeError` | S |
| `find()` with no `limit` or projection, `to_list(None)` in Motor | Loads the whole result | S |
| `create_index` on every call | A round trip for nothing on each run; make indexes once | S |
| `$regex` from the input | A slow pattern stalls the server (ReDoS) | S |
| ODMs: Beanie, MongoEngine, ODMantic | Most apps use one | M |
| DocumentDB as the box's name and logo when the host comes from the template | `aws-documentdb` is already there | S |

### OpenAI and Anthropic (library)

**Today.** OpenAI, Azure OpenAI and Anthropic (with Bedrock and Vertex) clients, the call's path
(`chat.completions.create`) and its model as the target, the SDKs' 10-minute timeout with retries, the Batch API
hint, and openai's pre-1.0 module functions.

| Finding | Why it matters | Size |
| --- | --- | --- |
| Input in the system prompt (`system=f"... {body['name']}"`, `instructions=`) | Whoever sends it can rewrite the model's instructions. `call.inputs()` already says what reached the argument | S |
| Anthropic's `messages.create` without `max_tokens` | It's required: `TypeError` on every call | S |
| A retired model ID (`text-davinci-003`, `gpt-3.5-turbo-0301`, `claude-2.0`) | 404 on every call. A dated table, kept like `LATEST_RUNTIMES` | S |
| `openai.ChatCompletion.create` with openai 1.0 or later pinned | `APIRemovedInV1` on every call; needs `Project.pins` | S |
| `embeddings.create` in a loop | It takes a list; the batch hint can say so instead of the Batch API | S |
| `OpenAI(base_url=...)` naming the service by its host (OpenRouter, vLLM, a local server) | Today it's drawn as OpenAI | S |
| More SDKs: Google's `google-genai` (Gemini), Vertex AI, Mistral, Cohere, Groq, Ollama, LiteLLM (`litellm.completion(model=...)`), Hugging Face's `InferenceClient` | Same plugin shape: client, path, model | M |
| LangChain and LlamaIndex: `ChatOpenAI(model=...)`, `ChatAnthropic`, `ChatBedrock`, `.invoke()` | Many LLM apps never touch the SDK directly | M |
| Vector stores: Pinecone, Qdrant, Weaviate, Chroma (pgvector is SQL) | Reads and writes on an index; its own `vectors` plugin | M |

### HTTP (in the reader)

**Today.** requests, httpx, urllib3, aiohttp, `http.client` and `urlopen`; sessions and their timeout; the
"no timeout" finding, worded for the platform.

Moving it into a `Library` plugin gives it what the others have, and lets it stack with service plugins:

| Finding or feature | Why it matters | Size |
| --- | --- | --- |
| A box per host, from a literal URL or the variable it comes from (`PAYMENTS_URL`), with known hosts' logos (api.stripe.com, hooks.slack.com) | The graph shows what the code talks to, not "HTTP" | M |
| A URL built from the input | SSRF: whoever sends it can make the code fetch internal addresses (the instance metadata service on EC2) | S |
| `verify=False` | TLS is off; anyone on the path can read and change the traffic | S |
| No `raise_for_status()` and the status never read | A 500 looks like success | S |
| `requests.get` (not a `Session`) in a loop | A new connection for each item | S |
| A token or password written into a header or URL | Feeds the secret finding | S |
| More clients: gRPC (`grpc.insecure_channel` with no deadline), `websockets`, GraphQL's `gql`, `smtplib` (no timeout, no `starttls`), `paramiko` (`AutoAddPolicy` trusts any host key) | Each is a service a box can show | M |

### AWS SAM and CloudFormation (deploy)

**Today.** `AWS::Serverless::Function` and `AWS::Lambda::Function` on Python, with `Globals`; environment variable
names; what the role allows from policy templates, the managed policies it knows, inline statements, a role in the
template and `AWS::IAM::Policy` resources; the permissions event sources add; layers, timeout, memory.

| Change | Why it matters | Size |
| --- | --- | --- |
| Policy templates' parameters (`DynamoDBCrudPolicy: {TableName: !Ref Orders}`) and env values (`TABLE: !Ref Orders`) | Resource-level IAM: "allowed on OrdersTable, not on ReceiptsTable" | M |
| Read `AWS::Serverless::Connector` (Source, Destination, Read/Write) | Today a connector makes permissions unknown | M |
| Every SAM policy template, generated from SAM's published `policy_templates.json` by a script with a pinned hash, as `scripts/logos.py` does | `POLICY_TEMPLATES` has 36; SAM has many more, and one it doesn't know makes the role unknown | S |
| Every AWS managed policy, from a pinned snapshot the same way | `MANAGED_POLICIES` has 20 | S |
| The event source's details: an S3 event's bucket, SQS's `FunctionResponseTypes`, an API event, a schedule | Feeds the Lambda checks above (recursion, partial batch, 29 s, input kind) | S |
| `Parameters` with defaults, `samconfig.toml`'s overrides, `Fn::Sub`, `Fn::If` | Resolve `!Ref Stage` and the names built from it | M |
| Nested stacks with a local `Location` / `TemplateURL` | Functions in a child template are missed today | M |
| `AWS::Serverless::Api` with no authorizer | A public endpoint, said as info | S |
| `AWS::Serverless::StateMachine` and its definition | Which functions a workflow calls, in order: a later "system map" (below) | L |

### Serverless Framework (deploy)

**Today.** Each Python function with the provider's settings, environment variable names, v3's
`provider.iam.role` and v2's `iamRoleStatements`, managed policies, SQS and stream grants, timeout, memory and layers.

| Change | Why it matters | Size |
| --- | --- | --- |
| Resolve `${self:...}`, `${file(...)}` and `${opt:stage, 'dev'}` defaults | Env values and resource names; today `${...}` stays as text | M |
| Read the `resources:` section (it's CloudFormation) with the SAM reader's helpers | Roles and tables declared there | S |
| `package.patterns` / `exclude` that leave out a file the handler imports | `Runtime.ImportModuleError` on every call | M |
| `serverless-python-requirements` in `plugins:` | Says which libraries ship in the package, against the imports | S |
| Per-function roles (`serverless-iam-roles-per-function`) | Today the provider's statements are used for every function | S |
| `http` / `httpApi`, `s3`, `schedule` and `sqs` (`functionResponseType`) events | The same Lambda checks as SAM's events | S |
| `serverless-compose.yml` | Several services in one folder | M |

## New platforms

| Platform | Entry points | Its input | Checks only it has | Size |
| --- | --- | --- | --- | --- |
| **Web: FastAPI / Starlette** | Routes (found today), `Mangum(app)` | Path, query and body parameters, `Depends` | A blocking call (`requests`, `time.sleep`, a sync DB driver) in an `async def` route stalls every request; `allow_origins=["*"]` with `allow_credentials=True` | M |
| **Web: Flask** | Routes (found today), blueprints | `request.args`, `request.form`, `request.json`, `request.headers` | `app.run(debug=True)` (the Werkzeug debugger runs any code sent to it); `render_template_string` with the input (template injection); `send_file` with a path from the input | M |
| **Web: Django** | `urls.py`'s `path()` to views, class-based views | `request.GET`, `request.POST`, `request.body` | `DEBUG = True`, `ALLOWED_HOSTS = ["*"]` and a literal `SECRET_KEY` in `settings.py`; `csrf_exempt`; the ORM checks above | L |
| **Task workers: Celery, RQ, Dramatiq, arq** | `@app.task`, `@shared_task`, `@dramatiq.actor` | The task's arguments | `result.get()` inside a task (Celery refuses it: it can deadlock); an ORM object passed to `.delay()`; no time limit; `autoretry_for` with no `max_retries` | M |
| **Google Cloud Functions / Cloud Run** | `@functions_framework.http`, `@functions_framework.cloud_event`, a web app in a container | The Flask request, `cloud_event.data` | Writes outside `/tmp` (an in-memory disk that counts against memory); a client per call; the 60 s default timeout; Pub/Sub messages base64 in `data` | L |
| **Azure Functions** | The v2 model's `func.FunctionApp()` with `@app.route`, `@app.queue_trigger`; v1's `function.json` with `main(req)` | `func.HttpRequest`, the trigger's binding | `functionTimeout` from `host.json`; settings from `local.settings.json` that aren't set | L |
| **Airflow DAGs (and Prefect, Dagster)** | `@task`, `PythonOperator(python_callable=...)`, `@flow`, `@op` | The task's arguments, `context` | Code at the top of a DAG file runs on every scheduler parse: heavy imports, `Variable.get` and API calls there slow the whole scheduler. The reader's start-up steps already find exactly this | M |
| **AWS Glue jobs** | The script itself | `getResolvedOptions(sys.argv, [...])` | `GlueContext` reads and writes as S3 and Glue calls with IAM; `toDF().collect()` on a big frame | M |
| **Containers / CLIs** | `CMD` in a Dockerfile, `Procfile` lines, Typer and click apps (found today) | `sys.argv`, the CLI's options | Errors dropped so the process exits 0; signals not handled before a container is stopped | M |

## New libraries

Every one of these fits the `Library` API as it is (`make`, `attribute`, `call`), and most have a logo already.

| Library | Modules | Draws | Its best finding | Logo |
| --- | --- | --- | --- | --- |
| Kafka | `kafka`, `confluent_kafka`, `aiokafka` | Topics produced to and consumed from | `produce()` with no `flush()` before a Lambda handler returns: messages still in the buffer are lost | `kafka-icon` (and `aws-msk`) |
| RabbitMQ | `pika`, `aio_pika`, `kombu` | Exchanges and routing keys | `auto_ack=True`: a message is gone if the worker dies on it; a `BlockingConnection` per call | `rabbitmq-icon` (and `aws-mq`) |
| Celery (producer side) | `celery` | `.delay()`, `.apply_async()`, `send_task()` as sends to a queue | A task called directly instead of with `.delay()`, so it runs in the request | needs one |
| Elasticsearch / OpenSearch | `elasticsearch`, `opensearchpy` | Indexes searched and written | `index()` in a loop instead of `helpers.bulk`; `query_string` built from the input; no `request_timeout` | `elasticsearch`, `aws-open-search` |
| Stripe | `stripe` | Charges, payment intents, refunds as writes | `PaymentIntent.create` without `idempotency_key` in code that's retried (Lambda, SQS, Celery): a retry charges twice. A webhook route that doesn't call `stripe.Webhook.construct_event` trusts anything posted to it | `stripe` |
| Twilio, Slack, SendGrid | `twilio`, `slack_sdk`, `sendgrid` | Messages sent | A message sent per item in a loop; a token written in the code | `twilio-icon`, `slack-icon` |
| Supabase | `supabase` | `table("x").select/insert/update` as SQL-like reads and writes | The service-role key in code that runs in a client | `supabase-icon` |
| Firebase | `firebase_admin` | Firestore, Auth, Cloud Messaging | Firestore `.stream()` on a whole collection | `firebase-icon` |
| Google Cloud | `google.cloud.storage`, `pubsub_v1`, `firestore`, `bigquery`, `secretmanager` | Buckets, topics, collections, datasets | `publisher.publish()` whose future is never awaited: lost when the function exits. BigQuery SQL built from the input | `google-cloud` |
| Azure | `azure.storage.blob`, `azure.servicebus`, `azure.cosmos` | Containers, queues, databases | A connection string written in the code | `azure-icon` |
| PynamoDB | `pynamodb` | DynamoDB calls with their IAM actions | Same as boto3's DynamoDB checks, so it needs `Use.permission` (above) | `aws-dynamodb` |
| Memcached | `pymemcache`, `pylibmc` | Keys read and written | No `connect_timeout` / `timeout` | needs one |
| SFTP / FTP | `paramiko`, `pysftp`, `ftplib` | Remote paths read and written | `AutoAddPolicy` (trusts any host); plain FTP sends the password in the clear | needs one |

Not libraries, but the same kind of check belongs in the generic findings next to shell injection: `pickle.loads`,
`yaml.load` without `SafeLoader`, `eval` / `exec`, and `tarfile.extractall` on anything from the input.

## New deploy readers

| Reader | Files | What it gives | Size |
| --- | --- | --- | --- |
| **AWS CDK (Python)** | `cdk.json`, then the app's `.py` files | `_lambda.Function(... runtime=Runtime.PYTHON_3_12, handler="app.handler", code=Code.from_asset("src"), environment={...}, timeout=Duration.seconds(30))` and `PythonFunction`; permissions from `table.grant_read_write_data(fn)` (a table of each `grant_*` to its actions) and `add_to_role_policy(PolicyStatement(actions=[...]))`. Read with `ast`, never run | L |
| **Terraform** | `*.tf` | `aws_lambda_function` (handler, runtime, timeout, memory, `environment.variables`, role), `aws_iam_policy_document` and `aws_iam_role_policy`, managed policy attachments, `archive_file`'s `source_dir`, and the common `terraform-aws-modules/lambda/aws` module. HCL needs a parser (`python-hcl2`, kept optional as botocore is) | L |
| **Pulumi (Python)** | `Pulumi.yaml`, then `__main__.py` | `aws.lambda_.Function(...)` and its role, read with `ast` like CDK | M |
| **Chalice** | `.chalice/config.json`, `policy-*.json` | Env vars, `lambda_timeout`, `lambda_memory_size`, and the role's policy file (Chalice apps are already found as Lambda web apps) | S |
| **Zappa** | `zappa_settings.json` | `app_function`, `environment_variables`, `timeout_seconds`, `extra_permissions`. It's the example in `docs/plugins.md`, so make it real | S |
| **Dockerfile** | `Dockerfile`, `*.Dockerfile` | The Python version from `FROM python:3.11-slim` (for `python_version`), the entry point from `CMD` / `ENTRYPOINT` (`uvicorn main:app`, `celery -A tasks worker`, a Lambda image's `app.handler`), `ENV` names | M |
| **docker-compose** | `docker-compose.yml`, `compose.yaml` | Each service's env names, and which hosts are other services (a Redis box that's the `redis` container) | S |
| **`.env` files** | `.env`, `.env.example`, `.env.sample` | The variables that are set, so "isn't set" works for any platform, not only a Lambda function with a template | S |
| **Kubernetes / Helm** | Manifests with `kind: Deployment/CronJob`, `values.yaml` | `env`, `envFrom`, `command`, resource limits, `serviceAccountName` | M |
| **Procfile and PaaS files** | `Procfile`, `app.yaml` (App Engine), `fly.toml`, `render.yaml` | Entry points (`web: gunicorn app:app`, `worker: celery ...`) with their platform, and env names | S |
| **Azure Functions** | `host.json`, `function.json`, `local.settings.json` | `functionTimeout`, bindings (which become the input kind), settings | M |
| **Google Cloud** | `service.yaml` (Cloud Run), `cloudbuild.yaml` | Timeout, concurrency, env, service account | M |

## Across all of them

| Idea | What it gives other repos | Size |
| --- | --- | --- |
| **`--json` and SARIF**, and `--fail-on warn` | CI can fail a pull request on a new warning, and GitHub shows findings on the lines they're about. A small GitHub Action and a pre-commit hook wrap it | M |
| **A system map.** Every entry point in the folder on one page, joined by what they share: function A sends to the queue that's function B's SQS event in the template, both write `OrdersTable` | The thing a new person on a team wants first. The deploy readers already know each function's events | L |
| **Dependency pins** (`Project.pins`) | Version-specific checks in every library plugin, and "imports a library that isn't in `requirements.txt`" before the package is built | M |
| **A plugin kit for other repos.** `code_node.testing.map_files({...}, platform=...)` returning the `CodeMap` and findings; a snapshot helper like `tests/snapshots/`; a template repo for a plugin package; `--plugins` listing each plugin's package and version | Others can write and test plugins without copying this repo's tests | M |
| **One example per family** | `examples/web-service` (FastAPI, SQLAlchemy ORM, Celery, Stripe) and a Cloud Functions one, next to `orders-service` and `cart-service`, each with a snapshot test and a docs figure (`scripts/docs_figures.py`) | M |
| **Logos for the new ones** | `scripts/logos.py` fetches from `@iconify-json/logos`; add the names for Celery, Django, FastAPI, Flask, Terraform, Docker, Kubernetes, Pulumi, Airflow and the GCP and Azure services the set has | S |

## An order to do them in

1. **Small checks on what's there** (no API change): the Lambda checks (SQS partial batch, response shape, S3 key
   unquoting, deprecated runtimes, custom resources, 29 s, visibility timeout), batch calls whose failures go
   unread, SQL's `UPDATE`/`DELETE` without `WHERE` and missing `commit()`, Mongo's removed methods and timeouts,
   Redis lock and blocking timeouts, Anthropic's `max_tokens`, the secret finding's wording, and the `.env`, Zappa
   and Chalice readers.
2. **The hooks**: `Use.permission`, `Deployment.facts` and env values, a platform's input parameters, decorators in
   `Library`, deploy readers that see Python, `Project.pins`. Then HTTP as a library plugin, and resource-level IAM.
3. **New ecosystems on those hooks**: the web platform (FastAPI, Flask, then Django), Celery, Kafka and RabbitMQ,
   SQLAlchemy ORM, CDK, Terraform and the Dockerfile.
4. **Further out**: Google Cloud and Azure (platform, libraries and deploy files together), the system map, and
   `--json` / SARIF for CI.

Each new plugin, as `CLAUDE.md` asks: a test in `tests/test_code_node.py`, a bullet under `## [Unreleased]` in
`CHANGELOG.md`, a row in `docs/plugins.md`'s table, its logo in `report/brands.py`, and the README's list.
