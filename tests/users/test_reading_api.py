from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.catalog.models import Book
from src.db import create_tables
from src.users import reading
from src.users.auth import CurrentUser, create_access_token
from src.users.models import FINISHED, MEMBER, READING, WANT_TO_READ, ReadingRecordRow, User
from src.users.reading_routes import router
from src.users.routes import get_db

ASHA = {"Authorization": "Bearer " + create_access_token(
    CurrentUser(1, "Asha Rao", "asha@example.com", MEMBER))}
RAVI = {"Authorization": "Bearer " + create_access_token(
    CurrentUser(2, "Ravi Kumar", "ravi@example.com", MEMBER))}
START = datetime(2026, 11, 3, 13, 0, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_tables(engine)
    with Session(engine) as session:
        session.add_all([
            User(id=1, name="Asha Rao", email="asha@example.com", password_hash="hashed"),
            User(id=2, name="Ravi Kumar", email="ravi@example.com", password_hash="hashed"),
            Book(id=42, title="The Pragmatic Programmer", author="Andrew Hunt, David Thomas",
                 isbn="9780135957059", genre="Technology", page_count=320, total_copies=2),
            Book(id=7, title="Dracula", author="Bram Stoker", isbn="9780141439846",
                 genre="Horror", page_count=400, total_copies=1),
            Book(id=9, title="Removed Book", author="Someone", isbn="9780306406157",
                 genre="Fiction", page_count=100, total_copies=1, is_deleted=True),
        ])
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def client(session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as test_client:
        yield test_client


def set_status(client, book_id, status, headers=ASHA):
    return client.put("/api/reading/status", json={"book_id": book_id, "status": status},
                      headers=headers)


def progress(client, headers=ASHA, **body):
    return client.post("/api/reading/progress", json={"book_id": 42, **body}, headers=headers)


def record_count(session):
    return session.scalar(select(func.count()).select_from(ReadingRecordRow))


# PUT /api/reading/status (FR-U5)

def test_set_status_creates_the_record_with_book_details(client):
    response = set_status(client, 42, READING)

    assert response.status_code == 200
    body = response.json()
    assert {k: body[k] for k in ("book_id", "title", "author", "genre", "status")} == {
        "book_id": 42, "title": "The Pragmatic Programmer",
        "author": "Andrew Hunt, David Thomas", "genre": "Technology", "status": READING}
    assert (body["current_page"], body["percent"]) == (0, 0.0)
    assert body["started_at"].endswith("Z") and body["updated_at"].endswith("Z")


def test_want_to_read_has_no_start_time(client):
    assert set_status(client, 42, WANT_TO_READ).json()["started_at"] is None


def test_status_is_saved_per_user_and_book(client, session):
    set_status(client, 42, WANT_TO_READ)
    set_status(client, 42, READING)
    set_status(client, 42, FINISHED, headers=RAVI)

    assert record_count(session) == 2
    assert [r.status for r in reading.get_history(1, db=session)] == [READING]
    assert [r.status for r in reading.get_history(2, db=session)] == [FINISHED]


def test_finished_status_counts_every_page(client):
    body = set_status(client, 42, FINISHED).json()

    assert (body["status"], body["current_page"], body["percent"]) == (FINISHED, 320, 100.0)


def test_unknown_status_is_422(client, session):
    assert set_status(client, 42, "abandoned").status_code == 422
    assert record_count(session) == 0


@pytest.mark.parametrize("book_id", [999, 9])
def test_unknown_or_removed_book_is_404(client, book_id):
    response = set_status(client, book_id, READING)

    assert response.status_code == 404
    assert response.json()["detail"] == "Book not found"


# POST /api/reading/progress (FR-U6)

def test_page_120_of_320_is_37_5_percent(client):
    body = progress(client, current_page=120).json()

    assert (body["current_page"], body["percent"], body["status"]) == (120, 37.5, READING)
    assert body["started_at"] is not None


def test_percent_is_turned_into_a_page(client):
    body = progress(client, percent=37.5).json()

    assert (body["current_page"], body["percent"]) == (120, 37.5)


def test_progress_moves_want_to_read_to_reading(client):
    set_status(client, 42, WANT_TO_READ)

    assert progress(client, current_page=10).json()["status"] == READING


@pytest.mark.parametrize("body", [{"current_page": 320}, {"percent": 100}])
def test_reaching_100_percent_marks_the_book_finished(client, body):
    result = progress(client, **body).json()

    assert (result["status"], result["current_page"], result["percent"]) == (FINISHED, 320, 100)


def test_progress_below_100_on_a_finished_book_means_reading_again(client):
    set_status(client, 42, FINISHED)

    assert progress(client, current_page=5).json()["status"] == READING


def test_progress_updates_the_same_record(client, session):
    progress(client, current_page=10)
    progress(client, current_page=20)

    assert record_count(session) == 1


@pytest.mark.parametrize("body", [
    {},
    {"current_page": 10, "percent": 5},
    {"current_page": -1},
    {"current_page": 321},
    {"percent": -0.5},
    {"percent": 100.5},
])
def test_invalid_progress_is_422(client, session, body):
    assert progress(client, **body).status_code == 422
    assert record_count(session) == 0


def test_progress_past_the_last_page_says_why(client):
    assert progress(client, current_page=321).json()["detail"] == (
        "current_page must be between 0 and 320")


def test_progress_on_unknown_book_is_404(client):
    response = client.post("/api/reading/progress", json={"book_id": 999, "current_page": 1},
                           headers=ASHA)

    assert response.status_code == 404


# GET /api/reading/history (FR-U7)

def test_empty_history(client):
    response = client.get("/api/reading/history", headers=ASHA)

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_history_is_newest_first_with_book_details(client, session):
    session.add_all([
        ReadingRecordRow(user_id=1, book_id=42, status=READING, current_page=120, percent=37.5,
                         started_at=START, updated_at=START + timedelta(days=1)),
        ReadingRecordRow(user_id=1, book_id=7, status=FINISHED, current_page=400, percent=100,
                         started_at=START, updated_at=START + timedelta(days=2)),
        ReadingRecordRow(user_id=1, book_id=9, updated_at=START),
        ReadingRecordRow(user_id=2, book_id=42, updated_at=START + timedelta(days=3)),
    ])
    session.commit()

    items = client.get("/api/reading/history", headers=ASHA).json()["items"]

    assert [(i["book_id"], i["title"]) for i in items] == [
        (7, "Dracula"), (42, "The Pragmatic Programmer"), (9, "Removed Book")]
    assert items[1]["started_at"] == "2026-11-03T13:00:00Z"
    assert items[1]["updated_at"] == "2026-11-04T13:00:00Z"


def test_history_can_be_filtered_by_status(client):
    set_status(client, 42, READING)
    set_status(client, 7, FINISHED)

    items = client.get("/api/reading/history?status=finished", headers=ASHA).json()["items"]

    assert [i["book_id"] for i in items] == [7]


def test_unknown_status_filter_is_422(client):
    assert client.get("/api/reading/history?status=abandoned", headers=ASHA).status_code == 422


@pytest.mark.parametrize("method, path", [
    ("put", "/api/reading/status"),
    ("post", "/api/reading/progress"),
    ("get", "/api/reading/history"),
])
def test_reading_endpoints_need_a_token(client, method, path):
    assert client.request(method, path).status_code == 401
