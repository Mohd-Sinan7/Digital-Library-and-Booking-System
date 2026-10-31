"""Unit and integrity tests for the dataset prepared in data/ (DLBS-8)."""

import csv
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def test_dataset_files_exist():
    """All required dataset files and README must exist in data/."""
    expected_files = ["books.csv", "users.csv", "reading_records.csv", "README.md"]
    for filename in expected_files:
        path = os.path.join(DATA_DIR, filename)
        assert os.path.exists(path), f"Missing dataset file: {filename}"
        assert os.path.getsize(path) > 0, f"Dataset file is empty: {filename}"


def test_books_csv_schema_and_constraints():
    """books.csv must have 10,000 books, unique ISBNs, and conform to DB constraints."""
    filepath = os.path.join(DATA_DIR, "books.csv")
    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == [
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
        ]
        rows = list(reader)

    assert len(rows) == 10000, f"Expected 10,000 books, got {len(rows)}"

    seen_ids = set()
    seen_isbns = set()

    for row in rows:
        bid = int(row["book_id"])
        assert bid not in seen_ids, f"Duplicate book_id: {bid}"
        seen_ids.add(bid)

        # ISBN constraints: unique, string length between 10 and 13 (Book.isbn String(13))
        isbn = row["isbn"]
        assert 10 <= len(isbn) <= 13, f"Invalid ISBN length for book {bid}: {isbn}"
        assert isbn not in seen_isbns, f"Duplicate ISBN found: {isbn}"
        seen_isbns.add(isbn)

        # Title & Author non-empty
        assert row["title"].strip(), f"Book {bid} has empty title"
        assert row["author"].strip(), f"Book {bid} has empty author"

        # Genre fits String(50) in DB
        genre = row["genre"]
        assert genre.strip() and len(genre) <= 50, f"Invalid genre for book {bid}: {genre}"

        # Description non-empty for TF-IDF feature extraction
        assert len(row["description"].strip()) > 10, f"Description too short for book {bid}"

        # Year integer (supports BCE years like -720 as well as CE years)
        assert -3000 <= int(row["year"]) <= 2026, f"Invalid year for book {bid}: {row['year']}"

        # Page count between 120 and 900
        page_count = int(row["page_count"])
        assert 120 <= page_count <= 900, f"Page count out of range: {page_count}"

        # Total copies between 1 and 5
        total_copies = int(row["total_copies"])
        assert 1 <= total_copies <= 5, f"Total copies out of range: {total_copies}"

        # Cover URL
        assert row["cover_url"].startswith("http"), f"Invalid cover_url: {row['cover_url']}"


def test_users_csv_schema_and_roles():
    """users.csv must contain 1,000 users with valid roles and seed accounts."""
    filepath = os.path.join(DATA_DIR, "users.csv")
    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == [
            "id",
            "name",
            "email",
            "password_hash",
            "role",
            "created_at",
        ]
        rows = list(reader)

    assert len(rows) == 1000, f"Expected 1,000 users, got {len(rows)}"

    seen_ids = set()
    seen_emails = set()

    for row in rows:
        uid = int(row["id"])
        assert uid not in seen_ids
        seen_ids.add(uid)

        email = row["email"].strip().lower()
        assert email not in seen_emails
        seen_emails.add(email)

        assert row["role"] in {"member", "admin"}
        assert row["password_hash"].startswith("$2b$")
        assert "T" in row["created_at"] and row["created_at"].endswith("Z")

    # Verify seed users
    assert rows[0]["id"] == "1"
    assert rows[0]["email"] == "member@example.com"
    assert rows[0]["role"] == "member"

    assert rows[1]["id"] == "2"
    assert rows[1]["email"] == "admin@example.com"
    assert rows[1]["role"] == "admin"


def test_reading_records_csv_integrity():
    """reading_records.csv must match books and users and have valid progress."""
    books_file = os.path.join(DATA_DIR, "books.csv")
    with open(books_file, encoding="utf-8") as f:
        book_pages = {int(r["book_id"]): int(r["page_count"]) for r in csv.DictReader(f)}

    users_file = os.path.join(DATA_DIR, "users.csv")
    with open(users_file, encoding="utf-8") as f:
        valid_user_ids = {int(r["id"]) for r in csv.DictReader(f)}

    records_file = os.path.join(DATA_DIR, "reading_records.csv")
    with open(records_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == [
            "user_id",
            "book_id",
            "status",
            "current_page",
            "percent",
            "started_at",
            "updated_at",
        ]
        records = list(reader)

    assert len(records) > 10000, f"Expected >10,000 reading records, got {len(records)}"

    user_1_records = [r for r in records if int(r["user_id"]) == 1]
    assert len(user_1_records) >= 10, "User 1 must have reading records for demo testing"

    for r in records:
        uid = int(r["user_id"])
        bid = int(r["book_id"])
        assert uid in valid_user_ids, f"Unknown user_id: {uid}"
        assert bid in book_pages, f"Unknown book_id: {bid}"

        status = r["status"]
        assert status in {"want_to_read", "reading", "finished"}

        curr_page = int(r["current_page"])
        percent = float(r["percent"])
        total_pages = book_pages[bid]

        assert 0 <= curr_page <= total_pages
        assert 0.0 <= percent <= 100.0

        if status == "finished":
            assert percent == 100.0
            assert curr_page == total_pages
            assert r["started_at"] != ""
        elif status == "want_to_read":
            assert percent == 0.0
            assert curr_page == 0
            assert r["started_at"] == ""


def test_readme_provenance_documentation():
    """README.md in data/ must document real vs generated columns and seed."""
    readme_path = os.path.join(DATA_DIR, "README.md")
    with open(readme_path, encoding="utf-8") as f:
        text = f.read()

    assert "Goodbooks-10k" in text
    assert "Real" in text
    assert "Generated" in text
    assert "Derived" in text
    assert "42" in text
    assert "books.csv" in text
    assert "users.csv" in text
    assert "reading_records.csv" in text
