# books-api

A small FastAPI app for code-node's web platform and `tests/snapshots/books-api.txt`. Its routes are on an
`APIRouter` in `books/routes.py`, and reach PostgreSQL (psycopg2), Redis, S3 (boto3) and the web. It's never run.

```bash
code-node examples/books-api
```

Each route is read as called with the request: `book_id` from the path, `q` and `limit` from the query, a `Review`
body, an `x-reader` header. It has mistakes on purpose, one for each thing the web platform finds: SQL built from
the query string, a shell command built from the request, an HTTP request with no timeout and a boto3 call that
block an `async def` route, and a database connection opened on every request.
