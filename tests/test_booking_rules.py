from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from src.bookings.models import Booking, BookingRow, BookingStatus, BookingTable
from src.bookings.routes import router as bookings_router
from src.bookings.routes import set_booking_service
from src.bookings.rules import (
    BookingRuleError,
    BookRemovedError,
    InvalidStateTransitionError,
    MaxActiveBookingsLimitError,
    NoCopiesAvailableError,
    calculate_due_date,
    calculate_hold_expiry,
    ensure_can_borrow,
    ensure_can_cancel,
    ensure_can_expire,
    ensure_can_reserve,
    ensure_can_return,
    validate_status_transition,
)
from src.bookings.service import BookingService
from src.users.auth import CurrentUser, create_access_token

# Real signed token for test user 1 (login issues JWTs since 1 Nov).
STUB_MEMBER_TOKEN = create_access_token(
    CurrentUser(1, "Test Member", "member@example.com", "member")
)


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
    """FR-B9: Reserving with 0 copies returns error/conflict and changes nothing."""
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
    """NFR-B1: In concurrent test 1 succeeds and copies never go below 0."""
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


# =========================================================================
# Acceptance Criteria Tests for Ticket DLBS-49 / FR-B2, FR-B3, FR-B4, FR-B5
# =========================================================================


def test_tc_b01_borrow_sets_status_and_due_date_copies_unchanged():
    """TC-B01 / FR-B2: Status becomes borrowed, due date is 14 days,
    available copies unchanged by borrowing."""
    service = BookingService()
    service.seed_book(book_id=301, title="Domain-Driven Design", available_copies=5)

    # Reserve -> copies drop by 1
    booking = service.reserve_book(user_id=1, book_id=301)
    copies_after_reserve = service.get_book(301)["available_copies"]
    assert copies_after_reserve == 4

    # Borrow -> status is borrowed, due_date is 14 days, copies unchanged
    borrowed = service.borrow_book(booking_id=booking.id, user_id=1)
    assert borrowed.status == BookingStatus.BORROWED
    assert borrowed.due_date == calculate_due_date(date.today())

    copies_after_borrow = service.get_book(301)["available_copies"]
    assert copies_after_borrow == copies_after_reserve  # FR-B2: unchanged


def test_tc_b03_return_restores_copy_and_rejects_non_borrowed():
    """TC-B03 / FR-B3: Status becomes returned and available copies rise by
    one; returning a booking that is not borrowed is rejected."""
    service = BookingService()
    service.seed_book(book_id=302, title="Working Effectively", available_copies=3)

    # Reserve -> borrow -> return
    b1 = service.reserve_book(user_id=1, book_id=302)
    copies_after_reserve = service.get_book(302)["available_copies"]
    assert copies_after_reserve == 2

    service.borrow_book(booking_id=b1.id, user_id=1)
    copies_after_borrow = service.get_book(302)["available_copies"]
    assert copies_after_borrow == 2  # borrow doesn't change copies

    returned = service.return_book(booking_id=b1.id, user_id=1)
    assert returned.status == BookingStatus.RETURNED
    copies_after_return = service.get_book(302)["available_copies"]
    assert copies_after_return == copies_after_reserve + 1  # rises by one

    # Returning an already-returned booking is rejected
    with pytest.raises(BookingRuleError):
        service.return_book(booking_id=b1.id, user_id=1)
    # Copies unchanged after rejected return of already-returned booking
    assert service.get_book(302)["available_copies"] == copies_after_return

    # Returning a reserved-only booking is rejected
    b2 = service.reserve_book(user_id=2, book_id=302)
    copies_after_reserve_b2 = service.get_book(302)["available_copies"]
    with pytest.raises(BookingRuleError):
        service.return_book(booking_id=b2.id, user_id=2)
    # Copies unchanged after rejected return of reserved booking
    assert service.get_book(302)["available_copies"] == copies_after_reserve_b2


