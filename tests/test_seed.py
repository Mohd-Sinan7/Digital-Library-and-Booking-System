"""Unit and integration tests for the books seed script (DLBS-47)."""

import csv
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from scripts.seed import (
    DEFAULT_SAMPLE_PATH,
    main,
    parse_book_row,
    resolve_csv_path,
    seed_books,
)
from src.bookings.models import BookingRow
from src.catalog.models import Book
from src.catalog.service import DuplicateIsbnError
from src.db import create_tables
from src.users.models import ReadingRecordRow


@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database session for testing."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_tables(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_parse_book_row_valid():
    """Verify parse_book_row correctly maps CSV headers and types."""
    csv_row = {
        "book_id": "42",
        "title": " The Hitchhiker's Guide to the Galaxy ",
        "author": "Douglas Adams ",
        "isbn": "9790000000042",
        "genre": "Science Fiction",
        "description": "Don't Panic.",
        "year": "1979",
        "page_count": "224",
        "cover_url": "https://covers.example.org/42.jpg",
        "total_copies": "3",
    }
    parsed = parse_book_row(csv_row)
    assert parsed["id"] == 42
    assert parsed["title"] == "The Hitchhiker's Guide to the Galaxy"
    assert parsed["author"] == "Douglas Adams"
    assert parsed["isbn"] == "9790000000042"
    assert parsed["genre"] == "Science Fiction"
    assert parsed["description"] == "Don't Panic."
    assert parsed["year"] == 1979
    assert parsed["page_count"] == 224
    assert parsed["cover_url"] == "https://covers.example.org/42.jpg"
    assert parsed["total_copies"] == 3


def test_parse_book_row_missing_id():
    """Verify parse_book_row raises ValueError when book_id is missing."""
    with pytest.raises(ValueError, match="Missing book_id"):
        parse_book_row({"title": "Test", "author": "Author"})


def test_resolve_csv_path():
    """Verify resolve_csv_path handles sample flag and explicit paths."""
    sample_path = resolve_csv_path(sample=True)
    assert sample_path == DEFAULT_SAMPLE_PATH

    custom_path = resolve_csv_path(file_path="data/books_sample.csv")
    assert custom_path.name == "books_sample.csv"


def test_seed_books_sample(db_session):
    """Seed sample books and verify shared IDs, copy counts, and attributes."""
    result = seed_books(sample=True, db=db_session)
    assert result["loaded"] == 20
    assert result["skipped"] == 0

    books = list(db_session.scalars(select(Book).order_by(Book.id)))
    assert len(books) == 20

    # Verify Book 1 corresponds to Pride and Prejudice with matching shared book_id
    b1 = db_session.get(Book, 1)
    assert b1 is not None
    assert b1.id == 1
    assert b1.title == "Pride and Prejudice"
    assert b1.author == "Jane Austen"
    assert b1.isbn == "9790000000018"
    assert b1.genre == "Romance"
    assert b1.year == 1813
    assert b1.page_count == 432
    assert b1.total_copies == 4
    assert b1.available_copies == 4
    assert b1.is_deleted is False


def test_seed_books_idempotency_and_skip_existing(db_session):
    """Running seed a second time skips already loaded books without duplicate errors."""
    res1 = seed_books(sample=True, db=db_session)
    assert res1["loaded"] == 20
    assert res1["skipped"] == 0

    res2 = seed_books(sample=True, db=db_session)
    assert res2["loaded"] == 0
    assert res2["skipped"] == 20

    count = len(list(db_session.scalars(select(Book.id))))
    assert count == 20


def test_seed_books_reset(db_session):
    """Verify reset=True removes existing books before re-seeding."""
    seed_books(sample=True, db=db_session)
    assert len(list(db_session.scalars(select(Book.id)))) == 20

    res = seed_books(sample=True, db=db_session, reset=True)
    assert res["loaded"] == 20
    assert res["skipped"] == 0
    assert len(list(db_session.scalars(select(Book.id)))) == 20


def test_seed_calls_member2_repository_function(db_session):
    """Verify seed_books routes all insertions through Member 2's create_book function."""
    with patch("scripts.seed.create_book") as mock_create_book:
        mock_create_book.return_value = {"id": 1}
        seed_books(sample=True, db=db_session)
        assert mock_create_book.call_count == 20
        first_call_args = mock_create_book.call_args_list[0]
        book_data, session = first_call_args[0]
        assert book_data["id"] == 1
        assert book_data["title"] == "Pride and Prejudice"
        assert session is db_session


