"""Reading history, called in-process by Member 1's recommender (FR-U7).

    from src.users import reading

    records = reading.get_history(user_id)

The signature and ReadingRecord shape are agreed in docs/api-contract.md.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db import SessionLocal
from src.users.models import ReadingRecordRow


@dataclass(frozen=True)
class ReadingRecord:
    """One book in a user's reading history."""

    book_id: int
    status: str                  # "want_to_read", "reading" or "finished"
    current_page: int
    percent: float               # 0 to 100
    started_at: datetime | None  # UTC; None until the user starts reading
    updated_at: datetime         # UTC


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


def get_history(user_id: int, db: Session | None = None) -> list[ReadingRecord]:
    """Return all of the user's reading records, newest updated_at first.

    Returns an empty list for a user with no records or a user_id that does not
    exist. Without a session it opens its own.
    """
    query = (
        select(ReadingRecordRow)
        .where(ReadingRecordRow.user_id == user_id)
        .order_by(ReadingRecordRow.updated_at.desc(), ReadingRecordRow.id.desc())
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
