"""
The Lambda function: an S3 upload of an orders file comes in, each order is checked, saved and announced.
"""

import json
import logging
import os

import boto3

from .store import OrderStore
from .notify import announce

log = logging.getLogger(__name__)
s3 = boto3.client("s3")
store = OrderStore(os.environ["ORDERS_TABLE"])


def read_orders(bucket, key):
    """Read one uploaded file of orders (JSON lines)."""
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    return [json.loads(line) for line in body.splitlines() if line]


def check(order):
    """An order is good when it has an id, a customer and a positive total."""
    return bool(order.get("id")) and bool(order.get("customer")) and order.get("total", 0) > 0


def lambda_handler(event, context):
    saved = 0
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        for order in read_orders(bucket, key):
            if not check(order):
                log.warning("skipping %s", order.get("id"))
                continue
            store.save(order)
            announce(order)
            saved += 1
    return {"saved": saved}
