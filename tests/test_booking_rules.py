from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from src.bookings.models import Booking, BookingStatus
from src.bookings.routes import router as bookings_router
from src.bookings.routes import set_booking_service
from src.bookings.rules import (
    BookingRuleError,
    BookRemovedError,
    MaxActiveBookingsLimitError,
    NoCopiesAvailableError,
    calculate_due_date,
    ensure_can_borrow,
    ensure_can_cancel,
    ensure_can_reserve,
    ensure_can_return,
)
from src.bookings.service import BookingService
from src.users.auth import STUB_MEMBER_TOKEN


def test_reservation_allowed_with_copy_and_capacity():
    ensure_can_reserve(active_booking_count=4, available_copies=1)


def test_sixth_active_booking_is_rejected():
    with pytest.raises(MaxActiveBookingsLimitError):
        ensure_can_reserve(active_booking_count=5, available_copies=1)


def test_reservation_rejected_when_no_copy_available():
    with pytest.raises(NoCopiesAvailableError):
        ensure_can_reserve(active_booking_count=0, available_copies=0)


def test_reservation_rejected_when_book_is_removed():
    with pytest.raises(BookRemovedError):
        ensure_can_reserve(active_booking_count=0, available_copies=2, is_removed=True)


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
    active_res = Booking(
        id=1,
        user_id=10,
        book_id=20,
        status=BookingStatus.RESERVED,
        created_at=date(2026, 10, 30),
    )
    assert active_res.is_active is True
    assert active_res.is_overdue is False

    inactive_cancelled = Booking(
        id=2,
        user_id=10,
        book_id=20,
        status=BookingStatus.CANCELLED,
        created_at=date(2026, 10, 30),
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
    service = BookingService()
    service.validate_reservation(active_booking_count=2, available_copies=3)
    due = service.borrow_due_date("reserved", date(2026, 10, 30))
    assert due == date(2026, 11, 13)
    service.validate_cancellation("reserved")
    service.validate_return("borrowed")


# =========================================================================
# Acceptance Criteria Tests for Ticket DLBS-46 / FR-B1, FR-B9, NFR-B1
# =========================================================================


def test_fr_b1_reserve_drops_available_copies_by_one():
    """FR-B1: Booking created as reserved and available copies drop by one."""
    service = BookingService()
    service.seed_book(book_id=101, title="Clean Code", available_copies=3)

    booking = service.reserve_book(user_id=1, book_id=101)

    assert booking.id is not None
    assert booking.status == BookingStatus.RESERVED
    assert booking.book_id == 101
    assert booking.user_id == 1

    book = service.get_book(101)
    assert book is not None
    assert book["available_copies"] == 2  # dropped by 1


def test_fr_b1_reserve_removed_book_is_rejected():
    """FR-B1: A removed book is rejected."""
    service = BookingService()
    service.seed_book(book_id=102, title="Deprecated Edition", available_copies=5, is_removed=True)

    with pytest.raises(BookRemovedError, match="is removed"):
        service.reserve_book(user_id=1, book_id=102)

    # copies unchanged
    book = service.get_book(102)
    assert book is not None
    assert book["available_copies"] == 5


def test_fr_b9_reserve_zero_available_copies_returns_conflict_and_changes_nothing():
    """FR-B9: Reserving a book with 0 available copies returns error/conflict and changes nothing."""
    service = BookingService()
    service.seed_book(book_id=103, title="Popular Novel", available_copies=0)

    with pytest.raises(NoCopiesAvailableError, match="No copies"):
        service.reserve_book(user_id=1, book_id=103)

    book = service.get_book(103)
    assert book is not None
    assert book["available_copies"] == 0

    user_bookings = service.get_user_bookings(1)
    assert len(user_bookings) == 0


def test_nfr_b1_concurrent_reservations_single_copy():
    """NFR-B1: In a concurrent test exactly one reservation succeeds and available copies never go below 0."""
    service = BookingService()
    # Exactly one copy available
    service.seed_book(book_id=104, title="Rare Manuscript", available_copies=1)

    num_threads = 10
    success_bookings = []
    conflict_errors = []

    def attempt_reservation(uid: int):
        try:
            b = service.reserve_book(user_id=uid, book_id=104)
            success_bookings.append(b)
        except NoCopiesAvailableError as err:
            conflict_errors.append(err)

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(attempt_reservation, i + 1) for i in range(num_threads)]
        for f in futures:
            f.result()

    # Exactly one reservation succeeded
    assert len(success_bookings) == 1
    # Exactly 9 failed with NoCopiesAvailableError
    assert len(conflict_errors) == num_threads - 1

    # Available copies never went below 0; exactly 0 now
    book = service.get_book(104)
    assert book is not None
    assert book["available_copies"] == 0


