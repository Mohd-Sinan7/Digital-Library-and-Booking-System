"""Database tables for the Users and Reading Tracking module."""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base

MEMBER = "member"
ADMIN = "admin"


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