def test_tc_b05_cancel_restores_copy_and_rejects_borrowed():
    """TC-B05 / FR-B4: Status becomes cancelled and available copies rise by
    one; a borrowed booking cannot be cancelled."""
    service = BookingService()
    service.seed_book(book_id=303, title="Mythical Man-Month", available_copies=4)

    # Reserve then cancel
    b1 = service.reserve_book(user_id=1, book_id=303)
    copies_after_reserve = service.get_book(303)["available_copies"]
    assert copies_after_reserve == 3

    cancelled = service.cancel_booking(booking_id=b1.id, user_id=1)
    assert cancelled.status == BookingStatus.CANCELLED
    copies_after_cancel = service.get_book(303)["available_copies"]
    assert copies_after_cancel == copies_after_reserve + 1  # rises by one

    # Reserve -> borrow -> try cancel -> rejected
    b2 = service.reserve_book(user_id=2, book_id=303)
    service.borrow_book(booking_id=b2.id, user_id=2)
    copies_before_rejected_cancel = service.get_book(303)["available_copies"]

    with pytest.raises(BookingRuleError):
        service.cancel_booking(booking_id=b2.id, user_id=2)

    # Copies unchanged after rejected cancel
    assert (
        service.get_book(303)["available_copies"]
        == copies_before_rejected_cancel
    )


def test_tc_b08_counts_verified_after_every_action():
    """TC-B08 / FR-B5: Counts checked after every action
    (reserve, borrow, return, reserve again, cancel)."""
    service = BookingService()
    service.seed_book(
        book_id=304, title="The Pragmatic Programmer", available_copies=5
    )

    # 1. Reserve: copies 5 -> 4
    b1 = service.reserve_book(user_id=1, book_id=304)
    assert service.get_book(304)["available_copies"] == 4

    # 2. Borrow: copies stay 4 (FR-B2)
    service.borrow_book(booking_id=b1.id, user_id=1)
    assert service.get_book(304)["available_copies"] == 4

    # 3. Return: copies 4 -> 5 (FR-B3)
    service.return_book(booking_id=b1.id, user_id=1)
    assert service.get_book(304)["available_copies"] == 5

    # 4. Reserve again: copies 5 -> 4
    b2 = service.reserve_book(user_id=2, book_id=304)
    assert service.get_book(304)["available_copies"] == 4

    # 5. Cancel: copies 4 -> 5 (FR-B4)
    service.cancel_booking(booking_id=b2.id, user_id=2)
    assert service.get_book(304)["available_copies"] == 5


# ---- API integration tests for DLBS-49 ----


def test_api_borrow_copies_unchanged(api_client):
    """FR-B2 API: Borrow via API does not change available_copies."""
    client, service = api_client
    service.seed_book(book_id=30, title="API Test Book", available_copies=3)
    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}

    res = client.post("/api/bookings", json={"book_id": 30}, headers=headers)
    assert res.status_code == 201
    booking_id = res.json()["id"]
    assert service.get_book(30)["available_copies"] == 2

    borrow_res = client.post(
        f"/api/bookings/{booking_id}/borrow", headers=headers
    )
    assert borrow_res.status_code == 200
    assert borrow_res.json()["status"] == "borrowed"
    assert borrow_res.json()["due_date"] is not None
    assert service.get_book(30)["available_copies"] == 2  # unchanged


def test_api_return_non_borrowed_returns_409(api_client):
    """FR-B3 API: Returning a reserved booking returns 409."""
    client, service = api_client
    service.seed_book(book_id=31, title="Non-Borrowed", available_copies=3)
    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}

    res = client.post("/api/bookings", json={"book_id": 31}, headers=headers)
    assert res.status_code == 201
    booking_id = res.json()["id"]

    return_res = client.post(
        f"/api/bookings/{booking_id}/return", headers=headers
    )
    assert return_res.status_code == 409


