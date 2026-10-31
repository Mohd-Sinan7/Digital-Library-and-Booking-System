"""Pure business rules. Persistence and catalog updates belong to integrations."""

from datetime import date, timedelta

MAX_ACTIVE_BOOKINGS = 5
LOAN_DAYS = 14
ACTIVE_STATUSES = {"reserved", "borrowed"}


class BookingRuleError(ValueError):
    """Raised when a booking action violates a business rule."""


class NoCopiesAvailableError(BookingRuleError):
    """Raised when no copies of a book are available (FR-B9, HTTP 409)."""


class BookRemovedError(BookingRuleError):
    """Raised when attempting to reserve a removed book (FR-B1, HTTP 409)."""


class BookNotFoundError(BookingRuleError):
    """Raised when the requested book is not found in the catalog (HTTP 404)."""


class MaxActiveBookingsLimitError(BookingRuleError):
    """Raised when a member already has 5 active bookings (BR-03, HTTP 409)."""


def ensure_can_reserve(
    active_booking_count: int,
    available_copies: int,
    is_removed: bool = False,
) -> None:
    """Validate that a reservation may proceed according to domain rules.

    - FR-B1: Removed book is rejected.
    - FR-B9: Reserving with 0 available copies returns error / conflict.
    - BR-03: Member cannot exceed MAX_ACTIVE_BOOKINGS (5).
    """
    if is_removed:
        raise BookRemovedError("Cannot reserve a removed book.")
    if available_copies < 1:
        raise NoCopiesAvailableError("No copies are currently available.")
    if active_booking_count >= MAX_ACTIVE_BOOKINGS:
        raise MaxActiveBookingsLimitError("A member may have at most 5 active bookings.")


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
