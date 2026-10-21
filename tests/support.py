"""
What the tests share: write() puts a small project in a folder, and the projects they write.
"""

from __future__ import annotations

from pathlib import Path

from code_node.analysis.mapping import map_code


def write(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


HANDLER = """
import os
import boto3
import requests

s3 = boto3.client("s3")


def load(bucket, key):
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def lambda_handler(event, context):
    for record in event["Records"]:
        load(record["s3"]["bucket"]["name"], record["s3"]["object"]["key"])
    requests.post(os.environ["HOOK"], json={})
"""


PACKAGE = {
    "pyproject.toml": '[project]\nname = "tool"\n[project.scripts]\ntool = "tool.cli:main"\n',
    "src/tool/__init__.py": "",
    "src/tool/cli.py": "from .store import Store\n\n\ndef main():\n    Store().save('x')\n",
    "src/tool/store.py": (
        "class Store:\n    def save(self, item):\n        self._write(item)\n\n"
        "    def _write(self, item):\n        open('out.txt', 'w').write(item)\n"
    ),
    "tests/test_cli.py": "def main():\n    pass\n",
}


STORES = """
import json
import os
import subprocess

import pymongo
import redis
import sqlite3
from anthropic import Anthropic

cache = redis.Redis(host="cache")
mongo = pymongo.MongoClient(os.environ["MONGO_URL"])
orders = mongo.shop["orders"]
claude = Anthropic(timeout=20)
LOOKUP = "SELECT name FROM users WHERE id = ?"


def handler(event, context):
    body = json.loads(event["body"])
    user = body["user"]
    db = sqlite3.connect("/tmp/app.db")
    name = db.execute(LOOKUP, (user,)).fetchone()
    query = "DELETE FROM sessions WHERE user = '" + user + "'"
    db.execute(query)
    for key in cache.keys("session:*"):
        cache.delete(key)
    orders.insert_one({"user": user})
    found = mongo.get_database("shop").users.find_one({"id": user})
    claude.messages.create(model="claude-sonnet-5-5", max_tokens=200, messages=[])
    subprocess.run(f"echo {body['note']}", shell=True)
    return name, found
"""


FAN = (
    "import os\nimport boto3\n\n\ndef lambda_handler(event, context):\n    route(event)\n\n\n"
    "def route(event):\n"
    + "".join(f"    step{i}()\n" for i in range(8))
    + "\n\n"
    + "".join(f"def step{i}():\n    leaf{i}()\n\n\n" for i in range(8))
    + "".join(f"def leaf{i}():\n    pass\n\n\n" for i in range(8))
    + "def leaf7():\n    boto3.client('s3').put_object(Bucket=os.environ['BUCKET'], Key='k', Body=b'')\n"
)


IMPORTED_FROM_SRC = {
    "src/common/__init__.py": "",
    "src/common/db.py": (
        'import boto3\n\ntable = boto3.resource("dynamodb").Table("orders")\n\n\n'
        "def save(item):\n    table.put_item(Item=item)\n"
    ),
    "src/handlers/orders/app.py": "from common.db import save\n\n\ndef handler(event, context):\n    save(event)\n",
}


def page_blocks_for(project, entry: str) -> list:
    from code_node.report.build import page_blocks

    cmap = map_code(project.files, entry, libraries=project.libraries(), platform="lambda")
    return page_blocks(cmap, project="x", max_functions=24, max_depth=5, sources=project.files)


TESTS = Path(__file__).parent
SNAPSHOTS = TESTS / "snapshots"
EXAMPLES = TESTS.parent / "examples"
