"""DLBS-24: genre list and availability endpoint (FR-C5)."""

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


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_tables(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app)


def add(session, n, **fields):
    book = Book(**{"title": f"B{n}", "author": "A", "isbn": f"97800000000{n:02d}",
                   "genre": "Fiction", "page_count": 10, "total_copies": 2, **fields})
    session.add(book)
    session.commit()
    return book


def test_availability_endpoint(client, session):
    book = add(session, 1, total_copies=3, available_copies=1)
    assert client.get(f"/api/books/{book.id}/availability").json() == {
        "book_id": book.id, "total_copies": 3, "available_copies": 1, "is_available": True,
    }


def test_availability_of_book_with_no_copies_left(client, session):
    book = add(session, 1, available_copies=0)
    assert client.get(f"/api/books/{book.id}/availability").json()["is_available"] is False


@pytest.mark.parametrize("deleted", [True, None])
def test_availability_404_for_missing_or_deleted(client, session, deleted):
    book_id = add(session, 1, is_deleted=True).id if deleted else 999
    assert client.get(f"/api/books/{book_id}/availability").status_code == 404


def test_genres_are_distinct_sorted_and_skip_deleted(client, session):
    add(session, 1, genre="Mystery")
    add(session, 2, genre="Fantasy")
    add(session, 3, genre="Mystery")
    add(session, 4, genre="Horror", is_deleted=True)
    assert client.get("/api/books/genres").json() == {"items": ["Fantasy", "Mystery"]}
    assert catalog.get_genres(db=session) == ["Fantasy", "Mystery"]
