"""Tests for Recommendation Engine skeleton, common interface and endpoints (NFR-R2, NFR-R3)."""

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
from src.users.auth import STUB_ADMIN_TOKEN, STUB_MEMBER_TOKEN


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


# --- Unit Tests: Domain Models and Interface (NFR-R2) ---


def test_recommendation_dataclass():
    """Recommendation dataclass holds book_id, score, reason and is immutable."""
    rec = Recommendation(book_id=42, score=0.95, reason="Because you read X")
    assert rec.book_id == 42
    assert rec.score == 0.95
    assert rec.reason == "Because you read X"
    with pytest.raises(Exception):
        rec.score = 0.50  # frozen dataclass


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

    # Verify type checking on set_recommender
    with pytest.raises(TypeError):
        set_recommender("not a recommender")  # type: ignore


# --- Unit Tests: Popularity Recommender & Service ---


def test_popularity_recommender_empty_catalog(session):
    """Popularity recommender returns empty list when catalog is empty."""
    recommender = PopularityRecommender(db=session)
    recs = recommender.recommend(user_id=1, n=5)
    assert recs == []


def test_popularity_recommender_with_books(session):
    """Popularity recommender produces ranked scores descending from 1.0."""
    for _ in range(5):
        _add_book(session)

    recommender = PopularityRecommender(db=session)
    recs = recommender.recommend(user_id=1, n=3)
    assert len(recs) == 3
    assert recs[0].book_id == 1
    assert recs[0].score >= recs[1].score >= recs[2].score
    assert recs[0].reason == "Popular among library readers"

    # Edge case: n <= 0
    assert recommender.recommend(user_id=1, n=0, db=session) == []


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
    # b2 is deleted and 99999 does not exist, so only b1 should be returned (FR-R4)
    assert len(results) == 1
    card = results[0]
    assert card["book_id"] == b1.id
    assert card["title"] == "Python Mastery"
    assert card["author"] == "Guido"
    assert card["cover_url"] == "https://cov.jpg"
    assert card["score"] == 0.9
    assert card["reason"] == "Because you read Python 101"

    # limit <= 0 returns empty list
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


# --- Integration / API Tests: Endpoints (FR-R1, FR-R6) ---


def test_get_recommendations_endpoint_requires_auth(client):
    """GET /api/recommendations/me returns 401 without Bearer token."""
    response = client.get("/api/recommendations/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_get_recommendations_endpoint_success(client, session):
    """GET /api/recommendations/me returns 200 and items for authenticated member."""
    b1 = _add_book(session, title="Domain-Driven Design")

    class SingleBookRecommender(Recommender):
        def recommend(self, user_id: int, n: int = 10) -> list[Recommendation]:
            return [Recommendation(book_id=b1.id, score=0.95, reason="Top choice")][:n]

    set_recommender(SingleBookRecommender())

    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}
    response = client.get("/api/recommendations/me", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["count"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["book_id"] == b1.id
    assert data["items"][0]["title"] == "Domain-Driven Design"
    assert data["items"][0]["score"] == 0.95
    assert data["items"][0]["reason"] == "Top choice"


@pytest.mark.parametrize("bad_limit", [0, -1, 51])
def test_get_recommendations_endpoint_validation(client, bad_limit):
    """GET /api/recommendations/me validates limit query parameter."""
    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}
    response = client.get(f"/api/recommendations/me?limit={bad_limit}", headers=headers)
    assert response.status_code == 422


def test_refresh_endpoint_admin_only(client):
    """POST /api/recommendations/refresh requires admin role (403 for member, 200 for admin)."""
    # 1. No token -> 401
    assert client.post("/api/recommendations/refresh").status_code == 401

    # 2. Member token -> 403 Forbidden
    member_headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}
    res_member = client.post("/api/recommendations/refresh", headers=member_headers)
    assert res_member.status_code == 403
    assert res_member.json()["detail"] == "Admin privileges required"

    # 3. Admin token -> 200 OK
    admin_headers = {"Authorization": f"Bearer {STUB_ADMIN_TOKEN}"}
    res_admin = client.post("/api/recommendations/refresh", headers=admin_headers)
    assert res_admin.status_code == 200
    assert res_admin.json()["status"] == "ok"
