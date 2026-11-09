"""Acceptance tests for Jira Card DLBS-51.

Requirements:
- FR-B6: A borrowed booking read after its due date shows overdue = true.
- FR-B7: GET /api/bookings/me lists only member bookings with status, dates and overdue.
- FR-B10: Reservation read more than 2 days after creation shows expired and copy restored.
"""

from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from src.bookings.models import Booking, BookingRow, BookingStatus
from src.bookings.routes import router as bookings_router
from src.bookings.routes import set_booking_service
from src.bookings.rules import (
    BookingRuleError,
    calculate_due_date,
    calculate_hold_expiry,
)
from src.bookings.service import BookingService
from src.users.auth import CurrentUser, create_access_token


@pytest.fixture
def test_service():
    """Isolated in-memory BookingService instance."""
    return BookingService(":memory:")


@pytest.fixture
def api_client(test_service):
    """FastAPI TestClient wired to isolated BookingService."""
    app = FastAPI()
    app.include_router(bookings_router)
    set_booking_service(test_service)
    client = TestClient(app)
    return client, test_service


def _auth_headers(
    user_id: int = 1, name: str = "Test User", role: str = "member"
) -> dict[str, str]:
    token = create_access_token(CurrentUser(user_id, name, f"user{user_id}@example.com", role))
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# FR-B6: Due Dates & Overdue Flag Acceptance Criteria
# =========================================================================


def test_tc_b20_fr_b2_due_date_calculation():
    """TC-B20 / DLBS-51: Due date strictly computed as 14 calendar days ahead."""
    borrow_date = date(2026, 10, 30)
    expected_due = date(2026, 11, 13)
    assert calculate_due_date(borrow_date) == expected_due


def test_tc_b21_fr_b6_overdue_flag_true_when_past_due(test_service):
    """TC-B21 / FR-B6: A borrowed booking read after its due date shows overdue = true."""
    # Borrowed book with due_date in the past
    past_due_date = date.today() - timedelta(days=2)
    booking = Booking(
        id=1,
        user_id=1,
        book_id=10,
        status=BookingStatus.BORROWED,
        created_at=date.today() - timedelta(days=16),
        borrowed_at=date.today() - timedelta(days=16),
        due_date=past_due_date,
    )

    assert booking.overdue is True
    assert booking.is_overdue is True
    assert booking.is_active is True


def test_fr_b6_overdue_flag_false_when_within_due_date():
    """FR-B6: A borrowed booking read on or before its due date shows overdue = false."""
    future_due_date = date.today() + timedelta(days=5)
    booking = Booking(
        id=2,
        user_id=1,
        book_id=10,
        status=BookingStatus.BORROWED,
        due_date=future_due_date,
    )

    assert booking.overdue is False
    assert booking.is_overdue is False

    today_due = Booking(
        id=3,
        user_id=1,
        book_id=10,
        status=BookingStatus.BORROWED,
        due_date=date.today(),
    )
    assert today_due.overdue is False
    assert today_due.is_overdue is False


def test_fr_b6_non_borrowed_bookings_never_overdue():
    """FR-B6: Reserved, returned, cancelled, and expired bookings are never overdue."""
    past_date = date.today() - timedelta(days=10)

    reserved = Booking(
        id=1, user_id=1, book_id=10, status=BookingStatus.RESERVED, due_date=past_date
    )
    assert reserved.overdue is False

    returned = Booking(
        id=2, user_id=1, book_id=10, status=BookingStatus.RETURNED, due_date=past_date
    )
    assert returned.overdue is False

    cancelled = Booking(
        id=3, user_id=1, book_id=10, status=BookingStatus.CANCELLED, due_date=past_date
    )
    assert cancelled.overdue is False

    expired = Booking(
        id=4, user_id=1, book_id=10, status=BookingStatus.EXPIRED, due_date=past_date
    )
    assert expired.overdue is False


