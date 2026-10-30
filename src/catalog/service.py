"""Catalog functions used by the REST routes and called in-process by other modules.

Each function takes an optional SQLAlchemy session. Without one it opens its own.
"""

import math
from contextlib import contextmanager

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.catalog.models import Book
from src.db import SessionLocal


@contextmanager
def _session(db: Session | None):
    if db is not None:
        yield db
    else:
        with SessionLocal() as own:
            yield own


def to_dict(book: Book, include_deleted: bool = False) -> dict:
    """Book JSON shape from docs/api-contract.md."""
    data = {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "isbn": book.isbn,
        "genre": book.genre,
        "description": book.description,
        "year": book.year,
        "page_count": book.page_count,
        "cover_url": book.cover_url,
        "total_copies": book.total_copies,
        "available_copies": book.available_copies,
        # Stored as UTC; SQLite drops the timezone, so format it explicitly.
        "created_at": book.created_at.replace(tzinfo=None).isoformat(timespec="seconds") + "Z",
    }
    if include_deleted:
        data["is_deleted"] = book.is_deleted
    return data


def get_books(
    q: str | None = None,
    genre: str | None = None,
    available: bool | None = None,
    page: int = 1,
    page_size: int | None = None,
    db: Session | None = None,
) -> dict:
    """Search, filter and page the non-deleted books (FR-C4, FR-C5, FR-C7).

    page_size=None returns every match on one page.
    """
    if page < 1:
        raise ValueError("page must be at least 1")
    query = select(Book).where(Book.is_deleted.is_(False))
    if q and q.strip():
        term = q.strip()
        isbn = term.replace("-", "").replace(" ", "")
        query = query.where(
            or_(Book.title.ilike(f"%{term}%"), Book.author.ilike(f"%{term}%"), Book.isbn == isbn)
        )
    if genre:
        query = query.where(func.lower(Book.genre) == genre.strip().lower())
    if available is True:
        query = query.where(Book.available_copies > 0)
    elif available is False:
        query = query.where(Book.available_copies == 0)

    with _session(db) as s:
        total = s.scalar(select(func.count()).select_from(query.subquery()))
        query = query.order_by(Book.title, Book.id)
        if page_size is not None:
            query = query.offset((page - 1) * page_size).limit(page_size)
        items = [to_dict(b) for b in s.scalars(query)]

    size = page_size if page_size is not None else max(total, 1)
    return {
        "items": items,
        "page": page,
        "page_size": size,
        "total": total,
        "total_pages": math.ceil(total / size),
    }


def get_book(book_id: int, include_deleted: bool = False, db: Session | None = None) -> dict | None:
    """One book, or None if missing (or deleted, unless include_deleted)."""
    with _session(db) as s:
        book = s.get(Book, book_id)
        if book is None or (book.is_deleted and not include_deleted):
            return None
        return to_dict(book, include_deleted)


def _availability(book: Book) -> dict:
    return {
        "book_id": book.id,
        "total_copies": book.total_copies,
        "available_copies": book.available_copies,
        "is_available": book.available_copies > 0 and not book.is_deleted,
        "is_deleted": book.is_deleted,
    }


def get_availability(book_id: int, db: Session | None = None) -> dict | None:
    """Copy counts for booking. Works for deleted books so returns still work."""
    with _session(db) as s:
        book = s.get(Book, book_id)
        return None if book is None else _availability(book)


def change_available_copies(book_id: int, delta: int, db: Session) -> dict:
    """Only the booking module calls this: -1 on reserve/borrow, +1 on cancel/return.

    Runs in the caller's session; the caller commits, so booking and count save together.
    """
    book = db.get(Book, book_id)
    if book is None:
        raise ValueError("Book not found")
    if delta < 0 and book.is_deleted:
        raise ValueError("Book has been removed")
    new = book.available_copies + delta
    if not 0 <= new <= book.total_copies:
        raise ValueError("available_copies would go out of range")
    book.available_copies = new
    db.flush()
    return _availability(book)
