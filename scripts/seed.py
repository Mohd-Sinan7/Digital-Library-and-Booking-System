"""Seed books from CSV into the database through the catalog repository function (DLBS-47).

Loads data/books_sample.csv (20 sample books) or data/books.csv (10,000 full books)
using Member 2's catalog repository function (create_book). Preserves the shared
book_id from the CSV as the primary key id in the database so that reading records
and bookings referencing book_id match across all modules.

Usage from repository root:

    python -m scripts.seed           # seeds data/books.csv if present, else sample
    python -m scripts.seed --sample  # seeds data/books_sample.csv (20 books)
    python -m scripts.seed --file <path>    # seeds from a custom CSV file
    python -m scripts.seed --reset          # clears existing books before seeding
"""

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from src.catalog.models import Book
from src.catalog.service import DuplicateIsbnError, create_book
from src.db import SessionLocal, create_tables

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_SAMPLE_PATH = DATA_DIR / "books_sample.csv"
DEFAULT_FULL_PATH = DATA_DIR / "books.csv"


def parse_book_row(row: dict[str, str]) -> dict[str, Any]:
    """Parse and convert a CSV row into a Book creation dictionary.

    The CSV's book_id is mapped to the database's primary key `id` so that
    identifiers remain shared across catalog, users/reading, and bookings.
    """
    raw_id = row.get("book_id") or row.get("id")
    if not raw_id:
        raise ValueError("Missing book_id in CSV row")

    raw_year = row.get("year")
    year = int(raw_year) if raw_year is not None and str(raw_year).strip() != "" else None

    book_data: dict[str, Any] = {
        "id": int(raw_id),
        "title": row["title"].strip(),
        "author": row["author"].strip(),
        "isbn": row["isbn"].strip(),
        "genre": row["genre"].strip(),
        "description": row.get("description", "").strip(),
        "year": year,
        "page_count": int(row["page_count"]),
        "cover_url": row.get("cover_url", "").strip() or None,
        "total_copies": int(row["total_copies"]),
    }

    if "available_copies" in row and row["available_copies"] is not None:
        avail_str = str(row["available_copies"]).strip()
        if avail_str != "":
            book_data["available_copies"] = int(avail_str)

    return book_data


def resolve_csv_path(file_path: str | Path | None = None, sample: bool = False) -> Path:
    """Determine the CSV path based on options and file existence."""
    if sample:
        return DEFAULT_SAMPLE_PATH
    if file_path:
        p = Path(file_path)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p
    if DEFAULT_FULL_PATH.exists():
        return DEFAULT_FULL_PATH
    return DEFAULT_SAMPLE_PATH


def _seed_session(
    path: Path,
    db: Session,
    reset: bool = False,
    skip_existing: bool = True,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Internal helper to seed books using an active SQLAlchemy session."""
    if not path.exists():
        raise FileNotFoundError(f"Books CSV file not found: {path}")

    bind = db.get_bind()
    create_tables(bind=bind)

    # Optimize SQLite transaction write speed if applicable
    if bind is not None and bind.dialect.name == "sqlite":
        try:
            db.execute(text("PRAGMA synchronous = NORMAL"))
        except Exception:
            pass

    if reset:
        db.execute(delete(Book))
        db.commit()

    existing_ids = set(db.scalars(select(Book.id)))
    existing_isbns = set(db.scalars(select(Book.isbn)))

    loaded = 0
    skipped = 0

    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            try:
                book_data = parse_book_row(row)
            except (ValueError, KeyError) as err:
                raise ValueError(f"Invalid row {i} in {path.name}: {err}") from err

            book_id = book_data["id"]
            isbn = book_data["isbn"]

            if skip_existing and (book_id in existing_ids or isbn in existing_isbns):
                skipped += 1
                continue

            try:
                create_book(book_data, db)
                existing_ids.add(book_id)
                existing_isbns.add(isbn)
                loaded += 1
            except DuplicateIsbnError:
                if skip_existing:
                    skipped += 1
                else:
                    raise

            if progress_callback:
                progress_callback(loaded, skipped)

    return {
        "loaded": loaded,
        "skipped": skipped,
        "total": loaded + skipped,
        "file": str(path),
    }


def seed_books(
    csv_path: str | Path | None = None,
    db: Session | None = None,
    reset: bool = False,
    skip_existing: bool = True,
    sample: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Seed books into the database from a CSV file.

    Parameters
    ----------
    csv_path : str | Path | None
        Path to the CSV file. If None, resolves to data/books.csv or data/books_sample.csv.
    db : Session | None
        SQLAlchemy session. If None, uses SessionLocal() and ensures tables exist.
    reset : bool
        If True, clears existing books table prior to seeding.
    skip_existing : bool
        If True, skips books whose id or ISBN already exists.
    sample : bool
        If True, specifically uses data/books_sample.csv.
    progress_callback : Callable[[int, int], None] | None
        Optional callback invoked with (loaded_count, skipped_count).

    Returns
    -------
    dict
        Summary with keys "loaded", "skipped", "total", and "file".
    """
    path = resolve_csv_path(file_path=csv_path, sample=sample)
    if db is not None:
        return _seed_session(
            path=path,
            db=db,
            reset=reset,
            skip_existing=skip_existing,
            progress_callback=progress_callback,
        )

    create_tables()
    with SessionLocal() as session:
        return _seed_session(
            path=path,
            db=session,
            reset=reset,
            skip_existing=skip_existing,
            progress_callback=progress_callback,
        )


def main() -> None:
    """CLI entrypoint for seeding books."""
    parser = argparse.ArgumentParser(
        description="Seed books from CSV into the library database (DLBS-47)."
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Optional positional path to CSV file.",
    )
    parser.add_argument(
        "-f",
        "--file",
        dest="file_flag",
        default=None,
        help="Path to CSV file (defaults to data/books.csv or data/books_sample.csv).",
    )
    parser.add_argument(
        "-s",
        "--sample",
        action="store_true",
        help="Seed data/books_sample.csv (20 sample books).",
    )
    parser.add_argument(
        "-r",
        "--reset",
        action="store_true",
        help="Clear the books table before seeding.",
    )
    parser.add_argument(
        "--no-skip",
        dest="skip_existing",
        action="store_false",
        default=True,
        help="Fail on duplicates instead of skipping existing books.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress intermediate progress messages.",
    )

    args = parser.parse_args()
    target_file = args.file or args.file_flag

    def report_progress(loaded: int, skipped: int) -> None:
        if not args.quiet and (loaded + skipped) % 1000 == 0:
            print(f"... processed {loaded + skipped} rows ({loaded} loaded, {skipped} skipped)")

    t0 = time.time()
    try:
        result = seed_books(
            csv_path=target_file,
            sample=args.sample,
            reset=args.reset,
            skip_existing=args.skip_existing,
            progress_callback=report_progress,
        )
    except Exception as exc:
        print(f"Error seeding books: {exc}", file=sys.stderr)
        sys.exit(1)

    duration = time.time() - t0
    print(
        f"Seeded books successfully from {Path(result['file']).name}: "
        f"{result['loaded']} loaded, {result['skipped']} skipped "
        f"in {duration:.2f}s."
    )


if __name__ == "__main__":
    main()
