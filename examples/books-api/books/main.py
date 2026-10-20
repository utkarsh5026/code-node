"""
The books API: a FastAPI app that looks books up, searches them, takes reviews, sets covers and exports a book.
"""

from fastapi import FastAPI

from . import routes

app = FastAPI(title="Books")
app.include_router(routes.router)
