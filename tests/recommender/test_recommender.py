"""Tests for recommender skeleton, popularity baseline and cold start (FR-R1, FR-R3, FR-R4)."""

import dataclasses
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.catalog.models import Book
from src.db import create_tables
from src.recommender import (
    ContentBasedRecommender,
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
    b1 = _add_book(session, title="Book 1")
    b2 = _add_book(session, title="Book 2")
    b3 = _add_book(session, title="Book 3")

    recommender = PopularityRecommender(db=session)
    recs = recommender.recommend(user_id=99, n=10)
    assert len(recs) == 3
    assert [r.book_id for r in recs] == [b1.id, b2.id, b3.id]
    assert recs[0].reason == "Popular among library readers"


def test_popularity_ordering_by_reader_counts(session):
    """Popularity recommender ranks books by reader counts descending across all users."""
    b1 = _add_book(session, title="Low Popularity Book")
    b2 = _add_book(session, title="High Popularity Book")
    b3 = _add_book(session, title="Medium Popularity Book")

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
    _add_record(session, user_id=user_id, book_id=b1.id, status=FINISHED)
    _add_record(session, user_id=user_id, book_id=b3.id, status=FINISHED)
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
    """FR-R1: GET /api/recommendations/me returns 401 without Bearer token."""
    response = client.get("/api/recommendations/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.parametrize(
    "bad_auth",
    [
        "Basic dXNlcjpwYXNz",
        "Bearer invalid-jwt-token-garbage",
        "Bearer ",
        "Token some-other-token",
    ],
)
def test_get_recommendations_endpoint_rejects_bad_token(client, bad_auth):
    """FR-R1: Invalid or malformed tokens get rejected with 401."""
    response = client.get("/api/recommendations/me", headers={"Authorization": bad_auth})
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_get_recommendations_endpoint_rejects_expired_token(client):
    """FR-R1: Expired tokens get rejected with 401."""
    user = CurrentUser(1, "Test Member", "member@example.com", "member")
    expired_token = create_access_token(user, expires_in=timedelta(minutes=-5))
    response = client.get(
        "/api/recommendations/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_get_recommendations_endpoint_limit_and_sorted_by_score(client, session):
    """FR-R1: GET /api/recommendations/me?limit=10 returns at most 10 items sorted by score.

    Each item carries: book_id, title, author, cover_url, score, reason.
    """
    # Seed 15 books with varied popularity
    books = []
    for i in range(1, 16):
        b = _add_book(
            session,
            title=f"Sample Book {i:02d}",
            author=f"Author {i}",
            cover_url=f"https://covers.example.org/{i}.jpg",
        )
        books.append(b)

    # Add different reader counts to create distinct scores
    # Book 1: 5 readers, Book 2: 4 readers, Book 3: 3 readers, etc.
    for idx, b in enumerate(books[:5]):
        for uid in range(10, 10 + (5 - idx)):
            _add_record(session, user_id=uid, book_id=b.id)

    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}

    # 1. Request with limit=10 on 15 catalog books
    response = client.get("/api/recommendations/me?limit=10", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "items" in data and "count" in data
    assert data["count"] == 10
    items = data["items"]
    assert len(items) == 10

    # Verify every required field is present in each recommendation card
    required_keys = {"book_id", "title", "author", "cover_url", "score", "reason"}
    for item in items:
        assert required_keys.issubset(item.keys())
        assert isinstance(item["book_id"], int)
        assert isinstance(item["title"], str)
        assert isinstance(item["author"], str)
        assert isinstance(item["score"], (int, float))
        assert isinstance(item["reason"], str)

    # Verify items are strictly sorted by score in descending order (FR-R1)
    scores = [item["score"] for item in items]
    assert scores == sorted(scores, reverse=True)
    for i in range(len(items) - 1):
        assert items[i]["score"] >= items[i + 1]["score"]

    # 2. Request with limit=5 returns at most 5 items
    res_limit_5 = client.get("/api/recommendations/me?limit=5", headers=headers)
    assert res_limit_5.status_code == 200
    assert len(res_limit_5.json()["items"]) == 5
    assert res_limit_5.json()["count"] == 5


def test_get_recommendations_endpoint_genre_filter(client, session):
    """FR-R3: GET /api/recommendations/me?genre=... filters results to specified genre."""
    b1 = _add_book(session, title="Domain-Driven Design", genre="Tech")
    b2 = _add_book(session, title="Refactoring", genre="Tech")
    _add_book(session, title="Cooking 101", genre="Food")

    headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}
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



# ==============================================================================
# Content-Based Filtering with TF-IDF Tests (FR-R2, DLBS-11)
# ==============================================================================


def test_content_based_recommender_inherits_recommender():
    """NFR-R2: ContentBasedRecommender implements the common Recommender interface."""
    cb = ContentBasedRecommender()
    assert isinstance(cb, Recommender)


def test_content_based_recommender_empty_catalog(session):
    """ContentBasedRecommender returns empty list when catalog is empty."""
    cb = ContentBasedRecommender(db=session)
    assert cb.recommend(user_id=1, n=10) == []


def test_content_based_recommender_negative_or_zero_n(session):
    """ContentBasedRecommender returns empty list for non-positive n."""
    _add_book(session, title="Book 1")
    cb = ContentBasedRecommender(db=session)
    assert cb.recommend(user_id=1, n=0) == []
    assert cb.recommend(user_id=1, n=-5) == []


def test_content_based_recommender_cold_start_fallback(session):
    """FR-R3: Cold-start user with no history falls back to popularity recommendations."""
    b1 = _add_book(session, title="Popular Book 1", genre="Tech")
    b2 = _add_book(session, title="Popular Book 2", genre="Tech")
    # User 1 has no reading records
    cb = ContentBasedRecommender(db=session)
    recs = cb.recommend(user_id=1, n=10)
    assert len(recs) == 2
    assert [r.book_id for r in recs] == [b1.id, b2.id]
    assert "Popular" in recs[0].reason


def test_content_based_recommender_genre_affinity_acceptance_criterion(session):
    """FR-R2 Acceptance Criterion:

    For a user who finished several books of one genre, at least 3 of the top 5 share it.
    """
    # Seed 6 Sci-Fi books
    scifi_books = [
        _add_book(
            session,
            title="Dune Chronicles",
            genre="Sci-Fi",
            description="Epic space opera dune sand planet spice desert interstellar empire",
        ),
        _add_book(
            session,
            title="Foundation and Empire",
            genre="Sci-Fi",
            description="Galactic empire psychohistory Hari Seldon mathematics future galaxy",
        ),
        _add_book(
            session,
            title="Neuromancer Matrix",
            genre="Sci-Fi",
            description="Cyberpunk artificial intelligence hacker cyberspace matrix virtual",
        ),
        _add_book(
            session,
            title="Hyperion Cantos",
            genre="Sci-Fi",
            description="Time tombs pilgrimage shrike space warfare Hegemony of Man",
        ),
        _add_book(
            session,
            title="Solaris Station",
            genre="Sci-Fi",
            description="Living sentient ocean planet research station astronaut spacecraft",
        ),
        _add_book(
            session,
            title="Snow Crash",
            genre="Sci-Fi",
            description="Metaverse hacker pizza delivery virtual reality cyber futuristic",
        ),
    ]

    # Seed books of other genres
    other_books = [
        _add_book(
            session,
            title="Pride and Prejudice",
            genre="Romance",
            description="Elizabeth Bennet Mr Darcy classic regency romance estate marriage love",
        ),
        _add_book(
            session,
            title="Sense and Sensibility",
            genre="Romance",
            description="Dashwood sisters romantic courtship inheritance English society love",
        ),
        _add_book(
            session,
            title="The French Chef Cookbook",
            genre="Cooking",
            description="Delicious french recipes gourmet pastry baking cuisine kitchen dinner",
        ),
        _add_book(
            session,
            title="Joy of Cooking",
            genre="Cooking",
            description="Home cooking recipes meals breakfast lunch dinner roasted chicken",
        ),
    ]

    # User 42 has finished 2 Sci-Fi books
    user_id = 42
    _add_record(session, user_id=user_id, book_id=scifi_books[0].id, status=FINISHED)
    _add_record(session, user_id=user_id, book_id=scifi_books[1].id, status=FINISHED)

    cb = ContentBasedRecommender(db=session)
    recs = cb.recommend(user_id=user_id, n=5)

    # Must return 5 recommendations
    assert len(recs) == 5

    # Finished books must be excluded (FR-R4)
    rec_bids = [r.book_id for r in recs]
    assert scifi_books[0].id not in rec_bids
    assert scifi_books[1].id not in rec_bids

    # Acceptance criterion: At least 3 of the top 5 share the finished genre ('Sci-Fi')
    catalog_map = {b.id: b.genre for b in scifi_books + other_books}
    rec_genres = [catalog_map[bid] for bid in rec_bids]
    scifi_count = sum(1 for g in rec_genres if g == "Sci-Fi")
    assert scifi_count >= 3, f"Expected >= 3 Sci-Fi books in top 5, got {scifi_count}: {rec_genres}"

    # Scores must be descending
    scores = [r.score for r in recs]
    assert scores == sorted(scores, reverse=True)
    assert all(s > 0 for s in scores[:scifi_count])


def test_content_based_recommender_weighted_by_progress(session):
    """User profile weights vectors by reading progress (finished=1.0, in-progress=percent)."""
    b_history = _add_book(
        session,
        title="Ancient Rome History",
        genre="History",
        description="Roman empire emperors legions senate warfare Caesar",
    )
    b_tech = _add_book(
        session,
        title="Python Data Science",
        genre="Tech",
        description="Machine learning data science programming algorithms python code",
    )
    b_history_unread = _add_book(
        session,
        title="Fall of the Roman Empire",
        genre="History",
        description="Decline and fall barbarian invasions Roman legions emperors Caesar",
    )
    _add_book(
        session,
        title="Deep Learning with Python",
        genre="Tech",
        description="Neural networks deep learning artificial intelligence python code",
    )

    user_id = 55
    # Finished history book (100% progress)
    _add_record(session, user_id=user_id, book_id=b_history.id, status=FINISHED)
    # Just started tech book (5% progress)
    r2 = ReadingRecordRow(
        user_id=user_id,
        book_id=b_tech.id,
        status=READING,
        current_page=10,
        percent=5.0,
    )
    session.add(r2)
    session.commit()

    cb = ContentBasedRecommender(db=session)
    recs = cb.recommend(user_id=user_id, n=2)

    # History candidate should be ranked higher due to 100% finished progress vs 5%
    assert len(recs) == 2
    assert recs[0].book_id == b_history_unread.id
    assert recs[0].score > recs[1].score


def test_content_based_recommender_excludes_deleted_books(session):
    """FR-R4: Soft-deleted books are never recommended."""
    b1 = _add_book(session, title="AI Guide", genre="Tech", description="Artificial intelligence")
    b2 = _add_book(
        session, title="ML Guide", genre="Tech", description="Machine learning AI", is_deleted=True
    )

    user_id = 60
    _add_record(session, user_id=user_id, book_id=b1.id, status=FINISHED)

    cb = ContentBasedRecommender(db=session)
    recs = cb.recommend(user_id=user_id, n=10)
    assert b2.id not in [r.book_id for r in recs]


def test_content_based_recommender_genre_filter(session):
    """ContentBasedRecommender supports explicit genre filtering."""
    b1 = _add_book(session, title="Sci-Fi One", genre="Sci-Fi", description="Space interstellar")
    _add_book(session, title="Sci-Fi Two", genre="Sci-Fi", description="Space galaxy")
    b3 = _add_book(session, title="Romantic Sunset", genre="Romance", description="Love romance")

    user_id = 70
    _add_record(session, user_id=user_id, book_id=b1.id, status=FINISHED)

    cb = ContentBasedRecommender(db=session)
    recs = cb.recommend(user_id=user_id, n=10, genre="Romance")
    assert len(recs) == 1
    assert recs[0].book_id == b3.id


def test_get_recommendations_with_content_based_active(session):
    """End-to-end get_recommendations service uses ContentBasedRecommender."""
    b1 = _add_book(session, title="Book Alpha", genre="Sci-Fi", description="Alien galaxy space")
    b2 = _add_book(
        session, title="Book Beta", genre="Sci-Fi", description="Alien planet space exploration"
    )

    user_id = 80
    _add_record(session, user_id=user_id, book_id=b1.id, status=FINISHED)

    set_recommender(ContentBasedRecommender(db=session))
    items = get_recommendations(user_id=user_id, limit=5, db=session)

    assert len(items) == 1
    assert items[0]["book_id"] == b2.id
    assert items[0]["genre"] == "Sci-Fi"
    assert "interest in Sci-Fi" in items[0]["reason"]
    assert items[0]["score"] > 0
