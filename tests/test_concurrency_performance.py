"""DLBS-54: Concurrency and Performance Tests for Booking and Borrowing.

Requirements:
- NFR-B1: Booking actions shall be atomic: two users booking the last copy at the same time
  must not both succeed. In a concurrent test, exactly one reservation succeeds and available
  copies never go below 0.
- NFR-B2: Every booking action shall complete in under 1 second. Each of 20 timed reserve,
  borrow, and return calls takes under 1 s.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from src.bookings.models import BookingStatus
from src.bookings.routes import router as bookings_router
from src.bookings.routes import set_booking_service
from src.bookings.rules import NoCopiesAvailableError
from src.bookings.service import BookingService
from src.users.auth import CurrentUser, create_access_token

MEMBER_TOKEN = create_access_token(
    CurrentUser(1, "Perf Test Member", "perftest@example.com", "member")
)


@pytest.fixture
def api_client():
    """Create a fresh FastAPI TestClient and isolated BookingService instance."""
    app = FastAPI()
    app.include_router(bookings_router)
    service = BookingService()
    set_booking_service(service)
    client = TestClient(app)
    return client, service


# ==============================================================================
# NFR-B1: Concurrency and Atomicity Tests
# ==============================================================================


def test_nfr_b1_concurrent_reservations_last_copy_exact_one_succeeds():
    """NFR-B1: Exactly 1 reservation succeeds on the last copy and copies never drop below 0."""
    service = BookingService()
    book_id = 901
    service.seed_book(book_id=book_id, title="High Demand Book", available_copies=1)

    num_threads = 20
    barrier = threading.Barrier(num_threads)
    successful_bookings = []
    conflict_errors = []
    lock = threading.Lock()

    def worker(user_id: int):
        barrier.wait()  # Release all threads at the exact same millisecond
        try:
            booking = service.reserve_book(user_id=user_id, book_id=book_id)
            with lock:
                successful_bookings.append(booking)
        except NoCopiesAvailableError as err:
            with lock:
                conflict_errors.append(err)

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, i + 10) for i in range(num_threads)]
        for f in futures:
            f.result()

    # Acceptance Criteria Check:
    # 1. Exactly one reservation succeeds
    assert len(successful_bookings) == 1, (
        f"Expected exactly 1 successful reservation, got {len(successful_bookings)}"
    )
    assert successful_bookings[0].status == BookingStatus.RESERVED

    # 2. All other concurrent threads fail with NoCopiesAvailableError
    assert len(conflict_errors) == num_threads - 1

    # 3. Available copies never drop below 0; exactly 0 remaining
    book = service.get_book(book_id)
    assert book is not None
    assert book["available_copies"] == 0


def test_nfr_b1_concurrent_reservations_multi_copy_limit():
    """NFR-B1: Under heavy contention, exactly N reservations succeed for N copies."""
    service = BookingService()
    book_id = 902
    initial_copies = 5
    service.seed_book(
        book_id=book_id, title="Limited Edition Book", available_copies=initial_copies
    )

    num_threads = 25
    barrier = threading.Barrier(num_threads)
    successful_bookings = []
    conflict_errors = []
    lock = threading.Lock()

    def worker(user_id: int):
        barrier.wait()
        try:
            booking = service.reserve_book(user_id=user_id, book_id=book_id)
            with lock:
                successful_bookings.append(booking)
        except NoCopiesAvailableError as err:
            with lock:
                conflict_errors.append(err)

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, i + 100) for i in range(num_threads)]
        for f in futures:
            f.result()

    assert len(successful_bookings) == initial_copies
    assert len(conflict_errors) == num_threads - initial_copies
    book = service.get_book(book_id)
    assert book is not None
    assert book["available_copies"] == 0


def test_nfr_b1_concurrent_api_reservations_last_copy(api_client):
    """NFR-B1 via HTTP API: Concurrent POST /api/bookings on last copy yields 1 201 and 409s."""
    client, service = api_client
    book_id = 903
    service.seed_book(book_id=book_id, title="API Contention Book", available_copies=1)

    num_threads = 10
    barrier = threading.Barrier(num_threads)
    responses = []
    lock = threading.Lock()

    def call_api(user_id: int):
        token = create_access_token(
            CurrentUser(user_id, f"Member {user_id}", f"member{user_id}@test.com", "member")
        )
        headers = {"Authorization": f"Bearer {token}"}
        barrier.wait()
        res = client.post("/api/bookings", json={"book_id": book_id}, headers=headers)
        with lock:
            responses.append((res.status_code, res.json()))

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(call_api, i + 1) for i in range(num_threads)]
        for f in futures:
            f.result()

    status_codes = [code for code, _ in responses]
    success_count = status_codes.count(201)
    conflict_count = status_codes.count(409)

    assert success_count == 1, f"Expected 1 HTTP 201 response, got {success_count}"
    assert conflict_count == num_threads - 1, (
        f"Expected {num_threads - 1} HTTP 409 responses, got {conflict_count}"
    )

    book = service.get_book(book_id)
    assert book is not None
    assert book["available_copies"] == 0


# ==============================================================================
# NFR-B2: Performance and Latency Tests (< 1.0s)
# ==============================================================================


def test_nfr_b2_twenty_timed_reserve_borrow_and_return_calls_under_one_second():
    """NFR-B2: Each of 20 timed reserve, borrow, and return calls takes under 1 s."""
    service = BookingService()
    # Seed 20 separate books, one for each lifecycle run
    for book_id in range(1001, 1021):
        service.seed_book(
            book_id=book_id, title=f"Speed Benchmark Book {book_id}", available_copies=1
        )

    reserve_times = []
    borrow_times = []
    return_times = []

    for i in range(20):
        book_id = 1001 + i
        user_id = 50 + i

        # 1. Timed reserve call
        t0 = time.perf_counter()
        booking = service.reserve_book(user_id=user_id, book_id=book_id)
        t_reserve = time.perf_counter() - t0
        reserve_times.append(t_reserve)
        assert t_reserve < 1.0, f"Reserve call #{i+1} took {t_reserve:.4f}s (must be < 1s)"

        # 2. Timed borrow call
        t1 = time.perf_counter()
        borrowed = service.borrow_book(booking_id=booking.id, user_id=user_id)
        t_borrow = time.perf_counter() - t1
        borrow_times.append(t_borrow)
        assert t_borrow < 1.0, f"Borrow call #{i+1} took {t_borrow:.4f}s (must be < 1s)"
        assert borrowed.status == BookingStatus.BORROWED

        # 3. Timed return call
        t2 = time.perf_counter()
        returned = service.return_book(booking_id=booking.id, user_id=user_id)
        t_return = time.perf_counter() - t2
        return_times.append(t_return)
        assert t_return < 1.0, f"Return call #{i+1} took {t_return:.4f}s (must be < 1s)"
        assert returned.status == BookingStatus.RETURNED

    # Acceptance Criteria Verification:
    # 20 calls each for reserve, borrow, and return (60 operations total)
    assert len(reserve_times) == 20
    assert len(borrow_times) == 20
    assert len(return_times) == 20

    max_reserve = max(reserve_times)
    max_borrow = max(borrow_times)
    max_return = max(return_times)

    assert max_reserve < 1.0, f"Max reserve duration {max_reserve:.4f}s exceeds 1.0s"
    assert max_borrow < 1.0, f"Max borrow duration {max_borrow:.4f}s exceeds 1.0s"
    assert max_return < 1.0, f"Max return duration {max_return:.4f}s exceeds 1.0s"

    avg_reserve = sum(reserve_times) / 20
    avg_borrow = sum(borrow_times) / 20
    avg_return = sum(return_times) / 20

    # Ensure typical performance is orders of magnitude below 1s (e.g., < 50ms)
    assert avg_reserve < 0.10, f"Average reserve {avg_reserve:.4f}s is higher than expected"
    assert avg_borrow < 0.10, f"Average borrow {avg_borrow:.4f}s is higher than expected"
    assert avg_return < 0.10, f"Average return {avg_return:.4f}s is higher than expected"


def test_nfr_b2_api_twenty_timed_reserve_borrow_return_calls_under_one_second(api_client):
    """NFR-B2 via HTTP API: 20 timed reserve, borrow, return API calls each take < 1 s."""
    client, service = api_client
    for book_id in range(1101, 1121):
        service.seed_book(book_id=book_id, title=f"API Latency Book {book_id}", available_copies=1)

    api_reserve_times = []
    api_borrow_times = []
    api_return_times = []

    for i in range(20):
        book_id = 1101 + i
        user_id = 100 + i
        token = create_access_token(
            CurrentUser(user_id, f"User {user_id}", f"user{user_id}@test.com", "member")
        )
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Timed POST /api/bookings (reserve)
        t0 = time.perf_counter()
        res_reserve = client.post("/api/bookings", json={"book_id": book_id}, headers=headers)
        t_res = time.perf_counter() - t0
        api_reserve_times.append(t_res)
        assert res_reserve.status_code == 201
        assert t_res < 1.0, f"API reserve #{i+1} took {t_res:.4f}s"
        booking_id = res_reserve.json()["id"]

        # 2. Timed POST /api/bookings/{id}/borrow
        t1 = time.perf_counter()
        res_borrow = client.post(f"/api/bookings/{booking_id}/borrow", headers=headers)
        t_bor = time.perf_counter() - t1
        api_borrow_times.append(t_bor)
        assert res_borrow.status_code == 200
        assert t_bor < 1.0, f"API borrow #{i+1} took {t_bor:.4f}s"

        # 3. Timed POST /api/bookings/{id}/return
        t2 = time.perf_counter()
        res_ret = client.post(f"/api/bookings/{booking_id}/return", headers=headers)
        t_ret = time.perf_counter() - t2
        api_return_times.append(t_ret)
        assert res_ret.status_code == 200
        assert t_ret < 1.0, f"API return #{i+1} took {t_ret:.4f}s"

    assert len(api_reserve_times) == 20
    assert len(api_borrow_times) == 20
    assert len(api_return_times) == 20

    assert max(api_reserve_times) < 1.0
    assert max(api_borrow_times) < 1.0
    assert max(api_return_times) < 1.0


def test_nfr_b2_timed_user_bookings_me_query_under_one_second(api_client):
    """NFR-B2: 20 timed queries to GET /api/bookings/me all respond in under 1 second."""
    client, service = api_client
    # Seed 5 books and create 5 active bookings for user 1
    headers = {"Authorization": f"Bearer {MEMBER_TOKEN}"}
    for book_id in range(1201, 1206):
        service.seed_book(book_id=book_id, title=f"List Book {book_id}", available_copies=1)
        client.post("/api/bookings", json={"book_id": book_id}, headers=headers)

    query_times = []
    for i in range(20):
        t0 = time.perf_counter()
        res = client.get("/api/bookings/me", headers=headers)
        t_query = time.perf_counter() - t0
        query_times.append(t_query)
        assert res.status_code == 200
        data = res.json()
        items = data["items"] if isinstance(data, dict) and "items" in data else data
        assert len(items) == 5
        assert t_query < 1.0, f"GET /api/bookings/me #{i+1} took {t_query:.4f}s"

    assert len(query_times) == 20
    assert max(query_times) < 1.0
    assert sum(query_times) / 20 < 0.10
