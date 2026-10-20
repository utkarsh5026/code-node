"""
SQL databases through their drivers: sqlite3, psycopg2 and psycopg (PostgreSQL), PyMySQL and mysql-connector
(MySQL), asyncpg, SQLAlchemy's engines and text(), and Django's connection.cursor(). Each statement is read for what it does to which table, and a
statement put together from the entry point's input is flagged.
"""

from __future__ import annotations

import re

from . import Call, Handle, Library, Use

_CONNECT = {  # a driver's function that opens a connection -> the database, as people name it
    "sqlite3.connect": "SQLite", "psycopg2.connect": "PostgreSQL", "psycopg.connect": "PostgreSQL",
    "psycopg.Connection.connect": "PostgreSQL", "psycopg.AsyncConnection.connect": "PostgreSQL",
    "pymysql.connect": "MySQL", "pymysql.connections.Connection": "MySQL", "MySQLdb.connect": "MySQL",
    "mysql.connector.connect": "MySQL", "asyncpg.connect": "PostgreSQL",
}

_POOLS = {"asyncpg.create_pool": "PostgreSQL", "psycopg2.pool.SimpleConnectionPool": "PostgreSQL",
          "psycopg2.pool.ThreadedConnectionPool": "PostgreSQL", "psycopg_pool.ConnectionPool": "PostgreSQL"}

_SCHEMES = (("postgres", "PostgreSQL"), ("mysql", "MySQL"), ("mariadb", "MySQL"), ("sqlite", "SQLite"),
            ("mssql", "SQL Server"), ("oracle", "Oracle"), ("snowflake", "Snowflake"), ("redshift", "Redshift"))

_TIMEOUTS = ("connect_timeout", "timeout", "command_timeout", "connection_timeout", "read_timeout")

_RUN = ("execute", "executemany", "executescript", "fetch", "fetchrow", "fetchval", "exec_driver_sql", "scalar",
        "scalars", "copy_records_to_table", "copy_from", "copy_expert")

_STATEMENT = re.compile(r"^\s*(?:\(\s*)?(WITH|SELECT|INSERT|UPDATE|DELETE|MERGE|REPLACE|UPSERT|CREATE|DROP|ALTER|"
                        r"TRUNCATE|CALL|COPY|GRANT|VACUUM|PRAGMA|SHOW|EXPLAIN|BEGIN|COMMIT|ROLLBACK|SET)\b", re.I)

_TABLE = {  # a statement -> where its table is named
    "SELECT": r"\bFROM\s+([\w.\"`\[\]{}]+)", "WITH": r"\bFROM\s+([\w.\"`\[\]{}]+)",
    "INSERT": r"\bINTO\s+([\w.\"`\[\]{}]+)", "REPLACE": r"\bINTO\s+([\w.\"`\[\]{}]+)",
    "UPSERT": r"\bINTO\s+([\w.\"`\[\]{}]+)", "MERGE": r"\bINTO\s+([\w.\"`\[\]{}]+)",
    "UPDATE": r"^\s*UPDATE\s+(?:ONLY\s+)?([\w.\"`\[\]{}]+)", "DELETE": r"\bFROM\s+([\w.\"`\[\]{}]+)",
    "CREATE": r"\b(?:TABLE|INDEX|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"`\[\]{}]+)",
    "DROP": r"\b(?:TABLE|INDEX|VIEW)\s+(?:IF\s+EXISTS\s+)?([\w.\"`\[\]{}]+)",
    "ALTER": r"\bTABLE\s+([\w.\"`\[\]{}]+)", "TRUNCATE": r"^\s*TRUNCATE\s+(?:TABLE\s+)?([\w.\"`\[\]{}]+)",
    "COPY": r"^\s*COPY\s+([\w.\"`\[\]{}]+)",
}

_MARKERS = {"SQLite": "?", "PostgreSQL": "%s", "MySQL": "%s"}  # how a driver's parameters are written


def _statement(text: str) -> tuple[str, str]:
    """
    What a SQL statement does and to which table, from its text (a literal or an f-string, as code):
    "'SELECT id FROM orders WHERE ...'" -> ('SELECT', 'orders'). ('', '') when it isn't SQL it can read.
    """
    body = re.sub(r"^[rbuf]*(['\"]{1,3})", "", text.strip(), flags=re.I)
    found = _STATEMENT.match(body)
    if not found:
        return "", ""
    verb = found.group(1).upper()
    if verb == "WITH":  # WITH ... AS (...) then the statement that does the work
        main = re.search(r"\)\s*(SELECT|INSERT|UPDATE|DELETE|MERGE)\b", body, re.I)
        verb = main.group(1).upper() if main else "SELECT"
    table = re.search(_TABLE.get(verb, r"$^"), body, re.I | re.S)
    return verb, table.group(1).strip("\"`[]") if table else ""


