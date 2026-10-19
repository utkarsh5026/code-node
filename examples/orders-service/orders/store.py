"""
Where orders are kept: a DynamoDB table, and an archive bucket for each customer's history.
"""

import json
import os

import boto3


class OrderStore:
    def __init__(self, table_name):
        self.table = boto3.resource("dynamodb").Table(table_name)
        self.archive = boto3.client("s3")

    def save(self, order):
        """Save an order, and keep a copy in the archive."""
        self.table.put_item(Item=order)
        self._archive(order)

    def _archive(self, order):
        key = f"{order['customer']}/{order['id']}.json"
        self.archive.put_object(Bucket=os.environ["ARCHIVE_BUCKET"], Key=key, Body=json.dumps(order))

    def recent(self, customer):
        """A customer's orders: the first page of them."""
        return self.table.query(KeyConditionExpression="customer = :c",
                                ExpressionAttributeValues={":c": customer})["Items"]
