"""
Redis through redis-py: the client (or a cluster's), its pipelines and pub/sub, and what each command does.
"""

from __future__ import annotations

from . import Call, Handle, Library, Use

_CLIENTS = ("Redis", "StrictRedis", "RedisCluster", "from_url")

_READS = frozenset(
    {
        "get",
        "mget",
        "getrange",
        "strlen",
        "exists",
        "type",
        "ttl",
        "pttl",
        "hget",
        "hgetall",
        "hmget",
        "hkeys",
        "hvals",
        "hlen",
        "hexists",
        "hscan",
        "hscan_iter",
        "lrange",
        "llen",
        "lindex",
        "lpos",
        "smembers",
        "sismember",
        "smismember",
        "scard",
        "srandmember",
        "sscan",
        "sscan_iter",
        "sinter",
        "sunion",
        "sdiff",
        "zrange",
        "zrevrange",
        "zrangebyscore",
        "zrevrangebyscore",
        "zscore",
        "zmscore",
        "zcard",
        "zcount",
        "zrank",
        "zrevrank",
        "zscan",
        "zscan_iter",
        "scan",
        "scan_iter",
        "keys",
        "xread",
        "xreadgroup",
        "xrange",
        "xrevrange",
        "xlen",
        "blpop",
        "brpop",
        "brpoplpush",
        "blmove",
        "bzpopmin",
        "bzpopmax",
        "pfcount",
        "getbit",
        "bitcount",
        "geopos",
        "geodist",
        "geosearch",
        "dbsize",
        "json",
        "ping",
        "info",
    }
)

_WRITES = frozenset(
    {
        "set",
        "setex",
        "psetex",
        "setnx",
        "mset",
        "msetnx",
        "getset",
        "getdel",
        "getex",
        "delete",
        "unlink",
        "expire",
        "pexpire",
        "expireat",
        "pexpireat",
        "persist",
        "rename",
        "renamenx",
        "incr",
        "incrby",
        "incrbyfloat",
        "decr",
        "decrby",
        "append",
        "setrange",
        "hset",
        "hmset",
        "hsetnx",
        "hdel",
        "hincrby",
        "hincrbyfloat",
        "lpush",
        "rpush",
        "lpushx",
        "rpushx",
        "lpop",
        "rpop",
        "lrem",
        "lset",
        "ltrim",
        "linsert",
        "lmove",
        "rpoplpush",
        "sadd",
        "srem",
        "spop",
        "smove",
        "sinterstore",
        "sunionstore",
        "sdiffstore",
        "zadd",
        "zrem",
        "zincrby",
        "zpopmin",
        "zpopmax",
        "zremrangebyscore",
        "zremrangebyrank",
        "xack",
        "xdel",
        "xtrim",
        "xgroup_create",
        "pfadd",
        "setbit",
        "geoadd",
        "copy",
        "flushdb",
        "flushall",
    }
)

_SENDS = frozenset({"publish", "spublish", "xadd"})

_RUNS = frozenset({"eval", "evalsha", "fcall", "script_load", "register_script"})

_MANY = {"get": "mget()", "set": "mset()", "hget": "hmget()", "delete": "one delete() with every key"}


class RedisLibrary(Library):
    """
    redis-py: redis.Redis(...) and redis.from_url(...), its pipelines and pub/sub.
    """

    name = "redis"
    title = "Redis"
    modules = ("redis",)
    icon = "database"

    def make(self, name: str, call: Call) -> Handle | Use | None:
        last = name.rsplit(".", 1)[-1]
        if last in _CLIENTS:
            given = call.given("socket_timeout") or "socket_timeout=" in call.code(0, most=200)
            return Handle(
                "client",
                "Redis",
                opens=True,
                waits="" if given else "as long as Redis takes",
                fix=f"{name.rsplit('.', 1)[-1]}(..., socket_timeout=5)",
            )
        if last in ("ConnectionPool", "BlockingConnectionPool"):
            given = call.given("socket_timeout")
            return Handle(
                "pool", "Redis", waits="" if given else "as long as Redis takes", fix=f"{last}(..., socket_timeout=5)"
            )
        return None

    def call(self, handle: Handle, method: str, call: Call) -> Handle | Use | None:
        if method == "pipeline":
            return handle.but("pipeline")
        if method == "pubsub":
            return handle.but("pubsub")
        if method == "lock":
            return Use("LOCK", "writes", call.shown(0, "name"), gives=handle.but("lock"))
        if handle.kind == "pubsub":
            if method in ("subscribe", "psubscribe"):
                return Use(method.upper(), "reads", call.shown(0))
            if method in ("listen", "get_message"):
                return None
        if handle.kind == "lock" or method in ("execute", "close", "reset", "watch", "multi"):
            return None
        target = call.shown(0, "name") if call.node.args or call.given("name", "keys", "channel") else ""
        operation = {
            "scan_iter": "SCAN",
            "hscan_iter": "HSCAN",
            "sscan_iter": "SSCAN",
            "zscan_iter": "ZSCAN",
            "register_script": "SCRIPT LOAD",
            "script_load": "SCRIPT LOAD",
        }.get(method, method.upper())
        batch = "" if handle.kind == "pipeline" else (_MANY.get(method, "") or "a pipeline()")
        if method in _READS:
            if method == "keys":
                return Use(
                    operation,
                    "reads",
                    target,
                    flag="KEYS blocks Redis",
                    batch=batch,
                    why=(
                        "walks every key in the database, and Redis answers nothing else until it's done: on a big "
                        "database that stalls every client. Use scan_iter(match=...) instead."
                    ),
                )
            return Use(operation, "reads", target, batch=batch)
        if method in _WRITES:
            if method in ("flushdb", "flushall"):
                return Use(
                    operation,
                    "writes",
                    flag="empties the database",
                    why=(
                        f"deletes every key{' in every database' if method == 'flushall' else ''}: make sure this can only "
                        "run where that's meant."
                    ),
                )
            return Use(operation, "writes", target, batch=batch)
        if method in _SENDS:
            return Use(operation, "sends", target, icon="queue", batch=batch if method == "xadd" else "")
        if method in _RUNS:
            return Use("EVAL" if method == "eval" else operation, "runs", "a Lua script")
        return None

    def describe(self, handle: Handle) -> str:
        return {
            "client": "a Redis client",
            "pool": "a Redis connection pool",
            "pipeline": "a Redis pipeline",
            "pubsub": "a Redis pub/sub",
            "lock": "a Redis lock",
        }.get(handle.kind, "a Redis " + handle.kind)
