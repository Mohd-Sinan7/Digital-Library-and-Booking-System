"""Pure business rules for bookings and state transitions (DLBS-45).

State rules (DLBS-45 / SRS FR-B1 through FR-B10):
- reserved to borrowed
- borrowed to returned
- reserved to cancelled
- reserved to expired (after 2 days)
Any other transition is rejected.
"""

from datetime import date, timedelta

MAX_ACTIVE_BOOKINGS = 5
LOAN_DAYS = 14
HOLD_DAYS = 2  # 2 days reservation hold expiry (FR-B10)
ACTIVE_STATUSES = {"reserved", "borrowed"}

VALID_TRANSITIONS: dict[str, set[str]] = {
    "reserved": {"borrowed", "cancelled", "expired"},
    "borrowed": {"returned"},
    "returned": set(),
    "cancelled": set(),
    "expired": set(),
}


class BookingRuleError(ValueError):
    """Raised when a booking action violates a business rule."""


class InvalidStateTransitionError(BookingRuleError):
    """Raised when an invalid booking state transition is attempted (DLBS-45)."""


class NoCopiesAvailableError(BookingRuleError):
    """Raised when no copies of a book are available (FR-B9, HTTP 409)."""


class BookRemovedError(BookingRuleError):
    """Raised when attempting to reserve a removed book (FR-B1, HTTP 409)."""


class BookNotFoundError(BookingRuleError):
    """Raised when the requested book is not found in the catalog (HTTP 404)."""


class MaxActiveBookingsLimitError(BookingRuleError):
    """Raised when a member already has 5 active bookings (BR-03, HTTP 409)."""


def validate_status_transition(current_status: str, new_status: str) -> None:
    """Validate state transition according to DLBS-45 state rules.

    Allowed transitions:
    - reserved -> borrowed
    - borrowed -> returned
    - reserved -> cancelled
    - reserved -> expired (after 2 days)

    Any other transition is rejected.
    """
    allowed = VALID_TRANSITIONS.get(str(current_status))
    if allowed is None or str(new_status) not in allowed:
        raise InvalidStateTransitionError(
            f"Invalid state transition: cannot transition booking from '{current_status}' to "
            f"'{new_status}'."
        )


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
    """Enforce valid transition into borrowed (only from reserved)."""
    validate_status_transition(status, "borrowed")


def calculate_due_date(borrowed_on: date) -> date:
    """Borrowing sets the due date to 14 calendar days after borrowing (FR-B2)."""
    return borrowed_on + timedelta(days=LOAN_DAYS)


def calculate_hold_expiry(reserved_on: date) -> date:
    """A reservation not borrowed within 2 days expires (FR-B10)."""
    return reserved_on + timedelta(days=HOLD_DAYS)


def ensure_can_cancel(status: str) -> None:
    """Enforce valid transition into cancelled (only from reserved)."""
    validate_status_transition(status, "cancelled")


def ensure_can_return(status: str) -> None:
    """Enforce valid transition into returned (only from borrowed)."""
    validate_status_transition(status, "returned")


def ensure_can_expire(status: str) -> None:
    """Enforce valid transition into expired (only from reserved)."""
    validate_status_transition(status, "expired")
