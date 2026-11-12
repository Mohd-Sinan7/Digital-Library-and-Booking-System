"""Seed demo accounts (members & admin) and reading records from data/ CSVs (DLBS-52).

Creates:
- Demo members using Member 3's create_user() function (validates & bcrypt-hashes passwords).
- One admin account using Member 3's create_user(..., role="admin") function.
- Synthetic reading records from data/reading_records.csv linked to the seeded book_id values.

Usage from repository root:

    python -m scripts.seed_demo
    python -m scripts.seed_demo --sample
    python -m scripts.seed_demo --members 25 --records-limit 500
    python -m scripts.seed_demo --all-users
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from scripts.seed import seed_books
from src.catalog.models import Book
from src.db import SessionLocal, create_tables
from src.users.models import ADMIN, FINISHED, MEMBER, WANT_TO_READ, ReadingRecordRow, User
from src.users.service import EmailTakenError, create_user, normalize_email

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_USERS_PATH = DATA_DIR / "users.csv"
DEFAULT_RECORDS_PATH = DATA_DIR / "reading_records.csv"

# Local demo-only default passwords satisfying FR-U1 / NFR-U3 password rules.
DEFAULT_MEMBER_PASSWORD = os.getenv("DEMO_MEMBER_PASSWORD", "DemoMember123")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEMO_ADMIN_PASSWORD", "DemoAdmin123")


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO-8601 UTC timestamp string (with optional trailing 'Z')."""
    if not value or not value.strip():
        return None
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clamp_reading_fields(
    status: str, raw_page: int, raw_percent: float, page_count: int
) -> tuple[int, float]:
    """Ensure current_page and percent satisfy catalog page bounds and DB check constraints."""
    if status == FINISHED:
        return page_count, 100.0
    if status == WANT_TO_READ:
        return 0, 0.0
    clamped_page = min(max(raw_page, 0), page_count)
    if raw_page > page_count and page_count > 0:
        clamped_percent = round((clamped_page / page_count) * 100, 2)
    else:
        clamped_percent = round(min(max(raw_percent, 0.0), 100.0), 2)
    return clamped_page, clamped_percent


def _ensure_demo_user(
    db: Session,
    name: str,
    email: str,
    password: str,
    role: str,
) -> tuple[User, bool]:
    """Create a user via Member 3's create_user() or return the existing account."""
    normalized = normalize_email(email)
    existing = db.scalar(select(User).where(User.email == normalized))
    if existing is not None:
        return existing, False
    try:
        user = create_user(db=db, name=name, email=normalized, password=password, role=role)
        return user, True
    except EmailTakenError:
        existing = db.scalar(select(User).where(User.email == normalized))
        if existing is None:
            raise
        return existing, False