def test_seed_custom_file(tmp_path, db_session):
    """Verify custom CSV file seeding with non-sequential shared book_ids."""
    custom_csv = tmp_path / "custom_books.csv"
    with open(custom_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "book_id",
            "title",
            "author",
            "isbn",
            "genre",
            "description",
            "year",
            "page_count",
            "cover_url",
            "total_copies",
        ])
        writer.writerow([
            "9901",
            "Custom Book One",
            "Author One",
            "9799990000011",
            "Tech",
            "Desc 1",
            "2024",
            "300",
            "http://example.com/1.jpg",
            "5",
        ])
        writer.writerow([
            "9902",
            "Custom Book Two",
            "Author Two",
            "9799990000028",
            "Science",
            "Desc 2",
            "2025",
            "150",
            "http://example.com/2.jpg",
            "2",
        ])

    res = seed_books(csv_path=custom_csv, db=db_session)
    assert res["loaded"] == 2
    assert res["skipped"] == 0

    b1 = db_session.get(Book, 9901)
    b2 = db_session.get(Book, 9902)
    assert b1 is not None and b1.title == "Custom Book One"
    assert b2 is not None and b2.title == "Custom Book Two"


def test_seed_missing_file_raises(db_session):
    """Verify FileNotFoundError is raised when target CSV does not exist."""
    with pytest.raises(FileNotFoundError, match="Books CSV file not found"):
        seed_books(csv_path="non_existent_file.csv", db=db_session)


def test_seed_duplicate_isbn_no_skip_raises(tmp_path, db_session):
    """Verify DuplicateIsbnError is raised if skip_existing is False on duplicate ISBN."""
    custom_csv = tmp_path / "dup_books.csv"
    with open(custom_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "book_id",
            "title",
            "author",
            "isbn",
            "genre",
            "description",
            "year",
            "page_count",
            "cover_url",
            "total_copies",
        ])
        writer.writerow([
            "101",
            "Book A",
            "Author A",
            "9798880000011",
            "Tech",
            "Desc",
            "2024",
            "200",
            "",
            "2",
        ])
        writer.writerow([
            "102",
            "Book B",
            "Author B",
            "9798880000011",  # Same ISBN
            "Tech",
            "Desc",
            "2024",
            "200",
            "",
            "2",
        ])

    with pytest.raises(DuplicateIsbnError):
        seed_books(csv_path=custom_csv, db=db_session, skip_existing=False)


def test_seed_shared_id_integrity_with_booking_and_reading(db_session):
    """Verify seeded book_ids cleanly integrate with BookingRow and ReadingRecordRow."""
    seed_books(sample=True, db=db_session)

    # Book 1 seeded from CSV
    b1 = db_session.get(Book, 1)
    assert b1 is not None

    # Member creates booking for seeded book_id=1
    booking = BookingRow(
        id=101,
        user_id=1,
        book_id=b1.id,
        status="reserved",
    )
    db_session.add(booking)

    # Member creates reading record for seeded book_id=1
    reading = ReadingRecordRow(
        user_id=1,
        book_id=b1.id,
        status="reading",
        current_page=100,
        percent=round(100 / b1.page_count * 100, 1),
    )
    db_session.add(reading)
    db_session.commit()

    saved_booking = db_session.get(BookingRow, 101)
    assert saved_booking is not None
    assert saved_booking.book_id == 1

    saved_reading = db_session.scalar(
        select(ReadingRecordRow).where(
            ReadingRecordRow.user_id == 1, ReadingRecordRow.book_id == 1
        )
    )
    assert saved_reading is not None
    assert saved_reading.book_id == 1
    assert saved_reading.current_page == 100


def test_seed_main_cli_sample(monkeypatch, tmp_path):
    """Verify main() CLI execution with --sample flag."""
    test_db = tmp_path / "cli_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{test_db}")

    # Reload engine configuration with new DATABASE_URL
    import src.db as db_mod

    db_mod.DATABASE_URL = f"sqlite:///{test_db}"
    db_mod.engine = create_engine(
        f"sqlite:///{test_db}",
        connect_args={"check_same_thread": False},
    )
    db_mod.SessionLocal.configure(bind=db_mod.engine)

    test_args = ["seed.py", "--sample", "--quiet"]
    with patch("sys.argv", test_args):
        main()

    with db_mod.SessionLocal() as s:
        book_count = len(list(s.scalars(select(Book.id))))
        assert book_count == 20
