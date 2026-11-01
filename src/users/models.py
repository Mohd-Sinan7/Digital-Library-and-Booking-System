"""Database tables for the Users and Reading Tracking module."""

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.catalog.models import Book
from src.db import Base

MEMBER = "member"
ADMIN = "admin"

WANT_TO_READ = "want_to_read"
READING = "reading"
FINISHED = "finished"


def utc_now() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(timezone.utc)


class User(Base):
    """A user account: email is unique, role is member or admin (FR-U3)."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"role IN ('{MEMBER}', '{ADMIN}')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10), default=MEMBER)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReadingRecordRow(Base):
    """A user's reading status and progress for one book (FR-U5, FR-U6, FR-U7).

    One row per user and book. percent is calculated from current_page and the
    book's page_count in the catalog.
    """

    __tablename__ = "reading_records"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_reading_records_user_book"),
        CheckConstraint(
            f"status IN ('{WANT_TO_READ}', '{READING}', '{FINISHED}')",
            name="ck_reading_records_status",
        ),
        CheckConstraint("current_page >= 0", name="ck_reading_records_current_page"),
        CheckConstraint("percent >= 0 AND percent <= 100", name="ck_reading_records_percent"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id, ondelete="CASCADE"), index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey(Book.id))
    status: Mapped[str] = mapped_column(String(20), default=WANT_TO_READ)
    current_page: Mapped[int] = mapped_column(Integer, default=0)
    percent: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
