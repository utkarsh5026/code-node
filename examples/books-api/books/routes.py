"""
The books API's routes.
"""

import json
import os
import subprocess

import boto3
import redis
import requests
from fastapi import APIRouter, Header
from pydantic import BaseModel

from . import db

router = APIRouter()
cache = redis.Redis(host=os.environ["REDIS_HOST"], socket_timeout=2)
s3 = boto3.client("s3")


class Review(BaseModel):
    rating: int
    text: str


@router.get("/books/{book_id}")
def get_book(book_id: int):
    cached = cache.get(f"book:{book_id}")
    if cached:
        return json.loads(cached)
    found = db.book(db.connect(), book_id)
    cache.setex(f"book:{book_id}", 300, json.dumps(found))
    return found


@router.get("/books")
def search(q: str, limit: int = 20):
    return db.search(db.connect(), q, limit)


@router.post("/books/{book_id}/reviews")
def add_review(book_id: int, review: Review, user: str = Header(alias="x-reader")):
    db.add_review(db.connect(), book_id, user, review.rating, review.text)
    cache.delete(f"book:{book_id}")


@router.put("/books/{book_id}/cover")
async def set_cover(book_id: int, url: str):
    image = requests.get(url).content
    s3.put_object(Bucket=os.environ["COVERS_BUCKET"], Key=f"covers/{book_id}.jpg", Body=image)
    return {"cover": f"covers/{book_id}.jpg"}


@router.get("/books/{book_id}/export")
def export(book_id: int, fmt: str = "pdf"):
    subprocess.run(f"pandoc books/{book_id}.md -o exports/{book_id}.{fmt}", shell=True, check=True)
    return {"file": f"exports/{book_id}.{fmt}"}