def test_fr_b6_is_overdue_as_of_arbitrary_reference_date():
    """FR-B6: Booking.is_overdue_as_of supports simulation against any reference date."""
    booking = Booking(
        id=5,
        user_id=1,
        book_id=10,
        status=BookingStatus.BORROWED,
        due_date=date(2026, 11, 10),
    )

    assert booking.is_overdue_as_of(date(2026, 11, 9)) is False
    assert booking.is_overdue_as_of(date(2026, 11, 10)) is False
    assert booking.is_overdue_as_of(date(2026, 11, 11)) is True


def test_fr_b6_sqlalchemy_model_overdue_properties():
    """FR-B6: BookingRow exposes is_overdue and overdue properties matching domain model."""
    row = BookingRow()
    row.status = "borrowed"
    row.due_date = date.today() - timedelta(days=1)
    assert row.overdue is True
    assert row.is_overdue is True

    row.due_date = date.today() + timedelta(days=1)
    assert row.overdue is False
    assert row.is_overdue is False

    row.status = "returned"
    row.due_date = date.today() - timedelta(days=5)
    assert row.overdue is False


# =========================================================================
# FR-B7: GET /api/bookings/me Acceptance Criteria
# =========================================================================


def test_tc_b22_fr_b7_get_my_bookings_lists_only_member_bookings(api_client):
    """TC-B22 / FR-B7: GET /api/bookings/me lists ONLY the authenticated member's bookings."""
    client, service = api_client
    service.seed_book(book_id=101, title="Book 101", available_copies=5)
    service.seed_book(book_id=102, title="Book 102", available_copies=5)
    service.seed_book(book_id=103, title="Book 103", available_copies=5)

    headers_user1 = _auth_headers(user_id=1, name="Alice")
    headers_user2 = _auth_headers(user_id=2, name="Bob")

    # User 1 makes 2 bookings
    client.post("/api/bookings", json={"book_id": 101}, headers=headers_user1)
    client.post("/api/bookings", json={"book_id": 102}, headers=headers_user1)

    # User 2 makes 1 booking
    client.post("/api/bookings", json={"book_id": 103}, headers=headers_user2)

    # User 1 calls GET /api/bookings/me
    res1 = client.get("/api/bookings/me", headers=headers_user1)
    assert res1.status_code == 200
    items1 = res1.json()["items"]
    assert len(items1) == 2
    for item in items1:
        assert item["user_id"] == 1
        assert item["book_id"] in [101, 102]

    # User 2 calls GET /api/bookings/me
    res2 = client.get("/api/bookings/me", headers=headers_user2)
    assert res2.status_code == 200
    items2 = res2.json()["items"]
    assert len(items2) == 1
    assert items2[0]["user_id"] == 2
    assert items2[0]["book_id"] == 103


