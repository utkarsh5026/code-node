"""
MongoDB through PyMongo (and Motor, its async twin): a client, its databases and their collections, by attribute
or by name, and what each collection method does.
"""

from __future__ import annotations

from typing import Any

from . import Call, Handle, Library, Use

_CLIENTS = ("MongoClient", "AsyncMongoClient", "AsyncIOMotorClient", "MotorClient")

_CLIENT_METHODS = frozenset(
    {
        "get_database",
        "get_default_database",
        "list_database_names",
        "list_databases",
        "drop_database",
        "close",
        "start_session",
        "server_info",
        "watch",
        "address",
        "options",
        "admin",
        "bulk_write",
        "with_options",
    }
)

_DATABASE_METHODS = frozenset(
    {
        "get_collection",
        "list_collection_names",
        "list_collections",
        "create_collection",
        "drop_collection",
        "command",
        "aggregate",
        "watch",
        "client",
        "name",
        "with_options",
        "validate_collection",
        "dereference",
        "cursor_command",
    }
)

_READS = frozenset(
    {
        "find",
        "find_one",
        "count_documents",
        "estimated_document_count",
        "distinct",
        "aggregate",
        "watch",
        "find_raw_batches",
        "aggregate_raw_batches",
        "list_indexes",
        "index_information",
        "options",
    }
)

_WRITES = frozenset(
    {
        "insert_one",
        "insert_many",
        "update_one",
        "update_many",
        "replace_one",
        "delete_one",
        "delete_many",
        "find_one_and_update",
        "find_one_and_replace",
        "find_one_and_delete",
        "bulk_write",
        "create_index",
        "create_indexes",
        "drop_index",
        "drop_indexes",
        "drop",
        "rename",
    }
)

_COLLECTION_METHODS = _READS | _WRITES | {"with_options", "name", "full_name", "database"}

_MANY = {
    "insert_one": "insert_many()",
    "update_one": "bulk_write() with UpdateOne",
    "delete_one": "delete_many()",
    "replace_one": "bulk_write() with ReplaceOne",
    "find_one": "one find() with $in",
}


class MongoLibrary(Library):
    """
    PyMongo and Motor: MongoClient(...), client.shop.orders (or client['shop']['orders']), and its methods.
    """

    name = "mongodb"
    title = "MongoDB"
    modules = ("pymongo", "motor")
    icon = "database"

    def make(self, name: str, call: Call) -> Handle | Use | None:
        if name.rsplit(".", 1)[-1] in _CLIENTS:
            return Handle("client", "MongoDB", opens=True)
        return None

    def attribute(self, handle: Handle, name: str) -> Handle | None:
        if name.startswith("_"):
            return None
        if handle.kind == "client" and name not in _CLIENT_METHODS:
            return handle.but("database", database=name)
        if handle.kind == "database" and name not in _DATABASE_METHODS:
            return handle.but("collection", collection=name)
        if handle.kind == "collection" and name not in _COLLECTION_METHODS:  # db.orders.archive: a sub-collection
            return handle.but("collection", collection=f"{handle.fact('collection')}.{name}")
        return None

    def item(self, handle: Handle, key: Any) -> Handle | None:
        name = key if isinstance(key, str) else "?"
        if handle.kind == "client":
            return handle.but("database", database=name)
        if handle.kind == "database":
            return handle.but("collection", collection=name)
        return None

    def call(self, handle: Handle, method: str, call: Call) -> Handle | Use | None:
        if handle.kind == "client" and method in ("get_database", "get_default_database"):
            return handle.but("database", database=str(call.value(0, "name") or "?"))
        if handle.kind == "database" and method in ("get_collection", "create_collection"):
            return handle.but("collection", collection=str(call.value(0, "name") or "?"))
        if handle.kind != "collection":
            return None
        collection = handle.fact("collection")
        flag = why = ""
        where = call.inputs(0, "filter")
        if (
            method in ("find", "find_one", "delete_many", "update_many", "count_documents")
            and where
            and "$where" in call.code(0, "filter", most=400)
        ):
            flag, why = (
                "$where from the input",
                (
                    f"runs JavaScript built from {where[0]} on the server ($where): whoever sends it can run their own. "
                    "Match the fields with a plain filter instead."
                ),
            )
        if method in _READS:
            return Use(method, "reads", collection, flag=flag, why=why, batch=_MANY.get(method, ""))
        if method in _WRITES:
            return Use(method, "writes", collection, flag=flag, why=why, batch=_MANY.get(method, ""))
        return None

    def describe(self, handle: Handle) -> str:
        if handle.kind == "database":
            return f"the MongoDB database {handle.fact('database')}"
        if handle.kind == "collection":
            return f"the MongoDB collection {handle.fact('collection')}"
        return "a MongoDB client"
