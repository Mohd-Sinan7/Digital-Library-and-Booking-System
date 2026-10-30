"""Database table for the Book Catalog module."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base


def utc_now() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(timezone.utc)


class Book(Base):
    """A book. `id` is the shared book_id used by every module."""

    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint("page_count >= 1", name="ck_books_page_count"),
        CheckConstraint("total_copies >= 0", name="ck_books_total_copies"),
        CheckConstraint(
            "available_copies >= 0 AND available_copies <= total_copies",
            name="ck_books_available_copies",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    author: Mapped[str] = mapped_column(String(255), index=True)
    isbn: Mapped[str] = mapped_column(String(13), unique=True, index=True)
    genre: Mapped[str] = mapped_column(String(50), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer)
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    total_copies: Mapped[int] = mapped_column(Integer)
    available_copies: Mapped[int] = mapped_column(Integer)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    def __init__(self, **fields):
        # available_copies starts equal to total_copies unless given explicitly.
        fields.setdefault("available_copies", fields.get("total_copies"))
        super().__init__(**fields)