def test_fr_b7_get_my_bookings_contains_status_dates_and_overdue_flag(api_client):
    """FR-B7: Response payload includes status, formatted dates, and overdue flag."""
    client, service = api_client
    service.seed_book(book_id=201, title="Refactoring", available_copies=2)

    headers = _auth_headers(user_id=42, name="Ada")

    # Reserve book
    res_reserve = client.post("/api/bookings", json={"book_id": 201}, headers=headers)
    assert res_reserve.status_code == 201
    booking_id = res_reserve.json()["id"]

    # Borrow book
    res_borrow = client.post(f"/api/bookings/{booking_id}/borrow", headers=headers)
    assert res_borrow.status_code == 200

    # Call GET /api/bookings/me
    res = client.get("/api/bookings/me", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert len(data["items"]) == 1

    item = data["items"][0]
    assert item["id"] == booking_id
    assert item["user_id"] == 42
    assert item["book_id"] == 201
    assert item["status"] == "borrowed"
    assert item["created_at"] == date.today().isoformat()
    assert item["borrowed_at"] == date.today().isoformat()
    assert item["due_date"] == (date.today() + timedelta(days=14)).isoformat()
    assert item["returned_at"] is None
    assert item["is_active"] is True
    assert item["is_overdue"] is False
    assert item["overdue"] is False


def test_fr_b7_get_my_bookings_sorted_newest_first(api_client):
    """FR-B7: Bookings are returned newest first (id descending)."""
    client, service = api_client
    for bid in range(301, 305):
        service.seed_book(book_id=bid, title=f"Volume {bid}", available_copies=2)

    headers = _auth_headers(user_id=50)
    created_ids = []
    for bid in range(301, 305):
        resp = client.post("/api/bookings", json={"book_id": bid}, headers=headers)
        created_ids.append(resp.json()["id"])

    res = client.get("/api/bookings/me", headers=headers)
    assert res.status_code == 200
    items = res.json()["items"]
    fetched_ids = [item["id"] for item in items]
    assert fetched_ids == list(reversed(created_ids))


def test_fr_b7_get_my_bookings_unauthenticated_returns_401(api_client):
    """FR-B7: Calling /api/bookings/me without authorization token returns 401."""
    client, _ = api_client
    res = client.get("/api/bookings/me")
    assert res.status_code == 401


# =========================================================================
# FR-B10: Hold Expiry After 2 Days Acceptance Criteria
# =========================================================================


def test_tc_b23_fr_b10_hold_expiry_calculation():
    """TC-B23 / FR-B10: Hold duration is strictly 2 calendar days from reservation."""
    res_date = date(2026, 11, 1)
    assert calculate_hold_expiry(res_date) == date(2026, 11, 3)


def test_tc_b23_fr_b10_reservation_read_past_two_days_shows_expired_and_restores_copy(test_service):
    """TC-B23 / FR-B10: A reservation read more than 2 days after it was made shows expired
    and its copy is available again."""
    # Seed 1 copy
    test_service.seed_book(book_id=401, title="Domain Driven Design", available_copies=1)

    # Reserve on 2026-11-01
    booking = test_service.reserve_book(user_id=1, book_id=401, reserved_on=date(2026, 11, 1))
    assert booking.status == BookingStatus.RESERVED
    assert test_service.get_book(401)["available_copies"] == 0

    # Read within hold period (2026-11-02 -> Day 1)
    read_day1 = test_service.get_booking(booking.id, as_of=date(2026, 11, 2))
    assert read_day1.status == BookingStatus.RESERVED
    assert test_service.get_book(401)["available_copies"] == 0

    # Read on last hold day (2026-11-03 -> Day 2)
    read_day2 = test_service.get_booking(booking.id, as_of=date(2026, 11, 3))
    assert read_day2.status == BookingStatus.RESERVED
    assert test_service.get_book(401)["available_copies"] == 0

    # Read past 2 days (2026-11-04 -> Day 3)
    read_day3 = test_service.get_booking(booking.id, as_of=date(2026, 11, 4))
    assert read_day3.status == BookingStatus.EXPIRED
    assert test_service.get_book(401)["available_copies"] == 1

    # Subsequent reads remain expired and do NOT increment copy count again
    read_day4 = test_service.get_booking(booking.id, as_of=date(2026, 11, 5))
    assert read_day4.status == BookingStatus.EXPIRED
    assert test_service.get_book(401)["available_copies"] == 1


def test_fr_b10_get_user_bookings_dynamically_expires_holds_on_read(test_service):
    """FR-B10: get_user_bookings dynamically expires old reservations and restores stock."""
    test_service.seed_book(book_id=501, title="Clean Architecture", available_copies=1)
    test_service.seed_book(book_id=502, title="The Mythical Man-Month", available_copies=1)

    # User reserves book 501 on Nov 1 (expired by Nov 5)
    b1 = test_service.reserve_book(user_id=10, book_id=501, reserved_on=date(2026, 11, 1))
    # User reserves book 502 on Nov 4 (valid on Nov 5)
    b2 = test_service.reserve_book(user_id=10, book_id=502, reserved_on=date(2026, 11, 4))

    assert test_service.get_book(501)["available_copies"] == 0
    assert test_service.get_book(502)["available_copies"] == 0

    # Read user bookings on Nov 5
    user_bookings = test_service.get_user_bookings(user_id=10, as_of=date(2026, 11, 5))
    assert len(user_bookings) == 2

    # Map by id
    by_id = {b.id: b for b in user_bookings}
    assert by_id[b1.id].status == BookingStatus.EXPIRED
    assert by_id[b2.id].status == BookingStatus.RESERVED

    # Book 501 stock restored; Book 502 stock still held
    assert test_service.get_book(501)["available_copies"] == 1
    assert test_service.get_book(502)["available_copies"] == 0


def test_fr_b10_borrow_attempt_after_hold_expiry_fails(test_service):
    """FR-B10: Attempting to borrow an expired reservation fails and restores copy."""
    test_service.seed_book(book_id=601, title="Legacy Code", available_copies=1)

    # Reserved Nov 1 (expires Nov 3)
    b = test_service.reserve_book(user_id=5, book_id=601, reserved_on=date(2026, 11, 1))
    assert test_service.get_book(601)["available_copies"] == 0

    # Borrow on Nov 5 (past 2-day hold)
    with pytest.raises(BookingRuleError, match="expired"):
        test_service.borrow_book(booking_id=b.id, user_id=5, borrowed_on=date(2026, 11, 5))

    # Copy is available again and booking status is expired
    assert test_service.get_book(601)["available_copies"] == 1
    assert test_service.get_booking(b.id).status == BookingStatus.EXPIRED


def test_fr_b10_cancel_attempt_after_hold_expiry_fails(test_service):
    """FR-B10: Attempting to cancel an expired reservation fails gracefully."""
    test_service.seed_book(book_id=602, title="Refactoring to Patterns", available_copies=1)

    b = test_service.reserve_book(user_id=5, book_id=602, reserved_on=date(2026, 11, 1))
    assert test_service.get_book(602)["available_copies"] == 0

    with pytest.raises(BookingRuleError, match="expired"):
        test_service.cancel_booking(booking_id=b.id, user_id=5, cancelled_on=date(2026, 11, 5))

    assert test_service.get_book(602)["available_copies"] == 1
    assert test_service.get_booking(b.id).status == BookingStatus.EXPIRED


def test_fr_b10_api_routes_single_booking_and_cross_user_isolation(api_client):
    """FR-B10 / API: GET /api/bookings/{id} validates ownership and dynamic expiry."""
    client, service = api_client
    service.seed_book(book_id=701, title="Architecture Patterns", available_copies=2)

    headers_user1 = _auth_headers(user_id=1, name="User One")
    headers_user2 = _auth_headers(user_id=2, name="User Two")
    headers_admin = _auth_headers(user_id=99, name="Admin", role="admin")

    res = client.post("/api/bookings", json={"book_id": 701}, headers=headers_user1)
    booking_id = res.json()["id"]

    # User 1 can view their booking
    view_res = client.get(f"/api/bookings/{booking_id}", headers=headers_user1)
    assert view_res.status_code == 200
    assert view_res.json()["id"] == booking_id
    assert view_res.json()["status"] == "reserved"

    # User 2 cannot view User 1's booking (404 access denied)
    unauth_res = client.get(f"/api/bookings/{booking_id}", headers=headers_user2)
    assert unauth_res.status_code == 404

    # Admin can view User 1's booking
    admin_res = client.get(f"/api/bookings/{booking_id}", headers=headers_admin)
    assert admin_res.status_code == 200
    assert admin_res.json()["id"] == booking_id

    # Non-existent booking returns 404
    assert client.get("/api/bookings/99999", headers=headers_user1).status_code == 404
