"""Domain models for book reservations and loans."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class BookingStatus(StrEnum):
    RESERVED = "reserved"
    BORROWED = "borrowed"
    RETURNED = "returned"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class Booking:
    id: int
    user_id: int
    book_id: int
    status: BookingStatus
    created_at: date
    due_date: date | None = None
    returned_at: date | None = None

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