def test_borrow_return_and_cancel_lifecycle_with_inventory():
    """Full lifecycle: reserve -> borrow -> return restores copy, and cancel restores copy."""
    service = BookingService()
    service.seed_book(book_id=201, title="Refactoring", available_copies=2)

    # 1. Reserve first copy
    b1 = service.reserve_book(user_id=1, book_id=201)
    assert service.get_book(201)["available_copies"] == 1

    # 2. Borrow first copy
    b1_borrowed = service.borrow_book(booking_id=b1.id, user_id=1)
    assert b1_borrowed.status == BookingStatus.BORROWED
    assert b1_borrowed.due_date == calculate_due_date(date.today())

    # 3. Return first copy
    b1_returned = service.return_book(booking_id=b1.id, user_id=1)
    assert b1_returned.status == BookingStatus.RETURNED
    assert service.get_book(201)["available_copies"] == 2  # restored

    # 4. Repeated return rejected (BR-08 / TC-08)
    with pytest.raises(BookingRuleError):
        service.return_book(booking_id=b1.id, user_id=1)
    assert service.get_book(201)["available_copies"] == 2  # stock not increased again

    # 5. Reserve and Cancel restores copy
    b2 = service.reserve_book(user_id=2, book_id=201)
    assert service.get_book(201)["available_copies"] == 1
    b2_cancelled = service.cancel_booking(booking_id=b2.id, user_id=2)
    assert b2_cancelled.status == BookingStatus.CANCELLED
    assert service.get_book(201)["available_copies"] == 2  # restored


def test_max_five_active_bookings_limit():
    """TC-04 / BR-03: Member attempts sixth active booking -> rejected."""
    service = BookingService()
    for book_id in range(1, 10):
        service.seed_book(book_id=book_id, title=f"Book {book_id}", available_copies=5)

    # Reserve 5 books
    for book_id in range(1, 6):
        service.reserve_book(user_id=1, book_id=book_id)

    # Attempting 6th reservation is rejected
    with pytest.raises(MaxActiveBookingsLimitError):
        service.reserve_book(user_id=1, book_id=6)


# =========================================================================
# API Integration Tests with TestClient (TC-01, TC-02, TC-03, TC-05, etc.)
# =========================================================================


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(bookings_router)
    service = BookingService()
    set_booking_service(service)
    client = TestClient(app)
    return client, service


def test_api_reserve_unauthenticated_returns_401(api_client):
    """TC-03: Reserve without auth header returns 401."""
    client, _ = api_client
    response = client.post("/api/bookings", json={"book_id": 1})
    assert response.status_code == 401


def test_api_reserve_success_returns_201_and_drops_copy(api_client):
    """TC-01 / FR-B1: Reserve with available copy returns 201."""
    client, service = api_client
    service.seed_book(book_id=10, title="TDD by Example", available_copies=2)

    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}
    response = client.post("/api/bookings", json={"book_id": 10}, headers=headers)

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "reserved"
    assert data["book_id"] == 10
    assert data["is_active"] is True
    assert service.get_book(10)["available_copies"] == 1


def test_api_reserve_zero_copies_returns_409(api_client):
    """TC-02 / FR-B9: Reserve with 0 copies returns 409 and changes nothing."""
    client, service = api_client
    service.seed_book(book_id=11, title="Zero Copies Book", available_copies=0)

    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}
    response = client.post("/api/bookings", json={"book_id": 11}, headers=headers)

    assert response.status_code == 409
    assert "No copies" in response.json()["detail"]
    assert service.get_book(11)["available_copies"] == 0


def test_api_reserve_removed_book_returns_409(api_client):
    """FR-B1: Reserve removed book returns 409."""
    client, service = api_client
    service.seed_book(book_id=12, title="Removed Book", available_copies=5, is_removed=True)

    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}
    response = client.post("/api/bookings", json={"book_id": 12}, headers=headers)

    assert response.status_code == 409
    assert "removed" in response.json()["detail"].lower()


def test_api_reserve_unknown_book_returns_404(api_client):
    """TC-15: Reserve non-existent book returns 404."""
    client, _ = api_client
    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}
    response = client.post("/api/bookings", json={"book_id": 9999}, headers=headers)

    assert response.status_code == 404


def test_api_borrow_return_cancel_and_get_me(api_client):
    """Full API endpoints test: reserve -> borrow -> return and cancel and GET /api/bookings/me."""
    client, service = api_client
    service.seed_book(book_id=20, title="Design Patterns", available_copies=2)
    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}

    # 1. Reserve
    res = client.post("/api/bookings", json={"book_id": 20}, headers=headers)
    assert res.status_code == 201
    booking_id = res.json()["id"]

    # 2. Borrow
    borrow_res = client.post(f"/api/bookings/{booking_id}/borrow", headers=headers)
    assert borrow_res.status_code == 200
    assert borrow_res.json()["status"] == "borrowed"
    assert borrow_res.json()["due_date"] is not None

    # 3. Return
    return_res = client.post(f"/api/bookings/{booking_id}/return", headers=headers)
    assert return_res.status_code == 200
    assert return_res.json()["status"] == "returned"
    assert return_res.json()["returned_at"] is not None

    # 4. GET /api/bookings/me
    me_res = client.get("/api/bookings/me", headers=headers)
    assert me_res.status_code == 200
    items = me_res.json()["items"]
    assert len(items) >= 1
    assert items[0]["id"] == booking_id

    # 5. Cancel endpoint with a new reservation
    res2 = client.post("/api/bookings", json={"book_id": 20}, headers=headers)
    assert res2.status_code == 201
    booking_id2 = res2.json()["id"]

    cancel_res = client.delete(f"/api/bookings/{booking_id2}", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"