def test_api_cancel_borrowed_returns_409(api_client):
    """FR-B4 API: Cancelling a borrowed booking returns 409."""
    client, service = api_client
    service.seed_book(
        book_id=32, title="Borrowed Cancel", available_copies=3
    )
    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}

    res = client.post("/api/bookings", json={"book_id": 32}, headers=headers)
    assert res.status_code == 201
    booking_id = res.json()["id"]

    client.post(f"/api/bookings/{booking_id}/borrow", headers=headers)

    cancel_res = client.delete(
        f"/api/bookings/{booking_id}", headers=headers
    )
    assert cancel_res.status_code == 409


# =========================================================================
# Acceptance Criteria Tests for Ticket DLBS-45: Bookings table & state rules
# =========================================================================


def test_dlbs_45_bookings_table_schema():
    """DLBS-45: Design the bookings table:
    id, user_id, book_id, status (reserved, borrowed, returned, cancelled, expired),
    reserved_at, expires_at, borrowed_at, due_date, returned_at.
    """
    from sqlalchemy import inspect

    assert BookingRow is BookingTable
    mapper = inspect(BookingRow)
    column_names = {col.key for col in mapper.columns}
    expected_columns = {
        "id",
        "user_id",
        "book_id",
        "status",
        "reserved_at",
        "expires_at",
        "borrowed_at",
        "due_date",
        "returned_at",
    }
    assert expected_columns.issubset(column_names)
    assert mapper.primary_key[0].name == "id"
    assert BookingRow.__tablename__ == "bookings"


def test_dlbs_45_allowed_state_transitions():
    """DLBS-45: State rules before coding:
    - reserved to borrowed
    - borrowed to returned
    - reserved to cancelled
    - reserved to expired (after 2 days)
    """
    # reserved -> borrowed
    validate_status_transition("reserved", "borrowed")
    ensure_can_borrow("reserved")

    # borrowed -> returned
    validate_status_transition("borrowed", "returned")
    ensure_can_return("borrowed")

    # reserved -> cancelled
    validate_status_transition("reserved", "cancelled")
    ensure_can_cancel("reserved")

    # reserved -> expired
    validate_status_transition("reserved", "expired")
    ensure_can_expire("reserved")


def test_dlbs_45_rejected_state_transitions():
    """DLBS-45: Any other transition is rejected."""
    invalid_transitions = [
        ("reserved", "returned"),
        ("borrowed", "reserved"),
        ("borrowed", "cancelled"),
        ("borrowed", "expired"),
        ("returned", "reserved"),
        ("returned", "borrowed"),
        ("returned", "cancelled"),
        ("returned", "expired"),
        ("cancelled", "reserved"),
        ("cancelled", "borrowed"),
        ("cancelled", "returned"),
        ("cancelled", "expired"),
        ("expired", "reserved"),
        ("expired", "borrowed"),
        ("expired", "returned"),
        ("expired", "cancelled"),
        ("unknown_status", "borrowed"),
        ("reserved", "unknown_status"),
    ]
    for current, target in invalid_transitions:
        with pytest.raises(InvalidStateTransitionError):
            validate_status_transition(current, target)


def test_dlbs_45_hold_expiry_calculation():
    """DLBS-45 / FR-B10: reserved to expired after 2 days."""
    reserved_date = date(2026, 11, 2)
    expiry_date = calculate_hold_expiry(reserved_date)
    assert expiry_date == date(2026, 11, 4)


def test_dlbs_45_service_expire_booking_restores_copy():
    """DLBS-45 / FR-B10: Expiring a reservation marks it expired and restores available copy."""
    service = BookingService()
    service.seed_book(book_id=401, title="State Rules in Practice", available_copies=2)

    booking = service.reserve_book(user_id=1, book_id=401)
    assert booking.status == BookingStatus.RESERVED
    assert service.get_book(401)["available_copies"] == 1

    expired = service.expire_booking(booking.id)
    assert expired.status == BookingStatus.EXPIRED
    assert service.get_book(401)["available_copies"] == 2

    # Expiring an already expired booking must be rejected
    with pytest.raises(BookingRuleError):
        service.expire_booking(booking.id)


