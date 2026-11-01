"""DLBS-21 / DLBS-22: admin add, edit and soft delete (FR-C1, C2, C3, C8, NFR-C2)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src import catalog
from src.catalog.models import Book
from src.catalog.routes import get_db, router
from src.db import create_tables
from src.users.auth import CurrentUser, get_current_user

ADMIN = CurrentUser(2, "Test Admin", "admin@example.com", "admin")
MEMBER = CurrentUser(1, "Test Member", "member@example.com", "member")

NEW_BOOK = {
    "title": "Dracula",
    "author": "Bram Stoker",
    "isbn": "979-0-00-000009-4",
    "genre": "Horror",
    "page_count": 418,
    "total_copies": 3,
}


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_tables(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def make_client(session, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: session
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture
def admin(session):
    return make_client(session, ADMIN)


def add(admin, **overrides):
    response = admin.post("/api/books", json={**NEW_BOOK, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


# --- Create (FR-C1, NFR-C2) ---

def test_valid_add(admin):
    book = add(admin, description="A vampire novel.", year=1897,
               cover_url="https://covers.example.org/9.jpg")
    assert book["isbn"] == "9790000000094"  # hyphens removed
    assert book["available_copies"] == book["total_copies"] == 3
    assert admin.get(f"/api/books/{book['id']}").json() == book


@pytest.mark.parametrize(
    "field", ["title", "author", "isbn", "genre", "page_count", "total_copies"]
)
def test_missing_required_field(admin, field):
    body = {k: v for k, v in NEW_BOOK.items() if k != field}
    assert admin.post("/api/books", json=body).status_code == 422


@pytest.mark.parametrize("overrides", [
    {"title": "   "},
    {"isbn": "9790000000095"},          # wrong check digit
    {"isbn": "12345"},
    {"page_count": 0},
    {"total_copies": -1},
    {"year": 3000},
    {"cover_url": "ftp://x/y.jpg"},
])
def test_invalid_field(admin, overrides):
    assert admin.post("/api/books", json={**NEW_BOOK, **overrides}).status_code == 422


def test_isbn10_with_x_is_accepted(admin):
    assert add(admin, isbn="0-8044-2957-X")["isbn"] == "080442957X"


def test_duplicate_isbn(admin):
    add(admin)
    response = admin.post("/api/books", json={**NEW_BOOK, "isbn": "9790000000094"})
    assert response.status_code == 409
    assert response.json() == {"detail": "ISBN already exists"}


# --- Edit (FR-C2) ---

def test_edit_details(admin):
    book = add(admin)
    response = admin.put(f"/api/books/{book['id']}", json={"title": "Dracula (1897)", "year": None})
    assert response.status_code == 200
    assert response.json()["title"] == "Dracula (1897)"
    assert response.json()["author"] == "Bram Stoker"  # unchanged


def test_edit_copies_moves_available_by_same_amount(admin, session):
    book = add(admin, total_copies=4)
    catalog.change_available_copies(book["id"], -3, session)  # 3 on loan
    session.commit()

    up = admin.put(f"/api/books/{book['id']}", json={"total_copies": 6}).json()
    assert (up["total_copies"], up["available_copies"]) == (6, 3)

    too_low = admin.put(f"/api/books/{book['id']}", json={"total_copies": 2})
    assert too_low.status_code == 409
    after = admin.get(f"/api/books/{book['id']}").json()
    assert (after["total_copies"], after["available_copies"]) == (6, 3)  # nothing changed


def test_edit_to_another_books_isbn_is_rejected(admin):
    add(admin)
    other = add(admin, isbn="9790000000018")
    assert admin.put(f"/api/books/{other['id']}", json={"isbn": "9790000000094"}).status_code == 409


def test_edit_cannot_null_a_required_field(admin):
    book = add(admin)
    assert admin.put(f"/api/books/{book['id']}", json={"title": None}).status_code == 422


def test_edit_missing_book(admin):
    assert admin.put("/api/books/999", json={"title": "X"}).status_code == 404


# --- Soft delete (FR-C3) ---

def test_soft_delete_keeps_row_but_hides_book(admin, session):
    book = add(admin)
    assert admin.delete(f"/api/books/{book['id']}").status_code == 204

    assert admin.get(f"/api/books/{book['id']}").status_code == 404
    assert admin.get("/api/books").json()["total"] == 0
    assert session.get(Book, book["id"]) is not None  # row (and its history) kept
    assert catalog.get_availability(book["id"], db=session)["is_available"] is False
    assert admin.delete(f"/api/books/{book['id']}").status_code == 404
    assert admin.put(f"/api/books/{book['id']}", json={"title": "X"}).status_code == 404


# --- Only admins modify (FR-C8) ---

@pytest.mark.parametrize("user, code", [(None, 401), (MEMBER, 403)])
def test_non_admin_cannot_modify(session, admin, user, code):
    book = add(admin)
    client = make_client(session, user)
    assert client.post("/api/books", json={**NEW_BOOK, "isbn": "9790000000018"}).status_code == code
    assert client.put(f"/api/books/{book['id']}", json={"title": "X"}).status_code == code
    assert client.delete(f"/api/books/{book['id']}").status_code == code
    assert client.get(f"/api/books/{book['id']}").json()["title"] == "Dracula"  # reads stay public
