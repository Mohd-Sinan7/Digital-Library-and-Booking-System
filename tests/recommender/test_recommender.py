"""Tests for recommender skeleton, popularity baseline and cold start (FR-R3, FR-R4)."""

import dataclasses

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.catalog.models import Book
from src.db import create_tables
from src.recommender import (
    PopularityRecommender,
    Recommendation,
    Recommender,
    get_recommendations,
    get_recommender,
    refresh_recommendations,
    set_recommender,
)
from src.recommender.routes import get_db, router
from src.users.auth import CurrentUser, create_access_token
from src.users.models import FINISHED, READING, WANT_TO_READ, ReadingRecordRow

# Real signed tokens for test users 1 and 2
STUB_MEMBER_TOKEN = create_access_token(
    CurrentUser(1, "Test Member", "member@example.com", "member")
)
STUB_ADMIN_TOKEN = create_access_token(
    CurrentUser(2, "Test Admin", "admin@example.com", "admin")
)


@pytest.fixture
def session():
    """In-memory SQLite database session with all tables created."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_tables(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


@pytest.fixture
def client(session):
    """FastAPI test client with get_db overridden to use the test session."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_recommender():
    """Ensure active recommender is reset to baseline PopularityRecommender after each test."""
    yield
    set_recommender(PopularityRecommender())


def _add_book(session: Session, **overrides) -> Book:
    count = session.query(Book).count() + 1
    data = {
        "title": f"Test Book {count:02d}",
        "author": "Author A",
        "isbn": f"978000000{count:04d}",
        "genre": "Fiction",
        "description": "A great novel",
        "page_count": 250,
        "total_copies": 3,
        "available_copies": 3,
        "cover_url": f"https://covers.example.com/{count}.jpg",
    }
    data.update(overrides)
    book = Book(**data)
    session.add(book)
    session.commit()
    return book


def _add_record(
    session: Session, user_id: int, book_id: int, status: str = FINISHED
) -> ReadingRecordRow:
    row = ReadingRecordRow(
        user_id=user_id,
        book_id=book_id,
        status=status,
        current_page=100 if status == FINISHED else 20,
        percent=100.0 if status == FINISHED else 20.0,
    )
    session.add(row)
    session.commit()
    return row


# --- Unit Tests: Domain Models and Interface (NFR-R2) ---


def test_recommendation_dataclass():
    """Recommendation dataclass holds book_id, score, reason and is immutable."""
    rec = Recommendation(book_id=42, score=0.95, reason="Because you read X")
    assert rec.book_id == 42
    assert rec.score == 0.95
    assert rec.reason == "Because you read X"
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.score = 0.50  # type: ignore


def test_recommender_abstract_interface():
    """Recommender is an abstract base class and cannot be instantiated directly."""
    with pytest.raises(TypeError):
        Recommender()


def test_pluggable_recommender_interface():
    """NFR-R2: A different Recommender can be plugged in with no changes outside src/recommender."""

    class MockCustomRecommender(Recommender):
        def recommend(self, user_id: int, n: int = 10) -> list[Recommendation]:
            return [
                Recommendation(book_id=999, score=0.99, reason="Custom algorithmic score")
            ][:n]

    custom = MockCustomRecommender()
    set_recommender(custom)
    assert get_recommender() is custom

    with pytest.raises(TypeError):
        set_recommender("not a recommender")  # type: ignore


# --- Unit Tests: Popularity Recommender & Cold Start (FR-R3, FR-R4) ---


def test_popularity_recommender_empty_catalog(session):
    """Popularity recommender returns empty list when catalog is empty."""
    recommender = PopularityRecommender(db=session)
    recs = recommender.recommend(user_id=1, n=5)
    assert recs == []


def test_cold_start_user_gets_popular_books(session):
    """FR-R3: Cold-start user gets popular books, never an error or empty list."""
    # Seed 5 books in catalog
    b1 = _add_book(session, title="Book 1")
    b2 = _add_book(session, title="Book 2")
    b3 = _add_book(session, title="Book 3")

    recommender = PopularityRecommender(db=session)
    # User 99 has zero reading records
    recs = recommender.recommend(user_id=99, n=10)
    assert len(recs) == 3
    assert [r.book_id for r in recs] == [b1.id, b2.id, b3.id]
    assert recs[0].reason == "Popular among library readers"