def _seed_demo_session(
    db: Session,
    users_csv: Path,
    records_csv: Path,
    member_limit: int | None = 25,
    records_limit: int | None = None,
    member_password: str = DEFAULT_MEMBER_PASSWORD,
    admin_password: str = DEFAULT_ADMIN_PASSWORD,
    seed_books_mode: str = "auto",
    reset: bool = False,
) -> dict[str, Any]:
    """Seed demo members, one admin account, and reading records into an active session."""
    if not users_csv.exists():
        raise FileNotFoundError(f"Users CSV file not found: {users_csv}")
    if not records_csv.exists():
        raise FileNotFoundError(f"Reading records CSV file not found: {records_csv}")

    bind = db.get_bind()
    create_tables(bind=bind)

    if bind is not None and bind.dialect.name == "sqlite":
        try:
            db.execute(text("PRAGMA synchronous = NORMAL"))
        except Exception:
            pass

    if reset:
        db.execute(delete(ReadingRecordRow))
        db.commit()

    books_summary: dict[str, Any] | None = None
    existing_book_count = db.scalar(select(func.count()).select_from(Book)) or 0
    if seed_books_mode == "full" or (seed_books_mode == "auto" and existing_book_count == 0):
        books_summary = seed_books(db=db, sample=False)
    elif seed_books_mode == "sample":
        books_summary = seed_books(db=db, sample=True)

    with open(users_csv, mode="r", encoding="utf-8") as f:
        user_rows = list(csv.DictReader(f))

    admin_rows = [r for r in user_rows if r.get("role", "").strip().lower() == ADMIN]
    member_rows = [r for r in user_rows if r.get("role", "").strip().lower() != ADMIN]
    if member_limit is not None:
        member_rows = member_rows[:member_limit]

    csv_user_to_db: dict[int, int] = {}
    admins_created = 0
    admins_skipped = 0
    members_created = 0
    members_skipped = 0

    # Create exactly one admin account via Member 3's create_user(..., role=ADMIN).
    if admin_rows:
        admin_row = admin_rows[0]
        admin_email = admin_row["email"].strip()
        admin_name = admin_row["name"].strip() or "Test Admin"
        admin_csv_id = int(admin_row["id"])
    else:
        admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com").strip()
        admin_name = "Test Admin"
        admin_csv_id = 2

    admin_user, created = _ensure_demo_user(
        db=db,
        name=admin_name,
        email=admin_email,
        password=admin_password,
        role=ADMIN,
    )
    csv_user_to_db[admin_csv_id] = admin_user.id
    if created:
        admins_created += 1
    else:
        admins_skipped += 1

    # Seed demo members via Member 3's create_user(..., role=MEMBER).
    for row in member_rows:
        csv_uid = int(row["id"])
        user_obj, created = _ensure_demo_user(
            db=db,
            name=row["name"].strip(),
            email=row["email"].strip(),
            password=member_password,
            role=MEMBER,
        )
        csv_user_to_db[csv_uid] = user_obj.id
        if created:
            members_created += 1
        else:
            members_skipped += 1

    # Build catalog book page_count lookup and existing reading record set for idempotency.
    book_pages = {
        book_id: page_count
        for book_id, page_count in db.execute(select(Book.id, Book.page_count)).all()
    }
    valid_db_user_ids = set(db.scalars(select(User.id)))
    existing_pairs = set(
        db.execute(select(ReadingRecordRow.user_id, ReadingRecordRow.book_id)).all()
    )

    records_loaded = 0
    records_skipped = 0
    records_to_insert: list[ReadingRecordRow] = []

    with open(records_csv, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if records_limit is not None and records_loaded >= records_limit:
                break

            csv_uid = int(row["user_id"])
            db_uid = csv_user_to_db.get(csv_uid)
            if db_uid is None:
                if csv_uid in valid_db_user_ids:
                    db_uid = csv_uid
                else:
                    continue

            book_id = int(row["book_id"])
            page_count = book_pages.get(book_id)
            if page_count is None:
                records_skipped += 1
                continue

            if (db_uid, book_id) in existing_pairs:
                records_skipped += 1
                continue

            status = row["status"].strip()
            raw_page = int(row.get("current_page") or 0)
            raw_percent = float(row.get("percent") or 0.0)
            current_page, percent = _clamp_reading_fields(
                status, raw_page, raw_percent, page_count
            )

            started_at = _parse_utc_timestamp(row.get("started_at"))
            updated_at = _parse_utc_timestamp(row.get("updated_at")) or datetime.now(
                timezone.utc
            )
            if status != WANT_TO_READ and started_at is None:
                started_at = updated_at

            records_to_insert.append(
                ReadingRecordRow(
                    user_id=db_uid,
                    book_id=book_id,
                    status=status,
                    current_page=current_page,
                    percent=percent,
                    started_at=started_at,
                    updated_at=updated_at,
                )
            )
            existing_pairs.add((db_uid, book_id))
            records_loaded += 1

    if records_to_insert:
        db.add_all(records_to_insert)
        db.commit()

    return {
        "books": books_summary,
        "members_created": members_created,
        "members_skipped": members_skipped,
        "admins_created": admins_created,
        "admins_skipped": admins_skipped,
        "records_loaded": records_loaded,
        "records_skipped": records_skipped,
        "demo_member_email": member_rows[0]["email"].strip() if member_rows else None,
        "demo_admin_email": admin_email,
    }


def seed_demo(
    db: Session | None = None,
    users_path: str | Path | None = None,
    records_path: str | Path | None = None,
    member_limit: int | None = 25,
    records_limit: int | None = None,
    member_password: str = DEFAULT_MEMBER_PASSWORD,
    admin_password: str = DEFAULT_ADMIN_PASSWORD,
    seed_books_mode: str = "auto",
    reset: bool = False,
) -> dict[str, Any]:
    """Seed demo members, one admin account, and reading records into the database.

    All accounts are created using Member 3's ``create_user`` function so password
    validation and bcrypt hashing behave identically to live user registration.
    """
    u_path = Path(users_path) if users_path else DEFAULT_USERS_PATH
    r_path = Path(records_path) if records_path else DEFAULT_RECORDS_PATH
    if not u_path.is_absolute():
        u_path = PROJECT_ROOT / u_path
    if not r_path.is_absolute():
        r_path = PROJECT_ROOT / r_path

    if db is not None:
        return _seed_demo_session(
            db=db,
            users_csv=u_path,
            records_csv=r_path,
            member_limit=member_limit,
            records_limit=records_limit,
            member_password=member_password,
            admin_password=admin_password,
            seed_books_mode=seed_books_mode,
            reset=reset,
        )

    create_tables()
    with SessionLocal() as session:
        return _seed_demo_session(
            db=session,
            users_csv=u_path,
            records_csv=r_path,
            member_limit=member_limit,
            records_limit=records_limit,
            member_password=member_password,
            admin_password=admin_password,
            seed_books_mode=seed_books_mode,
            reset=reset,
        )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for seeding demo accounts and synthetic reading records."""
    parser = argparse.ArgumentParser(
        description="Seed demo members, one admin account, and synthetic reading records (DLBS-52)."
    )
    parser.add_argument(
        "--members",
        type=int,
        default=25,
        help="Number of demo members to seed from data/users.csv (default: 25).",
    )
    parser.add_argument(
        "--all-users",
        action="store_true",
        help="Seed all members present in data/users.csv instead of limiting to --members.",
    )
    parser.add_argument(
        "--records-limit",
        type=int,
        default=None,
        help="Optional cap on the number of reading records inserted.",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Seed data/books_sample.csv before seeding demo users and reading records.",
    )
    parser.add_argument(
        "--seed-books",
        choices=("auto", "full", "sample", "none"),
        default="auto",
        help="Book seeding behavior (default: auto seeds books.csv if catalog is empty).",
    )
    parser.add_argument(
        "--member-password",
        default=DEFAULT_MEMBER_PASSWORD,
        help="Password assigned to newly created demo members.",
    )
    parser.add_argument(
        "--admin-password",
        default=DEFAULT_ADMIN_PASSWORD,
        help="Password assigned to the demo admin account.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear existing reading_records rows before seeding.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress summary output.",
    )

    args = parser.parse_args(argv)
    books_mode = "sample" if args.sample else args.seed_books
    member_limit = None if args.all_users else args.members

    summary = seed_demo(
        member_limit=member_limit,
        records_limit=args.records_limit,
        member_password=args.member_password,
        admin_password=args.admin_password,
        seed_books_mode=books_mode,
        reset=args.reset,
    )

    if not args.quiet:
        print(
            f"Demo seed complete: members added={summary['members_created']} "
            f"(skipped={summary['members_skipped']}), "
            f"admins added={summary['admins_created']} "
            f"(skipped={summary['admins_skipped']}), "
            f"reading records added={summary['records_loaded']} "
            f"(skipped={summary['records_skipped']}).",
            flush=True,
        )
        print(
            f"Demo login accounts -> Member: {summary['demo_member_email']} | "
            f"Admin: {summary['demo_admin_email']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
