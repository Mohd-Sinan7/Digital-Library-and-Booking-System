from datetime import date

import pytest

from src.bookings.rules import (
    BookingRuleError,
    calculate_due_date,
    ensure_can_borrow,
    ensure_can_cancel,
    ensure_can_reserve,
    ensure_can_return,
)


def test_reservation_allowed_with_copy_and_capacity():
    ensure_can_reserve(active_booking_count=4, available_copies=1)


def test_sixth_active_booking_is_rejected():
    with pytest.raises(BookingRuleError):
        ensure_can_reserve(active_booking_count=5, available_copies=1)


def test_reservation_rejected_when_no_copy_available():
    with pytest.raises(BookingRuleError):
        ensure_can_reserve(active_booking_count=0, available_copies=0)


def test_only_reserved_booking_can_be_borrowed():
    ensure_can_borrow("reserved")
    with pytest.raises(BookingRuleError):
        ensure_can_borrow("cancelled")


def test_due_date_is_fourteen_days_after_borrowing():
    assert calculate_due_date(date(2026, 10, 30)) == date(2026, 11, 13)


def test_only_reserved_booking_can_be_cancelled():
    ensure_can_cancel("reserved")
    with pytest.raises(BookingRuleError):
        ensure_can_cancel("borrowed")


def test_only_borrowed_booking_can_be_returned():
    ensure_can_return("borrowed")
    with pytest.raises(BookingRuleError):
        ensure_can_return("returned")


def test_booking_model_active_and_overdue_flags():
    from src.bookings.models import Booking, BookingStatus

    active_res = Booking(
        id=1, user_id=10, book_id=20, status=BookingStatus.RESERVED, created_at=date(2026, 10, 30)
    )
    assert active_res.is_active is True
    assert active_res.is_overdue is False

    inactive_cancelled = Booking(
        id=2, user_id=10, book_id=20, status=BookingStatus.CANCELLED, created_at=date(2026, 10, 30)
    )
    assert inactive_cancelled.is_active is False
    assert inactive_cancelled.is_overdue is False

    overdue_loan = Booking(
        id=3,
        user_id=10,
        book_id=20,
        status=BookingStatus.BORROWED,
        created_at=date(2026, 10, 1),
        due_date=date(2026, 10, 15),
    )
    assert overdue_loan.is_active is True
    assert overdue_loan.is_overdue is True


def test_booking_service_delegation():
    from src.bookings.service import BookingService

    service = BookingService()
    service.validate_reservation(active_booking_count=2, available_copies=3)
    due = service.borrow_due_date("reserved", date(2026, 10, 30))
    assert due == date(2026, 11, 13)
    service.validate_cancellation("reserved")
    service.validate_return("borrowed")

