"""Tests for DLBS-14: Integration, caching, and admin refresh (FR-R6, NFR-R1).

Acceptance criteria:
  - FR-R6: POST /api/recommendations/refresh by an admin rebuilds the model
    and clears the cache; a member gets 403.
  - NFR-R1: Each of 20 uncached requests on the full seed takes under 2 s.
"""

from __future__ import annotations

import concurrent.futures
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.catalog.models import Book
from src.db import create_tables
from src.recommender.base import Recommendation, Recommender
from src.recommender.cache import RecommendationCache, recommendation_cache
from src.recommender.content_based import ContentBasedRecommender
from src.recommender.hybrid import HybridRecommender
from src.recommender.popularity import PopularityRecommender
from src.recommender.routes import get_db, router
from src.recommender.service import (
    get_recommendations,
    refresh_recommendations,
    set_recommender,
)
from src.users.auth import CurrentUser, create_access_token
from src.users.models import FINISHED, ReadingRecordRow

STUB_MEMBER_TOKEN = create_access_token(
    CurrentUser(1, "Test Member", "member@example.com", "member")
)
STUB_ADMIN_TOKEN = create_access_token(
    CurrentUser(2, "Test Admin", "admin@example.com", "admin")
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    """FastAPI test client with get_db overridden to use test session."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clean_cache_and_recommender():
    """Reset recommendation cache and active recommender before and after every test."""
    recommendation_cache.clear()
    recommendation_cache.reset_stats()
    set_recommender(PopularityRecommender())
    yield
    recommendation_cache.clear()
    recommendation_cache.reset_stats()
    set_recommender(PopularityRecommender())


def _add_book(session: Session, **overrides) -> Book:
    count = session.query(Book).count() + 1
    data = {
        "title": f"Test Book {count:02d}",
        "author": "Author A",
        "isbn": f"978000000{count:04d}",
        "genre": "Fiction",
        "description": "A great novel for testing",
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


# ===========================================================================
# 1. RecommendationCache Unit Tests
# ===========================================================================


class TestRecommendationCache:
    """Unit tests for the RecommendationCache data structure."""

    def test_cache_miss_returns_none(self):
        cache = RecommendationCache()
        assert cache.get(user_id=1, limit=10) is None
        assert cache.stats()["misses"] == 1
        assert cache.stats()["hits"] == 0

    def test_cache_set_and_hit(self):
        cache = RecommendationCache()
        items = [{"book_id": 1, "score": 0.9, "reason": "Popular"}]
        cache.set(user_id=1, limit=10, genre=None, value=items)

        cached = cache.get(user_id=1, limit=10, genre=None)
        assert cached == items
        # Ensure deep copy is returned (modifying returned list does not alter cache)
        cached.append({"book_id": 2})
        assert len(cache.get(user_id=1, limit=10, genre=None)) == 1
        assert cache.stats()["hits"] == 2

    def test_cache_ttl_expiration(self):
        cache = RecommendationCache(default_ttl=0.05)
        items = [{"book_id": 1, "score": 0.9, "reason": "Popular"}]
        cache.set(user_id=1, limit=10, genre=None, value=items)

        # Immediate get hits
        assert cache.get(user_id=1, limit=10) is not None

        # Wait for expiration
        time.sleep(0.08)
        assert cache.get(user_id=1, limit=10) is None
        assert cache.stats()["size"] == 0

    def test_cache_clear(self):
        cache = RecommendationCache()
        cache.set(1, 10, None, [{"book_id": 1}])
        cache.set(2, 5, "Sci-Fi", [{"book_id": 2}])
        assert cache.stats()["size"] == 2

        cleared = cache.clear()
        assert cleared == 2
        assert cache.stats()["size"] == 0
        assert cache.get(1, 10) is None
        assert cache.get(2, 5, "Sci-Fi") is None

    def test_cache_invalidate_user(self):
        cache = RecommendationCache()
        cache.set(1, 10, None, [{"book_id": 1}])
        cache.set(1, 5, "Sci-Fi", [{"book_id": 2}])
        cache.set(2, 10, None, [{"book_id": 3}])

        removed = cache.invalidate_user(1)
        assert removed == 2
        assert cache.get(1, 10) is None
        assert cache.get(1, 5, "Sci-Fi") is None
        assert cache.get(2, 10) is not None

    def test_cache_max_size_eviction(self):
        cache = RecommendationCache(max_size=3)
        cache.set(1, 10, None, [{"id": 1}])
        cache.set(2, 10, None, [{"id": 2}])
        cache.set(3, 10, None, [{"id": 3}])
        assert cache.stats()["size"] == 3

        # Adding 4th item evicts oldest (user 1)
        cache.set(4, 10, None, [{"id": 4}])
        assert cache.stats()["size"] == 3
        assert cache.get(1, 10) is None
        assert cache.get(4, 10) is not None

    def test_cache_thread_safety(self):
        cache = RecommendationCache()

        def worker(uid: int):
            for _ in range(50):
                cache.set(uid, 10, None, [{"id": uid}])
                res = cache.get(uid, 10)
                assert res is not None

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(1, 6)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        assert cache.stats()["size"] == 5


# ===========================================================================
# 2. Model Rebuilding (fit) Unit Tests
# ===========================================================================


class TestModelRebuilding:
    """Tests for recommender fit() and model precomputations."""

    def test_content_based_fit_precomputes_vectors(self, session):
        b1 = _add_book(session, title="Python Architecture", genre="Tech")
        b2 = _add_book(session, title="Advanced Python", genre="Tech")

        cb = ContentBasedRecommender(db=session)
        assert cb._tfidf_matrix is None

        cb.fit(db=session)
        assert cb._tfidf_matrix is not None
        assert cb._all_books is not None
        assert len(cb._all_books) >= 2
        assert b1.id in cb._book_id_to_vec
        assert b2.id in cb._book_id_to_vec

    def test_content_based_fit_empty_catalog(self, session):
        cb = ContentBasedRecommender(db=session)
        cb.fit(db=session)
        assert cb._all_books == []
        assert cb._tfidf_matrix is None

    def test_hybrid_fit_delegates_to_content(self, session):
        _add_book(session, title="Science Fiction Epic", genre="Sci-Fi")
        hybrid = HybridRecommender(alpha=0.7, db=session)
        assert hybrid.content_recommender._tfidf_matrix is None

        hybrid.fit(db=session)
        assert hybrid.content_recommender._tfidf_matrix is not None


# ===========================================================================
# 3. Service Layer Caching Tests
# ===========================================================================


class TestServiceCaching:
    """Tests for service get_recommendations and caching integration."""

    def test_service_caches_responses(self, session):
        b1 = _add_book(session, title="Book 1")
        _add_record(session, user_id=10, book_id=b1.id, status=FINISHED)

        call_count = 0

        class SpyRecommender(Recommender):
            def recommend(self, user_id: int, n: int = 10, **kwargs) -> list[Recommendation]:
                nonlocal call_count
                call_count += 1
                return [Recommendation(book_id=b1.id, score=0.95, reason="Popular")]

        set_recommender(SpyRecommender())

        # First call: computes and caches
        res1 = get_recommendations(user_id=10, limit=5, db=session)
        assert call_count == 1
        assert len(res1) == 1

        # Second call: served from cache (call_count unchanged)
        res2 = get_recommendations(user_id=10, limit=5, db=session)
        assert call_count == 1
        assert res1 == res2
        assert recommendation_cache.stats()["hits"] == 1

    def test_service_bypass_cache(self, session):
        b1 = _add_book(session, title="Book 1")
        call_count = 0

        class SpyRecommender(Recommender):
            def recommend(self, user_id: int, n: int = 10, **kwargs) -> list[Recommendation]:
                nonlocal call_count
                call_count += 1
                return [Recommendation(book_id=b1.id, score=0.9, reason="Popular")]

        set_recommender(SpyRecommender())

        get_recommendations(user_id=12, limit=5, db=session, use_cache=True)
        assert call_count == 1

        # Calling with use_cache=False re-runs calculation
        get_recommendations(user_id=12, limit=5, db=session, use_cache=False)
        assert call_count == 2

    def test_set_recommender_clears_cache(self, session):
        b1 = _add_book(session, title="Book 1")
        b2 = _add_book(session, title="Book 2")

        class RecA(Recommender):
            def recommend(self, user_id: int, n: int = 10, **kwargs) -> list[Recommendation]:
                return [Recommendation(book_id=b1.id, score=0.9, reason="Rec A")]

        class RecB(Recommender):
            def recommend(self, user_id: int, n: int = 10, **kwargs) -> list[Recommendation]:
                return [Recommendation(book_id=b2.id, score=0.9, reason="Rec B")]

        set_recommender(RecA())
        r1 = get_recommendations(user_id=15, limit=5, db=session)
        assert r1[0]["book_id"] == b1.id

        # Swapping recommender clears cache
        set_recommender(RecB())
        assert recommendation_cache.stats()["size"] == 0

        r2 = get_recommendations(user_id=15, limit=5, db=session)
        assert r2[0]["book_id"] == b2.id


# ===========================================================================
# 4. Admin Refresh Endpoint (FR-R6) Integration Tests
# ===========================================================================


class TestAdminRefreshEndpointFR6:
    """Acceptance tests for FR-R6: POST /api/recommendations/refresh."""

    def test_refresh_anonymous_returns_401(self, client):
        """Unauthenticated request must return 401."""
        response = client.post("/api/recommendations/refresh")
        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    def test_refresh_member_returns_403(self, client):
        """Regular member role must return 403 Forbidden."""
        headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}
        response = client.post("/api/recommendations/refresh", headers=headers)
        assert response.status_code == 403
        assert response.json()["detail"] == "Admin privileges required"

    def test_refresh_admin_rebuilds_and_clears_cache(self, client, session):
        """Admin request clears cache and rebuilds recommendation model (FR-R6)."""
        _add_book(session, title="Catalog Book")
        set_recommender(ContentBasedRecommender(db=session))

        # Seed cache with a request
        member_headers = {"Authorization": f"Bearer {STUB_MEMBER_TOKEN}"}
        get_res = client.get("/api/recommendations/me", headers=member_headers)
        assert get_res.status_code == 200
        assert recommendation_cache.stats()["size"] >= 1

        # Admin triggers refresh
        admin_headers = {"Authorization": f"Bearer {STUB_ADMIN_TOKEN}"}
        post_res = client.post("/api/recommendations/refresh", headers=admin_headers)

        assert post_res.status_code == 200
        data = post_res.json()
        assert data["status"] == "ok"
        assert "refreshed successfully" in data["message"]
        assert data["cached_entries_cleared"] >= 1
        assert data["model_rebuilt"] is True

        # Cache must now be empty
        assert recommendation_cache.stats()["size"] == 0

    def test_refresh_service_direct_call(self, session):
        """Direct call to refresh_recommendations(db) operates cleanly."""
        recommendation_cache.set(1, 10, None, [{"id": 1}])
        assert recommendation_cache.stats()["size"] == 1

        res = refresh_recommendations(db=session)
        assert res["status"] == "ok"
        assert res["cached_entries_cleared"] == 1
        assert recommendation_cache.stats()["size"] == 0


# ===========================================================================
# 5. Performance Requirement NFR-R1: 20 Uncached Requests < 2s
# ===========================================================================


class TestPerformanceRequirementNFR1:
    """Acceptance tests for NFR-R1: 20 uncached requests take under 2s each."""

    def test_twenty_uncached_requests_each_under_two_seconds(self, session):
        """NFR-R1: Each of 20 uncached requests on full seed takes under 2 s."""
        # Populate realistic book catalog (50 books across diverse genres)
        genres = ["Fiction", "Tech", "Sci-Fi", "Mystery", "History"]
        books = []
        for i in range(1, 51):
            g = genres[i % len(genres)]
            b = _add_book(
                session,
                title=f"Library Volume {i}",
                author=f"Author {i % 10}",
                genre=g,
                description=f"Engaging story about {g.lower()} and intellectual exploration.",
            )
            books.append(b)

        # Create reading records for multiple users
        for u in range(1, 25):
            # User reads 2 books
            _add_record(session, user_id=u, book_id=books[u % 50].id, status=FINISHED)
            _add_record(session, user_id=u, book_id=books[(u + 5) % 50].id, status="reading")

        # Use ContentBasedRecommender
        cb = ContentBasedRecommender(db=session)
        set_recommender(cb)

        durations = []
        # Execute 20 distinct uncached recommendation requests
        for user_id in range(1, 21):
            t_start = time.perf_counter()
            items = get_recommendations(
                user_id=user_id,
                limit=10,
                db=session,
                use_cache=False,  # Enforce UNCACHED request
            )
            elapsed = time.perf_counter() - t_start
            durations.append(elapsed)

            # Each individual request must take under 2 seconds (NFR-R1)
            assert elapsed < 2.0, (
                f"Request for user {user_id} took {elapsed:.3f}s (> 2.0s limit)"
            )
            assert len(items) > 0

        # Verify summary statistics
        max_duration = max(durations)
        avg_duration = sum(durations) / len(durations)

        # Ensure performance margin: average should be well below 500ms
        assert max_duration < 2.0
        assert avg_duration < 0.50, f"Average duration {avg_duration:.3f}s exceeds 0.50s"
