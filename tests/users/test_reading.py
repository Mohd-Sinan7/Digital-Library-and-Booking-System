from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.catalog.models import Book
from src.db import create_tables
from src.users import reading
from src.users.models import FINISHED, READING, WANT_TO_READ, ReadingRecordRow, User

START = datetime(2026, 10, 30, 10, 15, tzinfo=timezone.utc)


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    create_tables(engine)
    return engine


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        session.add_all([
            User(id=1, name="Asha Rao", email="asha@example.com", password_hash="hashed"),
            User(id=2, name="Ravi Kumar", email="ravi@example.com", password_hash="hashed"),
        ])
        session.add_all([
            Book(id=book_id, title=f"Book {book_id}", author="Author", isbn=f"97800000000{book_id}",
                 genre="Fiction", page_count=320, total_copies=2)
            for book_id in (41, 42, 43)
        ])
        session.commit()
        yield session


def add_record(session, **overrides):
    fields = {"user_id": 1, "book_id": 42}
    fields.update(overrides)
    record = ReadingRecordRow(**fields)
    session.add(record)
    session.commit()
    return record


def test_reading_records_table_has_the_designed_columns(engine):
    columns = {column["name"] for column in inspect(engine).get_columns("reading_records")}

    assert columns == {"id", "user_id", "book_id", "status", "current_page", "percent",
                       "started_at", "updated_at"}


def test_new_record_starts_as_want_to_read_with_no_progress(session):
    record = add_record(session)

    assert (record.status, record.current_page, record.percent) == (WANT_TO_READ, 0, 0.0)
    assert record.started_at is None
    assert record.updated_at is not None


def test_one_record_per_user_and_book(session):
    add_record(session)

    with pytest.raises(IntegrityError):
        add_record(session, status=READING)


@pytest.mark.parametrize("overrides", [
    {"status": "abandoned"},
    {"current_page": -1},
    {"percent": -0.5},
    {"percent": 100.5},
])
def test_invalid_values_are_rejected(session, overrides):
    with pytest.raises(IntegrityError):
        add_record(session, **overrides)


def test_empty_history_for_a_user_with_no_records(session):
    assert reading.get_history(1, db=session) == []


def test_empty_history_for_an_unknown_user(session):
    assert reading.get_history(999, db=session) == []


def test_history_is_newest_first_and_only_for_that_user(session):
    add_record(session, book_id=41, status=FINISHED, current_page=320, percent=100.0,
               started_at=START, updated_at=START + timedelta(days=1))
    add_record(session, book_id=42, status=READING, current_page=120, percent=37.5,
               started_at=START, updated_at=START + timedelta(days=3))
    add_record(session, book_id=43, updated_at=START + timedelta(days=2))
    add_record(session, user_id=2, book_id=42, updated_at=START + timedelta(days=4))

    history = reading.get_history(1, db=session)

    assert [record.book_id for record in history] == [42, 43, 41]
    assert history[0] == reading.ReadingRecord(
        book_id=42,
        status=READING,
        current_page=120,
        percent=37.5,
        started_at=START,
        updated_at=START + timedelta(days=3),
    )
    assert history[1].started_at is None


def test_history_times_are_utc(session):
    add_record(session, started_at=START, updated_at=START)

    record = reading.get_history(1, db=session)[0]

    assert record.started_at.tzinfo == timezone.utc
    assert record.updated_at.tzinfo == timezone.utc


def test_get_history_opens_its_own_session_when_none_is_given(engine, session, monkeypatch):
    add_record(session)
    monkeypatch.setattr(reading, "SessionLocal", lambda: Session(engine))

    assert [record.book_id for record in reading.get_history(1)] == [42]
