"""Reading status, progress and history (FR-U5, FR-U6, FR-U7).

Member 1's recommender calls get_history() in-process:

    from src.users import reading

    records = reading.get_history(user_id)

The REST endpoints in src/users/reading_routes.py use the other functions, which
return the reading record JSON shape. Both shapes are agreed in docs/api-contract.md.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog import get_book
from src.catalog.models import Book
from src.db import SessionLocal
from src.users.models import FINISHED, READING, WANT_TO_READ, ReadingRecordRow, utc_now


@dataclass(frozen=True)
class ReadingRecord:
    """One book in a user's reading history."""

    book_id: int
    status: str                  # "want_to_read", "reading" or "finished"
    current_page: int
    percent: float               # 0 to 100
    started_at: datetime | None  # UTC; None until the user starts reading
    updated_at: datetime         # UTC


class BookNotFoundError(LookupError):
    """The book is not in the catalog, or has been removed (HTTP 404)."""


class InvalidProgressError(ValueError):
    """Progress outside 0 to 100% or past the book's last page (HTTP 422)."""


@contextmanager
def _session(db: Session | None):
    if db is not None:
        yield db
    else:
        with SessionLocal() as own:
            yield own


def _utc(value: datetime | None) -> datetime | None:
    # SQLite drops the timezone; every stored time is UTC.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _iso(value: datetime | None) -> str | None:
    return None if value is None else _utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


NEWEST_FIRST = (ReadingRecordRow.updated_at.desc(), ReadingRecordRow.id.desc())


def get_history(user_id: int, db: Session | None = None) -> list[ReadingRecord]:
    """Return all of the user's reading records, newest updated_at first.

    Returns an empty list for a user with no records or a user_id that does not
    exist. Without a session it opens its own.
    """
    query = (
        select(ReadingRecordRow).where(ReadingRecordRow.user_id == user_id).order_by(*NEWEST_FIRST)
    )
    with _session(db) as session:
        return [
            ReadingRecord(
                book_id=row.book_id,
                status=row.status,
                current_page=row.current_page,
                percent=row.percent,
                started_at=_utc(row.started_at),
                updated_at=_utc(row.updated_at),
            )
            for row in session.scalars(query)
        ]


def to_dict(row: ReadingRecordRow, title: str, author: str, genre: str) -> dict:
    """Reading record JSON shape from docs/api-contract.md."""
    return {
        "book_id": row.book_id,
        "title": title,
        "author": author,
        "genre": genre,
        "status": row.status,
        "current_page": row.current_page,
        "percent": row.percent,
        "started_at": _iso(row.started_at),
        "updated_at": _iso(row.updated_at),
    }


def list_history(user_id: int, db: Session, status: str | None = None) -> list[dict]:
    """The user's reading records with book details, newest first (FR-U7).

    Title, author and genre come from the catalog's books table, removed books included.
    """
    query = (
        select(ReadingRecordRow, Book)
        .join(Book, Book.id == ReadingRecordRow.book_id)
        .where(ReadingRecordRow.user_id == user_id)
        .order_by(*NEWEST_FIRST)
    )
    if status is not None:
        query = query.where(ReadingRecordRow.status == status)
    return [to_dict(row, book.title, book.author, book.genre) for row, book in db.execute(query)]


def _catalog_book(book_id: int, db: Session) -> dict:
    book = get_book(book_id, db=db)
    if book is None:
        raise BookNotFoundError("Book not found")
    return book


def _record_for(user_id: int, book_id: int, db: Session) -> ReadingRecordRow:
    """The user's record for the book, created as want_to_read if there is none."""
    row = db.scalar(
        select(ReadingRecordRow).where(
            ReadingRecordRow.user_id == user_id, ReadingRecordRow.book_id == book_id
        )
    )
    if row is None:
        row = ReadingRecordRow(user_id=user_id, book_id=book_id, status=WANT_TO_READ)
        db.add(row)
    return row


def _save(row: ReadingRecordRow, book: dict, db: Session) -> dict:
    db.commit()
    db.refresh(row)
    return to_dict(row, book["title"], book["author"], book["genre"])


def set_status(user_id: int, book_id: int, status: str, db: Session) -> dict:
    """Set the user's reading status for a book, creating the record if needed (FR-U5).

    Moving to reading or finished records started_at. Finished also sets progress to
    the book's last page, so the book counts fully in the reading statistics.
    """
    book = _catalog_book(book_id, db)
    row = _record_for(user_id, book_id, db)
    row.status = status
    if status != WANT_TO_READ and row.started_at is None:
        row.started_at = utc_now()
    if status == FINISHED:
        row.current_page, row.percent = book["page_count"], 100.0
    return _save(row, book, db)


def record_progress(
    user_id: int,
    book_id: int,
    db: Session,
    current_page: int | None = None,
    percent: float | None = None,
) -> dict:
    """Record progress as a page number or a percentage, not both (FR-U6).

    percent is calculated from current_page and the book's page_count, or the other
    way round. Any progress below 100% makes the status reading; 100% makes it finished.
    """
    if (current_page is None) == (percent is None):
        raise InvalidProgressError("Send exactly one of current_page or percent")
    book = _catalog_book(book_id, db)
    page_count = book["page_count"]
    if current_page is not None:
        if not 0 <= current_page <= page_count:
            raise InvalidProgressError(f"current_page must be between 0 and {page_count}")
        percent = round(current_page / page_count * 100, 2)
    else:
        if not 0 <= percent <= 100:
            raise InvalidProgressError("percent must be between 0 and 100")
        current_page = round(page_count * percent / 100)

    row = _record_for(user_id, book_id, db)
    row.current_page, row.percent = current_page, percent
    row.status = FINISHED if percent >= 100 else READING
    if row.started_at is None:
        row.started_at = utc_now()
    return _save(row, book, db)
