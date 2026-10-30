"""Pure business rules. Persistence and catalog updates belong to integrations."""

from datetime import date, timedelta

MAX_ACTIVE_BOOKINGS = 5
LOAN_DAYS = 14
ACTIVE_STATUSES = {"reserved", "borrowed"}


class BookingRuleError(ValueError):
    """Raised when a booking action violates a business rule."""


def ensure_can_reserve(active_booking_count: int, available_copies: int) -> None:
    if active_booking_count >= MAX_ACTIVE_BOOKINGS:
        raise BookingRuleError("A member may have at most 5 active bookings.")
    if available_copies < 1:
        raise BookingRuleError("No copies are currently available.")


def ensure_can_borrow(status: str) -> None:
    if status != "reserved":
        raise BookingRuleError("Only a reserved booking can be borrowed.")


def calculate_due_date(borrowed_on: date) -> date:
    return borrowed_on + timedelta(days=LOAN_DAYS)


def ensure_can_cancel(status: str) -> None:
    if status != "reserved":
        raise BookingRuleError("Only a reserved booking can be cancelled.")


def ensure_can_return(status: str) -> None:
    if status != "borrowed":
        raise BookingRuleError("Only a borrowed booking can be returned.")
