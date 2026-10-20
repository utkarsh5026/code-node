"""
The books database, in PostgreSQL.
"""

import os

import psycopg2

BOOK = "SELECT id, title, author FROM books WHERE id = %s"


def connect():
    """Open a connection to the books database."""
    return psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=5)


def book(conn, book_id):
    """One book by its id."""
    with conn.cursor() as cur:
        cur.execute(BOOK, (book_id,))
        return cur.fetchone()


def search(conn, text, limit):
    """Books whose title has the text in it."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT id, title FROM books WHERE title ILIKE '%{text}%' LIMIT {limit}")
        return cur.fetchall()


def add_review(conn, book_id, user, rating, text):
    """Save a reader's review."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO reviews (book_id, reader, rating, text) VALUES (%s, %s, %s, %s)",
                    (book_id, user, rating, text))
    conn.commit()