def test_popularity_ordering_by_reader_counts(session):
    """Popularity recommender ranks books by reader counts descending across all users."""
    b1 = _add_book(session, title="Low Popularity Book")
    b2 = _add_book(session, title="High Popularity Book")
    b3 = _add_book(session, title="Medium Popularity Book")

    # b2 read by 3 users, b3 read by 2 users, b1 read by 1 user
    for uid in [10, 11, 12]:
        _add_record(session, user_id=uid, book_id=b2.id)
    for uid in [10, 11]:
        _add_record(session, user_id=uid, book_id=b3.id)
    _add_record(session, user_id=10, book_id=b1.id)

    recommender = PopularityRecommender(db=session)
    recs = recommender.recommend(user_id=999, n=3)

    assert len(recs) == 3
    assert recs[0].book_id == b2.id
    assert recs[1].book_id == b3.id
    assert recs[2].book_id == b1.id
    assert recs[0].score >= recs[1].score >= recs[2].score
    assert "3 readers" in recs[0].reason


def test_exclusion_of_finished_books(session):
    """FR-R4: The system shall not recommend books the user has already finished."""
    b1 = _add_book(session, title="Finished Book 1")
    b2 = _add_book(session, title="Unread Book 2")
    b3 = _add_book(session, title="Finished Book 3")
    b4 = _add_book(session, title="Currently Reading Book 4")
    b5 = _add_book(session, title="Want To Read Book 5")

    user_id = 42
    # User 42 has finished b1 and b3
    _add_record(session, user_id=user_id, book_id=b1.id, status=FINISHED)
    _add_record(session, user_id=user_id, book_id=b3.id, status=FINISHED)
    # b4 is in reading status, b5 is in want_to_read status (should NOT be excluded by FR-R4)
    _add_record(session, user_id=user_id, book_id=b4.id, status=READING)
    _add_record(session, user_id=user_id, book_id=b5.id, status=WANT_TO_READ)

    recommender = PopularityRecommender(db=session)
    recs = recommender.recommend(user_id=user_id, n=10)

    rec_book_ids = [r.book_id for r in recs]
    assert b1.id not in rec_book_ids
    assert b3.id not in rec_book_ids
    assert b2.id in rec_book_ids
    assert b4.id in rec_book_ids
    assert b5.id in rec_book_ids


def test_exclusion_of_removed_books(session):
    """FR-R4: Books removed / deleted from the catalog are never recommended."""
    b1 = _add_book(session, title="Active Book 1")
    b2 = _add_book(session, title="Deleted Book 2", is_deleted=True)

    recommender = PopularityRecommender(db=session)
    recs = recommender.recommend(user_id=1, n=5)

    rec_book_ids = [r.book_id for r in recs]
    assert b1.id in rec_book_ids
    assert b2.id not in rec_book_ids


def test_cold_start_genre_filtering(session):
    """FR-R3: Popularity cold start can filter by a chosen genre."""
    b_sci1 = _add_book(session, title="Dune", genre="Sci-Fi")
    b_sci2 = _add_book(session, title="Foundation", genre="Sci-Fi")
    _add_book(session, title="Emma", genre="Romance")

    recommender = PopularityRecommender(db=session)
    recs = recommender.recommend(user_id=1, n=10, genre="Sci-Fi")

    assert len(recs) == 2
    assert {r.book_id for r in recs} == {b_sci1.id, b_sci2.id}
    assert all("Sci-Fi" in r.reason for r in recs)


def test_edge_cases_n_zero_or_negative(session):
    """recommend with n <= 0 returns empty list without error."""
    _add_book(session)
    recommender = PopularityRecommender(db=session)
    assert recommender.recommend(user_id=1, n=0) == []
    assert recommender.recommend(user_id=1, n=-5) == []


# --- Unit Tests: Service Layer ---


