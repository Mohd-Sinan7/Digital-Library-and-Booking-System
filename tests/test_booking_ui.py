"""Tests verifying the Booking UI pages, assets, accessibility, and API contract (DLBS-53)."""

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.bookings.routes import router as bookings_router
from src.bookings.routes import set_booking_service
from src.bookings.service import BookingService
from src.main import app
from src.users.auth import CurrentUser, create_access_token

WEB_DIR = Path(__file__).resolve().parents[1] / "src" / "web"

BOOKING_PAGES = {
    "bookings.html": "My Bookings",
    "book.html": "Book Details",
}


@pytest.mark.parametrize("page, heading", BOOKING_PAGES.items())
def test_booking_pages_served_with_app_shell(page, heading):
    """Both Booking UI pages load 200 OK inside Member 2's shell."""
    response = TestClient(app).get("/" + page)

    assert response.status_code == 200
    assert '<html lang="en">' in response.text
    assert heading in response.text
    assert '<link rel="stylesheet" href="/css/app.css">' in response.text
    assert '<link rel="stylesheet" href="/css/bookings.css">' in response.text
    assert '<script src="/js/app.js"></script>' in response.text
    assert '<script src="/js/booking-actions.js"></script>' in response.text


def test_booking_ui_assets_are_served():
    """Booking CSS and JS assets load cleanly with expected selectors/symbols."""
    client = TestClient(app)

    css_res = client.get("/css/bookings.css")
    assert css_res.status_code == 200
    assert ".badge-overdue" in css_res.text
    assert ".booking-card" in css_res.text

    js_res = client.get("/js/booking-actions.js")
    assert js_res.status_code == 200
    assert "DLBooking" in js_res.text
    assert "mountBookActions" in js_res.text
    assert "statusBadgeHtml" in js_res.text


def test_bookings_page_requires_login():
    """My Bookings page enforces DL.requireLogin()."""
    html = (WEB_DIR / "bookings.html").read_text(encoding="utf-8")
    assert "DL.requireLogin()" in html


def test_booking_ui_calls_only_mounted_api_endpoints():
    """Every literal /api/... endpoint in Booking UI HTML/JS matches OpenAPI routes."""
    openapi_paths = set(app.openapi()["paths"])
    sources = [
        (WEB_DIR / "bookings.html").read_text(encoding="utf-8"),
        (WEB_DIR / "book.html").read_text(encoding="utf-8"),
        (WEB_DIR / "js" / "booking-actions.js").read_text(encoding="utf-8"),
    ]
    called = set()
    for src in sources:
        called.update(re.findall(r'"(/api/[a-z_/]+)"', src))

    assert "/api/bookings/me" in called
    assert "/api/bookings" in called
    assert called <= openapi_paths


def test_booking_ui_status_badges_and_action_buttons():
    """Verify Reserve, Borrow, Cancel, Return controls and all status badges exist."""
    bookings_html = (WEB_DIR / "bookings.html").read_text(encoding="utf-8")
    book_html = (WEB_DIR / "book.html").read_text(encoding="utf-8")
    js = (WEB_DIR / "js" / "booking-actions.js").read_text(encoding="utf-8")

    # Book page actions
    assert "Reserve or Borrow" in book_html
    assert "Reserve Copy" in js
    assert "Borrow Now" in js

    # My Bookings controls and badges
    for action_name in ('data-action="borrow"', 'data-action="return"', 'data-action="cancel"'):
        assert action_name in bookings_html
        assert action_name in js

    for status_name in ("reserved", "borrowed", "returned", "cancelled", "expired", "overdue"):
        assert status_name in js
        assert status_name in bookings_html


def test_booking_ui_accessibility_and_semantics():
    """Verify ARIA live regions, explicit labels, and no inline onclick handlers."""
    for filename in ("bookings.html", "book.html"):
        html = (WEB_DIR / filename).read_text(encoding="utf-8")
        assert "<main>" in html
        assert "onclick=" not in html
        assert 'role="alert"' in html

    bookings_html = (WEB_DIR / "bookings.html").read_text(encoding="utf-8")
    assert 'for="status-filter"' in bookings_html
    assert 'role="status"' in bookings_html
    assert 'aria-live="polite"' in bookings_html
    assert 'aria-label="Return ' in bookings_html


def test_booking_ui_api_payload_compatibility():
    """Verify backend payloads match properties consumed by booking-actions.js and bookings.html."""
    isolated_app = FastAPI()
    isolated_app.include_router(bookings_router)
    service = BookingService(":memory:")
    service.seed_book(book_id=10, title="Clean Code", available_copies=2)
    set_booking_service(service)

    try:
        token = create_access_token(CurrentUser(1, "Demo Member", "member@example.com", "member"))
        headers = {"Authorization": f"Bearer {token}"}
        client = TestClient(isolated_app)

        res = client.post("/api/bookings", json={"book_id": 10}, headers=headers)
        assert res.status_code == 201
        created = res.json()
        assert {"id", "book_id", "status", "expires_at", "is_active"} <= set(created)

        borrowed = client.post(f"/api/bookings/{created['id']}/borrow", headers=headers).json()
        assert borrowed["status"] == "borrowed"
        assert borrowed["due_date"] is not None
        assert "overdue" in borrowed and "is_overdue" in borrowed

        me = client.get("/api/bookings/me", headers=headers).json()
        assert "items" in me and len(me["items"]) == 1

        returned = client.post(f"/api/bookings/{created['id']}/return", headers=headers).json()
        assert returned["status"] == "returned"
        assert returned["returned_at"] is not None
    finally:
        set_booking_service(None)
