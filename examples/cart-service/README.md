# cart-service

A small Lambda function for code-node's [Plugins](https://utkarsh5026.github.io/code-node/plugins.html) page and
`tests/snapshots/cart-service.txt`. Every kind of plugin reads it at once: `template.yaml` (AWS SAM) says where it
runs, and the code reaches PostgreSQL (psycopg2), Redis, OpenAI and AWS (boto3). It's never deployed or run.

```bash
code-node examples/cart-service
```

It has mistakes on purpose, one for each thing the plugins find together: two environment variables the template
doesn't set, two AWS calls its role doesn't allow, SQL built from the request, a query run once per item, an OpenAI
client with no timeout, and a database connection opened on every call.
