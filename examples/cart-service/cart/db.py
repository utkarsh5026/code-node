"""
The cart database: product prices and saved carts, in PostgreSQL.
"""

import os

import psycopg2

PRICE = "SELECT price FROM products WHERE sku = %s"


def connect():
    """Open a connection to the cart database."""
    return psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=5)


def price(conn, sku):
    """The price of one product."""
    with conn.cursor() as cur:
        cur.execute(PRICE, (sku,))
        return cur.fetchone()[0]


def clear_cart(conn, customer):
    """Empty a customer's saved cart once it's checked out."""
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM carts WHERE customer = '{customer}'")
    conn.commit()