def test_tc_b02_second_member_reserves_same_book_rejected():
    """TC-B02 / FR-B9: Second member reserves book with 0 copies (rejected)."""
    service = BookingService()
    service.seed_book(book_id=501, title="Single Copy Book", available_copies=1)

    # Member 1 reserves successfully
    b1 = service.reserve_book(user_id=1, book_id=501)
    assert b1.status == BookingStatus.RESERVED
    assert service.get_book(501)["available_copies"] == 0

    # Member 2 attempts to reserve the same book -> rejected with clear message
    with pytest.raises(NoCopiesAvailableError, match="No copies"):
        service.reserve_book(user_id=2, book_id=501)

    assert service.get_book(501)["available_copies"] == 0


def test_tc_b04_member_tries_sixth_active_booking_rejected():
    """TC-B04 / FR-B8: Member tries a sixth active booking -> rejected."""
    service = BookingService()
    for book_id in range(601, 607):
        service.seed_book(book_id=book_id, title=f"Book {book_id}", available_copies=5)

    # Member creates 5 active bookings
    for book_id in range(601, 606):
        service.reserve_book(user_id=10, book_id=book_id)

    # Member tries 6th active booking -> rejected
    with pytest.raises(MaxActiveBookingsLimitError, match="at most 5 active bookings"):
        service.reserve_book(user_id=10, book_id=606)


# =========================================================================
# DLBS-50: Booking Limit (FR-B8) and Remaining Unit Tests (NFR-B3)
# =========================================================================


def test_dlbs_50_api_sixth_active_booking_rejected_with_409(api_client):
    """DLBS-50 / FR-B8: A sixth active reservation or loan is rejected with 409."""
    client, service = api_client
    for book_id in range(701, 707):
        service.seed_book(book_id=book_id, title=f"Book {book_id}", available_copies=5)

    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}

    # Member creates 5 active reservations successfully (201 Created)
    for book_id in range(701, 706):
        res = client.post("/api/bookings", json={"book_id": book_id}, headers=headers)
        assert res.status_code == 201
        assert res.json()["status"] == "reserved"

    # Member attempts 6th active reservation -> rejected with HTTP 409 Conflict
    res_sixth = client.post("/api/bookings", json={"book_id": 706}, headers=headers)
    assert res_sixth.status_code == 409
    assert "at most 5 active bookings" in res_sixth.json()["detail"].lower()


def test_dlbs_50_sixth_active_with_mixed_borrowed_and_reserved_rejected(api_client):
    """DLBS-50 / FR-B8: Sixth booking rejected when holding mixed reserved + borrowed loans."""
    client, service = api_client
    for book_id in range(711, 717):
        service.seed_book(book_id=book_id, title=f"Book {book_id}", available_copies=5)

    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}

    # Reserve 3 books
    b1 = client.post("/api/bookings", json={"book_id": 711}, headers=headers).json()
    b2 = client.post("/api/bookings", json={"book_id": 712}, headers=headers).json()
    client.post("/api/bookings", json={"book_id": 713}, headers=headers)

    # Borrow 2 of them (status becomes borrowed; still active)
    borrow_res1 = client.post(f"/api/bookings/{b1['id']}/borrow", headers=headers)
    assert borrow_res1.status_code == 200
    borrow_res2 = client.post(f"/api/bookings/{b2['id']}/borrow", headers=headers)
    assert borrow_res2.status_code == 200

    # Reserve 2 more books (3 reserved + 2 borrowed = 5 active bookings)
    client.post("/api/bookings", json={"book_id": 714}, headers=headers)
    client.post("/api/bookings", json={"book_id": 715}, headers=headers)

    # 6th booking attempt -> HTTP 409 Conflict
    res_fail = client.post("/api/bookings", json={"book_id": 716}, headers=headers)
    assert res_fail.status_code == 409
    assert "at most 5 active bookings" in res_fail.json()["detail"].lower()

    # Returning one of the borrowed books restores active capacity
    return_res = client.post(f"/api/bookings/{b1['id']}/return", headers=headers)
    assert return_res.status_code == 200

    # Now member holds 4 active bookings, 6th attempt succeeds
    res_retry = client.post("/api/bookings", json={"book_id": 716}, headers=headers)
    assert res_retry.status_code == 201


