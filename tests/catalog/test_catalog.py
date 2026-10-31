import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
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


def add_book(session, **overrides):
    n = session.query(Book).count() + 1
    fields = {
        "title": f"Book {n:02d}",
        "author": "Some Author",
        "isbn": f"978000000{n:04d}",
        "genre": "Fiction",
        "page_count": 100,
        "total_copies": 2,
    }
    fields.update(overrides)
    book = Book(**fields)
    session.add(book)
    session.commit()
    return book


@pytest.fixture
def client(session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: session
    return TestClient(app)


# --- Book table (DLBS-6) ---

def test_new_book_starts_with_all_copies_available(session):
    book = add_book(session, total_copies=4)
    assert book.available_copies == 4
    assert book.is_deleted is False
    assert book.created_at is not None


def test_duplicate_isbn_is_rejected(session):
    add_book(session, isbn="9790000000018")
    with pytest.raises(IntegrityError):
        add_book(session, isbn="9790000000018")


def test_book_dict_has_contract_fields(session):
    book = add_book(session)
    data = catalog.get_book(book.id, db=session)
    assert set(data) == {
        "id", "title", "author", "isbn", "genre", "description", "year",
        "page_count", "cover_url", "total_copies", "available_copies", "created_at",
    }
    assert data["created_at"].endswith("Z")


def test_get_book_missing_and_deleted(session):
    book = add_book(session, is_deleted=True)
    assert catalog.get_book(999, db=session) is None
    assert catalog.get_book(book.id, db=session) is None
    assert catalog.get_book(book.id, include_deleted=True, db=session)["is_deleted"] is True


def test_availability(session):
    book = add_book(session, total_copies=3)
    assert catalog.get_availability(book.id, db=session) == {
        "book_id": book.id, "total_copies": 3, "available_copies": 3,
        "is_available": True, "is_deleted": False,
    }
    assert catalog.get_availability(999, db=session) is None


def test_availability_of_deleted_book_is_not_available(session):
    book = add_book(session, is_deleted=True)
    assert catalog.get_availability(book.id, db=session)["is_available"] is False


def test_change_available_copies_stays_in_range(session):
    book = add_book(session, total_copies=1)
    assert catalog.change_available_copies(book.id, -1, session)["available_copies"] == 0
    with pytest.raises(ValueError):
        catalog.change_available_copies(book.id, -1, session)
    assert catalog.change_available_copies(book.id, +1, session)["available_copies"] == 1
    with pytest.raises(ValueError):
        catalog.change_available_copies(book.id, +1, session)


def test_deleted_book_can_be_returned_but_not_reserved(session):
    book = add_book(session, total_copies=2, available_copies=1, is_deleted=True)
    with pytest.raises(ValueError):
        catalog.change_available_copies(book.id, -1, session)
    assert catalog.change_available_copies(book.id, +1, session)["available_copies"] == 2


# --- Search and pagination (DLBS-7) ---

def test_search_by_title_author_and_isbn(session):
    add_book(session, title="Dracula", author="Bram Stoker", isbn="9790000000094")
    add_book(session, title="Emma", author="Jane Austen")

    def titles(q):
        return [b["title"] for b in catalog.get_books(q=q, db=session)["items"]]

    assert titles("drac") == ["Dracula"]
    assert titles("stoker") == ["Dracula"]
    assert titles("979-0-00-000009-4") == ["Dracula"]


def test_search_with_no_match(session):
    add_book(session, title="Dracula")
    result = catalog.get_books(q="zzz", db=session)
    assert result["items"] == [] and result["total"] == 0 and result["total_pages"] == 0


def test_empty_catalog(session):
    result = catalog.get_books(db=session)
    assert result["items"] == [] and result["total"] == 0


def test_deleted_books_are_not_listed(session):
    add_book(session, title="Gone", is_deleted=True)
    add_book(session, title="Here")
    assert [b["title"] for b in catalog.get_books(db=session)["items"]] == ["Here"]


def test_pagination(session):
    for _ in range(25):
        add_book(session)
    first = catalog.get_books(page=1, page_size=10, db=session)
    last = catalog.get_books(page=3, page_size=10, db=session)
    past = catalog.get_books(page=4, page_size=10, db=session)
    assert len(first["items"]) == 10 and first["total"] == 25 and first["total_pages"] == 3
    assert [b["title"] for b in last["items"]] == [f"Book {n:02d}" for n in range(21, 26)]
    assert past["items"] == [] and past["total"] == 25
    assert len(catalog.get_books(db=session)["items"]) == 25  # page_size=None: all


def test_invalid_page_is_rejected(session):
    with pytest.raises(ValueError):
        catalog.get_books(page=0, db=session)


def test_genre_and_availability_filters(session):
    add_book(session, title="A", genre="Horror", total_copies=1, available_copies=0)
    add_book(session, title="B", genre="horror")
    add_book(session, title="C", genre="Romance")

    def titles(**f):
        return [b["title"] for b in catalog.get_books(db=session, **f)["items"]]

    assert titles(genre="HORROR") == ["A", "B"]
    assert titles(available=True) == ["B", "C"]
    assert titles(available=False) == ["A"]


def test_list_endpoint_defaults_and_search(client, session):
    for _ in range(21):
        add_book(session)
    body = client.get("/api/books").json()
    assert body["page"] == 1 and body["page_size"] == 20 and len(body["items"]) == 20
    assert body["total"] == 21 and body["total_pages"] == 2
    assert client.get("/api/books", params={"q": "Book 07"}).json()["total"] == 1


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page_size": 101}])
def test_list_endpoint_rejects_bad_paging(client, params):
    assert client.get("/api/books", params=params).status_code == 422
