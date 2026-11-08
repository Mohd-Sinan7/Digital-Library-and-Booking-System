"""Every book in the dataset fits the catalog's columns (found while deploying, DLBS-42).

SQLite never checks VARCHAR lengths, but PostgreSQL does, so a value that is too long
only fails in Docker and on the deployed app.
"""

import csv
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.seed import parse_book_row
from src.catalog.models import Book
from src.catalog.schemas import BookCreate, BookUpdate

DATA = Path(__file__).resolve().parents[2] / "data"
LIMITS = {
    column.name: column.type.length
    for column in Book.__table__.columns
    if getattr(column.type, "length", None)
}


@pytest.mark.parametrize("csv_name", ["books.csv", "books_sample.csv"])
def test_every_book_fits_the_columns(csv_name):
    with open(DATA / csv_name, encoding="utf-8") as f:
        books = [parse_book_row(row) for row in csv.DictReader(f)]

    too_long = [
        (book["id"], name, len(book[name]))
        for book in books
        for name, limit in LIMITS.items()
        if book.get(name) and len(book[name]) > limit
    ]
    assert too_long == []


def book(author: str) -> dict:
    return {"title": "Collected Essays", "author": author, "isbn": "9780306406157",
            "genre": "Essays", "page_count": 300, "total_copies": 1, "description": ""}


def test_long_co_author_list_is_accepted():
    authors = ", ".join(f"Author Number {n}" for n in range(50))  # 888 characters

    assert BookCreate(**book(authors)).author == authors
    assert BookUpdate(author=authors).author == authors


def test_author_over_1000_characters_is_rejected():
    with pytest.raises(ValidationError):
        BookCreate(**book("x" * 1001))
