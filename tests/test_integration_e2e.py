"""Cross-module smoke and end-to-end integration tests (DLBS-55).

Exercises the complete integrated application (src.main.create_app) over a
single shared SQLAlchemy database across all modules:
Users/Auth -> Book Catalog -> Booking & Borrowing -> Reading -> Recommender.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import db as app_db
from src.bookings.routes import set_booking_service
from src.bookings.rules import NoCopiesAvailableError
from src.bookings.session_service import SessionBookingService
from src.catalog import routes as catalog_routes
from src.catalog import service as catalog_service
from src.main import create_app
from src.recommender import routes as recommender_routes
from src.users import reading as users_reading
from src.users import routes as users_routes


@pytest.fixture
def integrated_client(monkeypatch):
    """Create a FastAPI TestClient backed by an isolated shared in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine)

    for module in (
        app_db,
        users_routes,
        users_reading,
        catalog_routes,
        catalog_service,
        recommender_routes,
    ):
        monkeypatch.setattr(module, "SessionLocal", TestingSessionLocal)

    monkeypatch.setattr(app_db, "engine", engine)
    monkeypatch.setattr(
        app_db,
        "create_tables",
        lambda bind=None: app_db.Base.metadata.create_all(engine),
    )
    monkeypatch.setenv("ADMIN_EMAIL", "admin@dlbs.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "AdminPass123")

    # Reset booking route service override so routes use SessionBookingService against shared DB.
    set_booking_service(None)
    app_db.create_tables(engine)

    app = create_app()
    try:
        with TestClient(app) as client:
            yield client, TestingSessionLocal
    finally:
        set_booking_service(None)
        engine.dispose()


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _register_and_login(
    client: TestClient, name: str, email: str, password: str = "MemberPass123"
) -> tuple[int, dict[str, str]]:
    reg = client.post(
        "/api/auth/register",
        json={"name": name, "email": email, "password": password},
    )
    assert reg.status_code == 201, reg.text
    user_id = reg.json()["id"]
    return user_id, _login(client, email, password)


def _isbn(code: int) -> str:
    """Build a valid 13-digit ISBN with a proper EAN-13 check digit."""
    prefix = f"97800000{code:04d}"
    total = sum(int(ch) * (1 if idx % 2 == 0 else 3) for idx, ch in enumerate(prefix))
    check = (10 - (total % 10)) % 10
    return f"{prefix}{check}"


def _create_sample_book(
    client: TestClient,
    admin_headers: dict[str, str],
    *,
    title: str,
    author: str = "Ada Lovelace",
    isbn: str,
    genre: str = "Science Fiction",
    page_count: int = 320,
    total_copies: int = 2,
) -> dict:
    res = client.post(
        "/api/books",
        headers=admin_headers,
        json={
            "title": title,
            "author": author,
            "isbn": isbn,
            "genre": genre,
            "description": f"{title} in {genre}",
            "year": 2024,
            "page_count": page_count,
            "total_copies": total_copies,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_smoke_test_login_search_and_reserve(integrated_client):
    """DLBS-55 Sprint 2 Smoke Test: health -> login -> search catalog -> reserve copy."""
    client, _ = integrated_client

    assert client.get("/health").json() == {"status": "ok"}

    admin_headers = _login(client, "admin@dlbs.test", "AdminPass123")
    book = _create_sample_book(
        client,
        admin_headers,
        title="Dune Messiah",
        author="Frank Herbert",
        isbn="9780000000101",
        total_copies=3,
    )

    _, member_headers = _register_and_login(client, "Smoke Member", "smoke@dlbs.test")

    # Search catalog by title
    search = client.get("/api/books", params={"q": "Dune"})
    assert search.status_code == 200
    assert search.json()["total"] == 1
    found = search.json()["items"][0]
    assert found["id"] == book["id"]
    assert found["available_copies"] == 3

    # Reserve through live booking endpoint (updates shared Catalog DB)
    reserve = client.post(
        "/api/bookings", json={"book_id": found["id"]}, headers=member_headers
    )
    assert reserve.status_code == 201
    assert reserve.json()["status"] == "reserved"

    # Catalog availability endpoint immediately reflects decrement
    avail = client.get(f"/api/books/{found['id']}/availability")
    assert avail.status_code == 200
    assert avail.json()["available_copies"] == 2


def test_e2e_full_journey_login_search_reserve_borrow_return_read_recommend(
    integrated_client,
):
    """DLBS-55 Full Journey: login -> search -> reserve -> borrow -> return -> read -> recommend."""
    client, _ = integrated_client
    admin_headers = _login(client, "admin@dlbs.test", "AdminPass123")

    # Seed several books across Science Fiction & Fantasy so TF-IDF recommender can rank matches
    b1 = _create_sample_book(
        client, admin_headers, title="Foundation", isbn=_isbn(201),
        genre="Science Fiction", total_copies=2,
    )
    b2 = _create_sample_book(
        client, admin_headers, title="Hyperion", isbn=_isbn(202),
        genre="Science Fiction", total_copies=2,
    )
    _create_sample_book(
        client, admin_headers, title="Neuromancer", isbn=_isbn(203),
        genre="Science Fiction", total_copies=2,
    )
    _create_sample_book(
        client, admin_headers, title="The Hobbit", isbn=_isbn(204),
        genre="Fantasy", total_copies=2,
    )

    _, member_headers = _register_and_login(client, "E2E Reader", "e2e@dlbs.test")

    # 1. Search catalog
    found = client.get("/api/books", params={"q": "Foundation"}).json()["items"][0]
    assert found["id"] == b1["id"]

    # 2. Reserve book -> available_copies 2 -> 1
    res_resp = client.post("/api/bookings", json={"book_id": b1["id"]}, headers=member_headers)
    assert res_resp.status_code == 201
    booking_id = res_resp.json()["id"]
    assert client.get(f"/api/books/{b1['id']}/availability").json()["available_copies"] == 1

    # 3. Borrow -> due_date = +14 days, available_copies stays 1
    borrow_resp = client.post(f"/api/bookings/{booking_id}/borrow", headers=member_headers)
    assert borrow_resp.status_code == 200
    assert borrow_resp.json()["status"] == "borrowed"
    assert borrow_resp.json()["due_date"] == (date.today() + timedelta(days=14)).isoformat()
    assert client.get(f"/api/books/{b1['id']}/availability").json()["available_copies"] == 1

    # 4. Return -> available_copies 1 -> 2
    ret_resp = client.post(f"/api/bookings/{booking_id}/return", headers=member_headers)
    assert ret_resp.status_code == 200
    assert ret_resp.json()["status"] == "returned"
    assert client.get(f"/api/books/{b1['id']}/availability").json()["available_copies"] == 2

    # 5. Track reading: update status & finish Foundation + Hyperion
    r_prog = client.post(
        "/api/reading/progress",
        json={"book_id": b1["id"], "current_page": 320},
        headers=member_headers,
    )
    assert r_prog.status_code == 200
    assert r_prog.json()["status"] == "finished"

    r_stat2 = client.put(
        "/api/reading/status",
        json={"book_id": b2["id"], "status": "finished"},
        headers=member_headers,
    )
    assert r_stat2.status_code == 200

    stats = client.get("/api/reading/stats", headers=member_headers).json()
    assert stats["books_finished"] == 2

    # 6. Personalized Recommendations: returns un-finished items with reasons
    recs = client.get("/api/recommendations/me", params={"limit": 5}, headers=member_headers)
    assert recs.status_code == 200
    rec_items = recs.json()["items"]
    assert len(rec_items) > 0
    rec_ids = {item["book_id"] for item in rec_items}
    assert b1["id"] not in rec_ids
    assert b2["id"] not in rec_ids
    for item in rec_items:
        assert item["reason"]


def test_e2e_soft_deleted_book_blocks_reserve_but_allows_return(integrated_client):
    """Cross-module invariant: soft-deleted books reject new reservations but allow returns."""
    client, _ = integrated_client
    admin_headers = _login(client, "admin@dlbs.test", "AdminPass123")
    book = _create_sample_book(
        client, admin_headers, title="Retiring Tome", isbn=_isbn(301), total_copies=2
    )
    _, member_headers = _register_and_login(client, "Borrow User", "borrower@dlbs.test")

    # Borrow before admin removes book
    b = client.post("/api/bookings", json={"book_id": book["id"]}, headers=member_headers).json()
    assert client.post(f"/api/bookings/{b['id']}/borrow", headers=member_headers).status_code == 200

    # Admin soft-deletes book
    del_res = client.delete(f"/api/books/{book['id']}", headers=admin_headers)
    assert del_res.status_code == 204

    # New reservation rejected with 409 Conflict
    blocked = client.post("/api/bookings", json={"book_id": book["id"]}, headers=member_headers)
    assert blocked.status_code == 409
    assert "removed" in blocked.json()["detail"].lower()

    # Returning the active loan still succeeds cleanly
    ret = client.post(f"/api/bookings/{b['id']}/return", headers=member_headers)
    assert ret.status_code == 200
    assert ret.json()["status"] == "returned"


def test_e2e_concurrent_last_copy_atomic_with_shared_db(integrated_client):
    """NFR-B1: Concurrent reservations against shared DB allow exactly 1 winner."""
    client, _ = integrated_client
    admin_headers = _login(client, "admin@dlbs.test", "AdminPass123")
    book = _create_sample_book(
        client, admin_headers, title="Last Copy Book", isbn=_isbn(401), total_copies=1
    )

    service = SessionBookingService()
    barrier = threading.Barrier(8)
    successes = []
    conflicts = []

    def try_reserve(uid: int) -> None:
        barrier.wait()
        try:
            res = service.reserve_book(user_id=uid, book_id=book["id"])
            successes.append(res)
        except NoCopiesAvailableError as err:
            conflicts.append(err)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(try_reserve, uid) for uid in range(100, 108)]
        for fut in futures:
            fut.result()

    assert len(successes) == 1
    assert len(conflicts) == 7
    assert client.get(f"/api/books/{book['id']}/availability").json()["available_copies"] == 0


def test_e2e_hold_expiry_and_overdue_flag_with_shared_catalog(integrated_client):
    """FR-B6 & FR-B10: Reading bookings expires stale holds in Catalog & flags overdue loans."""
    client, _ = integrated_client
    admin_headers = _login(client, "admin@dlbs.test", "AdminPass123")
    b_hold = _create_sample_book(
        client, admin_headers, title="Expired Hold Book", isbn=_isbn(501), total_copies=1
    )
    b_overdue = _create_sample_book(
        client, admin_headers, title="Overdue Loan Book", isbn=_isbn(502), total_copies=1
    )
    uid, member_headers = _register_and_login(client, "Time User", "timeuser@dlbs.test")

    svc = SessionBookingService()
    # Reservation made 4 days ago (2-day hold already expired)
    svc.reserve_book(
        user_id=uid, book_id=b_hold["id"], reserved_on=date.today() - timedelta(days=4)
    )
    assert client.get(f"/api/books/{b_hold['id']}/availability").json()["available_copies"] == 0

    # Loan borrowed 20 days ago (14-day due date passed 6 days ago -> overdue)
    loan_res = svc.reserve_book(
        user_id=uid, book_id=b_overdue["id"], reserved_on=date.today() - timedelta(days=20)
    )
    svc.borrow_book(
        booking_id=loan_res.id, user_id=uid, borrowed_on=date.today() - timedelta(days=20)
    )

    # Reading GET /api/bookings/me dynamically expires hold & returns overdue=True for loan
    me = client.get("/api/bookings/me", headers=member_headers)
    assert me.status_code == 200
    by_book = {item["book_id"]: item for item in me.json()["items"]}

    assert by_book[b_hold["id"]]["status"] == "expired"
    assert client.get(f"/api/books/{b_hold['id']}/availability").json()["available_copies"] == 1

    assert by_book[b_overdue["id"]]["status"] == "borrowed"
    assert by_book[b_overdue["id"]]["overdue"] is True
    assert by_book[b_overdue["id"]]["is_overdue"] is True


def test_e2e_cancel_restores_catalog_and_respects_5_booking_limit(integrated_client):
    """FR-B4 & FR-B8: Cancelling 1 of 5 active bookings restores catalog copies & allowance."""
    client, _ = integrated_client
    admin_headers = _login(client, "admin@dlbs.test", "AdminPass123")
    books = [
        _create_sample_book(
            client, admin_headers, title=f"Limit Book {i}",
            isbn=_isbn(600 + i), total_copies=1,
        )
        for i in range(1, 7)
    ]
    _, member_headers = _register_and_login(client, "Limit User", "limit@dlbs.test")

    booking_ids = []
    for bk in books[:5]:
        res = client.post("/api/bookings", json={"book_id": bk["id"]}, headers=member_headers)
        assert res.status_code == 201
        booking_ids.append(res.json()["id"])

    # 6th booking rejected (limit = 5)
    sixth = client.post("/api/bookings", json={"book_id": books[5]["id"]}, headers=member_headers)
    assert sixth.status_code == 409

    # Cancel 1st booking -> catalog copy restored from 0 back to 1
    cancel = client.delete(f"/api/bookings/{booking_ids[0]}", headers=member_headers)
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
    assert client.get(f"/api/books/{books[0]['id']}/availability").json()["available_copies"] == 1

    # 6th book can now be reserved
    ok_sixth = client.post(
        "/api/bookings", json={"book_id": books[5]["id"]}, headers=member_headers
    )
    assert ok_sixth.status_code == 201


def test_e2e_role_and_user_isolation_across_modules(integrated_client):
    """Security & isolation across auth, catalog, bookings, and recommender."""
    client, _ = integrated_client
    admin_headers = _login(client, "admin@dlbs.test", "AdminPass123")
    book = _create_sample_book(
        client, admin_headers, title="Role Check Book", isbn=_isbn(701), total_copies=2
    )

    _, user1_headers = _register_and_login(client, "Member One", "m1@dlbs.test")
    _, user2_headers = _register_and_login(client, "Member Two", "m2@dlbs.test")

    # Member cannot create or delete catalog books (403)
    assert (
        client.post(
            "/api/books",
            headers=user1_headers,
            json={
                "title": "Illegal", "author": "X", "isbn": _isbn(799),
                "genre": "Fiction", "page_count": 100, "total_copies": 1,
            },
        ).status_code
        == 403
    )
    assert client.post("/api/recommendations/refresh", headers=user1_headers).status_code == 403

    # User 1 reserves book; User 2 cannot view or mutate User 1's booking
    b1 = client.post("/api/bookings", json={"book_id": book["id"]}, headers=user1_headers).json()
    assert client.get("/api/bookings/me", headers=user2_headers).json()["items"] == []
    assert client.get(f"/api/bookings/{b1['id']}", headers=user2_headers).status_code == 404
    assert (
        client.post(f"/api/bookings/{b1['id']}/borrow", headers=user2_headers).status_code == 409
    )
    assert client.delete(f"/api/bookings/{b1['id']}", headers=user2_headers).status_code == 409