def test_dlbs_50_cancel_restores_allowance_via_api(api_client):
    """DLBS-50 / FR-B8: Cancelling an active reservation frees up capacity."""
    client, service = api_client
    for book_id in range(721, 727):
        service.seed_book(book_id=book_id, title=f"Book {book_id}", available_copies=5)

    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}

    # Create 5 active reservations
    first_booking = client.post("/api/bookings", json={"book_id": 721}, headers=headers).json()
    for book_id in range(722, 726):
        client.post("/api/bookings", json={"book_id": book_id}, headers=headers)

    # 6th attempt fails
    assert client.post("/api/bookings", json={"book_id": 726}, headers=headers).status_code == 409

    # Cancel one reservation
    cancel_res = client.delete(f"/api/bookings/{first_booking['id']}", headers=headers)
    assert cancel_res.status_code == 200

    # Now reservation succeeds
    success_res = client.post("/api/bookings", json={"book_id": 726}, headers=headers)
    assert success_res.status_code == 201


def test_dlbs_50_api_routes_not_found_handling(api_client):
    """DLBS-50: Verify borrow, return, and cancel return 404 for nonexistent bookings."""
    client, _ = api_client
    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}

    assert client.post("/api/bookings/99999/borrow", headers=headers).status_code == 404
    assert client.post("/api/bookings/99999/return", headers=headers).status_code == 404
    assert client.delete("/api/bookings/99999", headers=headers).status_code == 404


def test_dlbs_50_api_cross_user_mutations_forbidden(api_client):
    """DLBS-50: Verify users cannot borrow, return, or cancel another member's booking."""
    client, service = api_client
    service.seed_book(book_id=731, title="User Isolation Book", available_copies=5)

    user1_headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}
    user2_token = create_access_token(
        CurrentUser(2, "Second Member", "member2@example.com", "member")
    )
    user2_headers = {"Authorization": f"Bearer {user2_token}"}

    # User 1 reserves the book
    b1 = client.post("/api/bookings", json={"book_id": 731}, headers=user1_headers).json()

    # User 2 attempts to borrow User 1's booking -> 409 Conflict
    res_borrow = client.post(f"/api/bookings/{b1['id']}/borrow", headers=user2_headers)
    assert res_borrow.status_code == 409
    assert "another member" in res_borrow.json()["detail"].lower()

    # User 2 attempts to return User 1's booking -> 409 Conflict
    res_return = client.post(f"/api/bookings/{b1['id']}/return", headers=user2_headers)
    assert res_return.status_code == 409

    # User 2 attempts to cancel User 1's booking -> 409 Conflict
    res_cancel = client.delete(f"/api/bookings/{b1['id']}", headers=user2_headers)
    assert res_cancel.status_code == 409
    assert "another member" in res_cancel.json()["detail"].lower()


def test_dlbs_50_models_and_service_edge_cases():
    """DLBS-50: Test edge cases in models and service for full coverage."""
    service = BookingService()

    # get_book with non-existent ID returns None
    assert service.get_book(99999) is None

    # expire_booking with non-existent booking ID raises BookingRuleError
    with pytest.raises(BookingRuleError, match="not found"):
        service.expire_booking(99999)

    # Booking post_init with datetime reserved_at sets created_at date
    dt = datetime(2026, 11, 1, 14, 30)
    b_dt = Booking(
        id=1,
        user_id=1,
        book_id=1,
        status=BookingStatus.RESERVED,
        reserved_at=dt,
        created_at=None,
    )
    assert b_dt.created_at == dt.date()

    # Booking post_init with date reserved_at sets created_at date
    d = date(2026, 11, 2)
    b_d = Booking(
        id=2,
        user_id=1,
        book_id=1,
        status=BookingStatus.RESERVED,
        reserved_at=d,
        created_at=None,
    )
    assert b_d.created_at == d
