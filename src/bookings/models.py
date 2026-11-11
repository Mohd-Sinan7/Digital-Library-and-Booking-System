"""Domain models and database table for book reservations and loans (DLBS-45, DLBS-51)."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base


def utc_now() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(UTC)


class BookingStatus(StrEnum):
    RESERVED = "reserved"
    BORROWED = "borrowed"
    RETURNED = "returned"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class BookingRow(Base):
    """Database table for bookings (DLBS-45, DLBS-51).

    Columns:
    - id: Primary key
    - user_id: Foreign key to users.id
    - book_id: Foreign key to books.id
    - status: reserved, borrowed, returned, cancelled, expired
    - reserved_at: timestamp when reserved
    - expires_at: timestamp when hold expires (2 days after reserved_at)
    - borrowed_at: timestamp when loan started
    - due_date: date when book is due (14 days after borrowed_at)
    - returned_at: timestamp when book was returned
    """

    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('reserved', 'borrowed', 'returned', 'cancelled', 'expired')",
            name="ck_bookings_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=BookingStatus.RESERVED.value, index=True
    )
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    borrowed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_active(self) -> bool:
        return self.status in {BookingStatus.RESERVED.value, BookingStatus.BORROWED.value}

    @property
    def is_overdue(self) -> bool:
        return (
            self.status == BookingStatus.BORROWED.value
            and self.due_date is not None
            and date.today() > self.due_date
        )

    @property
    def overdue(self) -> bool:
        """Alias for is_overdue (FR-B6 / DLBS-51 acceptance criteria)."""
        return self.is_overdue


# Alias for readability across modules
BookingTable = BookingRow


@dataclass(frozen=True)
class Booking:
    """Domain model for a booking record."""

    id: int
    user_id: int
    book_id: int
    status: BookingStatus
    reserved_at: datetime | date | None = None
    expires_at: datetime | date | None = None
    borrowed_at: datetime | date | None = None
    due_date: date | None = None
    returned_at: datetime | date | None = None
    created_at: date | None = None

    def __post_init__(self) -> None:
        if self.reserved_at is None and self.created_at is not None:
            object.__setattr__(self, "reserved_at", self.created_at)
        elif self.reserved_at is not None and self.created_at is None:
            d = (
                self.reserved_at.date()
                if isinstance(self.reserved_at, datetime)
                else self.reserved_at
            )
            object.__setattr__(self, "created_at", d)

    @property
    def is_active(self) -> bool:
        return self.status in {BookingStatus.RESERVED, BookingStatus.BORROWED}

    @property
    def is_overdue(self) -> bool:
        return (
            self.status == BookingStatus.BORROWED
            and self.due_date is not None
            and date.today() > self.due_date
        )

    @property
    def overdue(self) -> bool:
        """Alias for is_overdue (FR-B6 / DLBS-51 acceptance criteria)."""
        return self.is_overdue

    def is_overdue_as_of(self, as_of: date) -> bool:
        """Evaluate overdue status relative to a specific reference date (FR-B6)."""
        return (
            self.status == BookingStatus.BORROWED
            and self.due_date is not None
            and as_of > self.due_date
        )