def test_service_get_recommendations_enriches_catalog_fields(session):
    """Service enriches recommendations with book details for home page cards."""
    b1 = _add_book(session, title="Python Mastery", author="Guido", cover_url="https://cov.jpg")
    b2 = _add_book(session, title="Clean Code", author="Robert", is_deleted=True)

    class FixedRecommender(Recommender):
        def recommend(self, user_id: int, n: int = 10) -> list[Recommendation]:
            return [
                Recommendation(book_id=b1.id, score=0.9, reason="Because you read Python 101"),
                Recommendation(book_id=b2.id, score=0.8, reason="Deleted book test"),
                Recommendation(book_id=99999, score=0.7, reason="Non-existent book"),
            ][:n]

    set_recommender(FixedRecommender())

    results = get_recommendations(user_id=1, limit=5, db=session)
    assert len(results) == 1
    card = results[0]
    assert card["book_id"] == b1.id
    assert card["title"] == "Python Mastery"
    assert card["author"] == "Guido"
    assert card["cover_url"] == "https://cov.jpg"
    assert card["score"] == 0.9
    assert card["reason"] == "Because you read Python 101"

    assert get_recommendations(user_id=1, limit=0, db=session) == []


def test_service_with_recommender_without_db_param(session):
    """Service seamlessly executes a Recommender that does not accept db in recommend()."""
    b1 = _add_book(session, title="Standard Recommender Book")

    class SimpleRecommender(Recommender):
        def recommend(self, user_id: int, n: int = 10) -> list[Recommendation]:
            return [Recommendation(book_id=b1.id, score=0.88, reason="Simple baseline")][:n]

    set_recommender(SimpleRecommender())
    results = get_recommendations(user_id=1, limit=5, db=session)
    assert len(results) == 1
    assert results[0]["book_id"] == b1.id


def test_refresh_recommendations_service():
    """Service refresh function returns success status (FR-R6)."""
    res = refresh_recommendations()
    assert res["status"] == "ok"
    assert "refreshed successfully" in res["message"]


def test_get_db_generator():
    """get_db dependency yields a working session."""
    gen = get_db()
    db_session = next(gen)
    assert db_session is not None
    try:
        next(gen)
    except StopIteration:
        pass


# --- Integration / API Tests: Endpoints (FR-R1, FR-R3, FR-R6) ---


def test_get_recommendations_endpoint_requires_auth(client):
    """GET /api/recommendations/me returns 401 without Bearer token."""
    response = client.get("/api/recommendations/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_get_recommendations_endpoint_success_and_cold_start(client, session):
    """GET /api/recommendations/me returns 200 with popular books for cold start user."""
    b1 = _add_book(session, title="Domain-Driven Design", genre="Tech")
    b2 = _add_book(session, title="Refactoring", genre="Tech")
    _add_book(session, title="Cooking 101", genre="Food")

    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}
    response = client.get("/api/recommendations/me", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["count"] == 3
    assert len(data["items"]) == 3

    # Test genre filtering query parameter
    res_genre = client.get("/api/recommendations/me?genre=Tech", headers=headers)
    assert res_genre.status_code == 200
    tech_data = res_genre.json()
    assert tech_data["count"] == 2
    assert {i["book_id"] for i in tech_data["items"]} == {b1.id, b2.id}


@pytest.mark.parametrize("bad_limit", [0, -1, 51])
def test_get_recommendations_endpoint_validation(client, bad_limit):
    """GET /api/recommendations/me validates limit query parameter."""
    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}
    response = client.get(f"/api/recommendations/me?limit={bad_limit}", headers=headers)
    assert response.status_code == 422


def test_refresh_endpoint_admin_only(client):
    """POST /api/recommendations/refresh requires admin role (403 for member, 200 for admin)."""
    assert client.post("/api/recommendations/refresh").status_code == 401

    member_headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}
    res_member = client.post("/api/recommendations/refresh", headers=member_headers)
    assert res_member.status_code == 403
    assert res_member.json()["detail"] == "Admin privileges required"

    admin_headers = {"Authorization": f"Bearer {STUB_ADMIN_TOKEN}"}
    res_admin = client.post("/api/recommendations/refresh", headers=admin_headers)
    assert res_admin.status_code == 200
    assert res_admin.json()["status"] == "ok"
