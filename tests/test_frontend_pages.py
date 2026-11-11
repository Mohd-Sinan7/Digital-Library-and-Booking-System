"""Unit and integration tests for frontend static pages (DLBS-23, DLBS-45, DLBS-21)."""

from pathlib import Path

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_frontend_pages_exist_on_filesystem():
    web_dir = Path("src/web")
    required_files = [
        "index.html",
        "catalog.html",
        "book.html",
        "bookings.html",
        "admin.html",
        "login.html",
        "register.html",
        "profile.html",
        "reading.html",
        "css/app.css",
        "js/app.js",
    ]
    for rel_path in required_files:
        p = web_dir / rel_path
        assert p.exists(), f"Expected {rel_path} to exist in src/web"


def test_fastapi_serves_all_frontend_pages():
    routes = [
        ("/", 200),
        ("/index.html", 200),
        ("/catalog.html", 200),
        ("/book.html", 200),
        ("/bookings.html", 200),
        ("/admin.html", 200),
        ("/login.html", 200),
        ("/register.html", 200),
        ("/profile.html", 200),
        ("/reading.html", 200),
        ("/css/app.css", 200),
        ("/js/app.js", 200),
    ]
    for path, expected_status in routes:
        response = client.get(path)
        assert (
            response.status_code == expected_status
        ), f"Route {path} returned {response.status_code}"


def test_catalog_html_elements():
    content = Path("src/web/catalog.html").read_text(encoding="utf-8")
    assert "/css/app.css" in content
    assert "/js/app.js" in content
    assert 'id="q"' in content
    assert 'id="genre"' in content
    assert 'id="available"' in content
    assert 'id="book-grid"' in content
    assert "DL.bookCard" in content


def test_book_html_elements():
    content = Path("src/web/book.html").read_text(encoding="utf-8")
    assert "/css/app.css" in content
    assert "/js/app.js" in content
    assert 'id="book-title"' in content
    assert 'id="booking-actions"' in content
    assert 'id="reading-section"' in content
    assert 'id="admin-section"' in content
    assert "/api/bookings" in content


def test_bookings_html_elements():
    content = Path("src/web/bookings.html").read_text(encoding="utf-8")
    assert "/css/app.css" in content
    assert "/js/app.js" in content
    assert "DL.requireLogin()" in content
    assert "/api/bookings/me" in content
    assert "btn-borrow" in content
    assert "btn-return" in content


def test_admin_html_elements():
    content = Path("src/web/admin.html").read_text(encoding="utf-8")
    assert "/css/app.css" in content
    assert "/js/app.js" in content
    assert "DL.requireLogin()" in content
    assert 'id="refresh-models-btn"' in content
    assert 'id="book-form"' in content
    assert 'id="inventory-tbody"' in content


def test_index_html_elements():
    content = Path("src/web/index.html").read_text(encoding="utf-8")
    assert "/css/app.css" in content
    assert "/js/app.js" in content
    assert "hero-search" in content
    assert 'id="recommendations-grid"' in content
    assert "/api/recommendations/me" in content