def _access(verb: str) -> str:
    if verb in ("SELECT", "SHOW", "EXPLAIN", "PRAGMA"):
        return "reads"
    if verb == "CALL":
        return "runs"
    return "writes"


class SqlLibrary(Library):
    """
    SQL through a DB-API driver (connect(), cursor(), execute()) or SQLAlchemy (create_engine(), connect(),
    execute(text(...))).
    """

    name = "sql"
    title = "SQL"
    modules = ("sqlite3", "psycopg2", "psycopg", "psycopg_pool", "pymysql", "MySQLdb", "mysql", "asyncpg",
               "sqlalchemy", "django")
    icon = "database"

    def make(self, name: str, call: Call) -> Handle | Use | None:
        if name in _CONNECT or name in _POOLS:
            service = _CONNECT.get(name) or _POOLS[name]
            target = call.shown(0, "database") if service == "SQLite" else ""
            waits = "" if service == "SQLite" or call.given(*_TIMEOUTS) or "timeout" in call.code(0, most=300) \
                else f"as long as {service} takes to answer"
            kind = "connection" if name in _CONNECT else "pool"
            facts = (("database", target),) if target else ()
            fix = f"{name}(..., {'timeout' if name.startswith('asyncpg') else 'connect_timeout'}=5)"
            return Handle(kind, service, facts + (("driver", name.split(".")[0]),), opens=service != "SQLite",
                          waits=waits, fix=fix)  # SQLite opens a file: nothing to keep a connection to
        if name == "django.db.connection.cursor":  # Django opens and keeps the connection itself
            return Handle("cursor", "", (("driver", "django"),))
        last = name.rsplit(".", 1)[-1]
        if name.startswith("sqlalchemy") and last in ("create_engine", "create_async_engine", "engine_from_config"):
            url = str(call.value(0, "url") or "")
            service = next((label for scheme, label in _SCHEMES if url.startswith(scheme)), "SQL database")
            return Handle("engine", service, (("driver", "sqlalchemy"),), opens=True)
        if name.startswith("sqlalchemy") and last == "text":
            return Handle("statement", "", (("sql", call.text(0)), ("built", "yes" if call.built(0) else ""),
                                            ("inputs", ", ".join(call.inputs(0)))))
        return None

    def call(self, handle: Handle, method: str, call: Call) -> Handle | Use | None:
        kind = handle.kind
        if kind == "pool" and method in ("getconn", "acquire", "connection"):
            return handle.but("connection")
        if kind == "engine" and method in ("connect", "begin", "raw_connection"):
            return handle.but("connection")
        if kind == "connection" and method == "cursor":
            return handle.but("cursor")
        if kind == "connection" and method in ("transaction", "begin"):
            return handle.but("connection")
        if method not in _RUN:
            return None
        return self._statement(handle, method, call)

    def _statement(self, handle: Handle, method: str, call: Call) -> Use:
        service = handle.service or "SQL database"
        held = call.held(0, "statement") or call.held(0, "query") or call.held(0, "sql")
        if held is not None and held.kind == "statement":
            text, built = held.fact("sql"), bool(held.fact("built"))
            inputs = [part for part in held.fact("inputs").split(", ") if part]
        else:
            text = call.text(0, "sql") or call.text(0, "query") or call.text(0, "operation")
            built = call.built(0, "sql") or call.built(0, "query") or call.built(0, "operation")
            inputs = call.inputs(0, "sql") + call.inputs(0, "query") + call.inputs(0, "operation")
        verb, table = _statement(text) if text else ("", "")
        if method == "executescript":
            verb, table = verb or "SCRIPT", table
        operation = verb or "a query"
        access = _access(verb) if verb else "runs"
        flag = why = ""
        if built and inputs:
            marker = "$1" if handle.fact("driver") == "asyncpg" else _MARKERS.get(service, "%s")
            flag = "SQL injection"
            why = (f"puts {', '.join(dict.fromkeys(inputs))} into the SQL text itself, so whoever sends it can change "
                   f"the statement (SQL injection). Pass it as a parameter instead: "
                   f"execute(\"... WHERE id = {marker}\", (value,)).")
        batch = ""
        if method == "execute" and access == "writes" and verb in ("INSERT", "UPDATE", "DELETE", "REPLACE", "UPSERT"):
            batch = "one execute() with a list of rows" if handle.fact("driver") == "sqlalchemy" else "executemany()"
        elif access == "reads":
            batch = "one query for all of them (WHERE ... IN (...), or a join)"
        return Use(operation, access, table, service, flag=flag, why=why, batch=batch,
                   gives=handle.but("cursor") if handle.kind == "connection" else None)

    def describe(self, handle: Handle) -> str:
        service = handle.service or "SQL"
        return {"statement": "a SQL statement", "engine": f"a {service} engine",
                "pool": f"a {service} connection pool"}.get(handle.kind, f"a {service} {handle.kind}")
