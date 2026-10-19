"""
Telling people: an SNS topic for the warehouse, and a webhook for the shop's chat.
"""

import json
import os

import boto3
import requests

sns = boto3.client("sns")


def announce(order):
    """Tell the warehouse, then post to the shop's chat."""
    sns.publish(TopicArn=os.environ["ORDERS_TOPIC"], Message=json.dumps(order))
    post_to_chat(f"New order {order['id']} for {order['total']}")


def post_to_chat(text):
    requests.post(os.environ.get("CHAT_WEBHOOK", "https://chat.example.com/hook"), json={"text": text})
