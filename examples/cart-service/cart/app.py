"""
The checkout Lambda function: API Gateway posts a cart, it's priced from the database, the cart is cleared, the
receipt is saved, cached for the customer's next visit and announced, with a sentence about it from a model.
"""

import json
import os

import boto3
import redis

from . import db
from .assistant import summary

cache = redis.Redis(host=os.environ["REDIS_HOST"], socket_timeout=2)
receipts = boto3.resource("dynamodb").Table(os.environ["RECEIPTS_TABLE"])
sns = boto3.client("sns")


def on_checkout(event, context):
    cart = json.loads(event["body"])
    customer = cart["customer"]
    conn = db.connect()
    total = 0
    for item in cart["items"]:
        total += db.price(conn, item["sku"]) * item["quantity"]
    db.clear_cart(conn, customer)
    receipt = {"customer": customer, "total": total, "note": summary(cart["items"], total)}
    receipts.put_item(Item=receipt)
    cache.setex(f"receipt:{customer}", 3600, json.dumps(receipt))
    sns.publish(TopicArn=os.environ["TOPIC_ARN"], Message=json.dumps(receipt))
    return {"statusCode": 200, "body": json.dumps(receipt)}
