"""Booking use-case boundary.

Connect this service to the shared catalog and persistence implementations only
after their owners confirm the repository interfaces. Do not modify
available_copies in more than one place.
"""

from datetime import date

from .rules import (
    calculate_due_date,
    ensure_can_borrow,
    ensure_can_cancel,
    ensure_can_reserve,
    ensure_can_return,
)


class BookingService:
    """Coordinates booking rules; repository integration is intentionally injected later."""

    def validate_reservation(self, active_booking_count: int, available_copies: int) -> None:
        ensure_can_reserve(active_booking_count, available_copies)

    def borrow_due_date(self, status: str, borrowed_on: date) -> date:
        ensure_can_borrow(status)
        return calculate_due_date(borrowed_on)

    def validate_cancellation(self, status: str) -> None:
        ensure_can_cancel(status)

    def validate_return(self, status: str) -> None:
        ensure_can_return(status)
