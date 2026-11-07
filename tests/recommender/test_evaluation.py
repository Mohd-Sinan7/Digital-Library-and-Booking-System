"""Unit and integration tests for recommendation evaluation metrics (DLBS-13)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.catalog.models import Book
from src.db import create_tables
from src.recommender.base import Recommender
from src.recommender.content_based import ContentBasedRecommender
from src.recommender.evaluation import (
    compare_recommenders,
    evaluate_recommender,
    f1_at_k,
    format_evaluation_markdown,
    precision_at_k,
    recall_at_k,
    split_user_history,
)
from src.recommender.hybrid import HybridRecommender
from src.recommender.popularity import PopularityRecommender
from src.users.models import FINISHED, ReadingRecordRow


@pytest.fixture
def session():
    """In-memory SQLite database session."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_tables(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def _add_book(session: Session, **overrides) -> Book:
    count = session.query(Book).count() + 1
    data = {
        "title": f"Eval Book {count:02d}",
        "author": "Author X",
        "isbn": f"978100000{count:04d}",
        "genre": "Fiction",
        "description": "Evaluation novel test description",
        "page_count": 200,
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
    session: Session, user_id: int, book_id: int, status: str = FINISHED, percent: float = 100.0
) -> ReadingRecordRow:
    row = ReadingRecordRow(
        user_id=user_id,
        book_id=book_id,
        status=status,
        current_page=int(percent),
        percent=percent,
    )
    session.add(row)
    session.commit()
    return row


# ==============================================================================
# Metric Computation Unit Tests (Precision@K, Recall@K, F1@K)
# ==============================================================================


def test_precision_at_k_basic():
    """Precision@K computes proportion of top-K recommendations in ground truth."""
    # 2 hits out of 5 -> 0.4
    assert precision_at_k([1, 2, 3, 4, 5], {2, 4, 9}, k=5) == 0.4
    # 1 hit out of 2 -> 0.5
    assert precision_at_k([1, 2, 3, 4, 5], {2, 4, 9}, k=2) == 0.5
    # 0 hits
    assert precision_at_k([1, 3, 5], {2, 4}, k=3) == 0.0


def test_precision_at_k_edge_cases():
    """Precision@K handles empty lists, negative or zero k."""
    assert precision_at_k([], {1, 2}, k=5) == 0.0
    assert precision_at_k([1, 2], set(), k=5) == 0.0
    assert precision_at_k([1, 2], {1}, k=0) == 0.0
    assert precision_at_k([1, 2], {1}, k=-3) == 0.0


def test_recall_at_k_basic():
    """Recall@K computes proportion of ground truth recovered in top-K."""
    # 2 hits out of 3 ground truth -> 0.6667
    assert recall_at_k([1, 2, 3, 4, 5], {2, 4, 9}, k=5) == 0.6667
    # 1 hit out of 3 ground truth -> 0.3333
    assert recall_at_k([1, 2, 3, 4, 5], {2, 4, 9}, k=2) == 0.3333
    # 3 hits out of 3 ground truth -> 1.0
    assert recall_at_k([2, 4, 9, 1], {2, 4, 9}, k=3) == 1.0


def test_recall_at_k_edge_cases():
    """Recall@K handles empty lists, empty ground truth, and non-positive k."""
    assert recall_at_k([], {1, 2}, k=5) == 0.0
    assert recall_at_k([1, 2], set(), k=5) == 0.0
    assert recall_at_k([1, 2], {1}, k=0) == 0.0
    assert recall_at_k([1, 2], {1}, k=-2) == 0.0


def test_f1_at_k():
    """F1@K computes harmonic mean of precision and recall."""
    assert f1_at_k(0.5, 0.5) == 0.5
    assert f1_at_k(0.0, 0.0) == 0.0
    assert f1_at_k(0.4, 0.6667) == 0.5


# ==============================================================================
# Train / Test Holdout Split Tests
# ==============================================================================


def test_split_user_history():
    """split_user_history splits history into train and holdout test set."""
    records = [{"id": i} for i in range(10)]
    train, test = split_user_history(records, holdout_ratio=0.2, min_records=3)
    assert len(train) == 8
    assert len(test) == 2
    assert train == records[:8]
    assert test == records[8:]


def test_split_user_history_few_records():
    """split_user_history returns empty test set if records < min_records."""
    records = [{"id": 1}, {"id": 2}]
    train, test = split_user_history(records, min_records=3)
    assert train == records
    assert test == []


# ==============================================================================
# Multi-Algorithm Evaluation & Comparison Tests
# ==============================================================================


def test_evaluate_recommender(session):
    """evaluate_recommender computes macro-averaged metrics across users."""
    b1 = _add_book(session, title="Book 1")
    b2 = _add_book(session, title="Book 2")
    b3 = _add_book(session, title="Book 3")

    # Recommender always returns [b1, b2, b3] for cold-start
    recommender = PopularityRecommender(db=session)

    test_set = {
        101: {b1.id, b2.id},  # 2 hits out of 3
        102: {b3.id},        # 1 hit out of 3
    }

    metrics = evaluate_recommender(recommender, test_set=test_set, k=3, db=session)
    assert metrics["users_evaluated"] == 2
    # User 101: p@3 = 2/3 (0.6667), r@3 = 2/2 (1.0)
    # User 102: p@3 = 1/3 (0.3333), r@3 = 1/1 (1.0)
    # Mean P@3: (0.6667 + 0.3333)/2 = 0.50
    # Mean R@3: (1.0 + 1.0)/2 = 1.0
    assert metrics["precision@3"] == 0.50
    assert metrics["recall@3"] == 1.0
    assert metrics["f1@3"] > 0


def test_evaluate_recommender_empty_test_set():
    """evaluate_recommender handles empty test set safely."""
    recommender = PopularityRecommender()
    metrics = evaluate_recommender(recommender, test_set={}, k=5)
    assert metrics["users_evaluated"] == 0
    assert metrics["precision@5"] == 0.0


def test_compare_recommenders_and_markdown_formatting(session):
    """compare_recommenders benchmarks multiple algorithms and formats markdown table."""
    b1 = _add_book(session, title="Sci-Fi A", genre="Sci-Fi", description="Space interstellar")
    b2 = _add_book(session, title="Sci-Fi B", genre="Sci-Fi", description="Space galaxy")
    _add_book(session, title="Romance A", genre="Romance", description="Love estate")

    test_set = {
        201: {b1.id, b2.id},
    }

    recommenders = {
        "Popularity Baseline": PopularityRecommender(db=session),
        "Content-Based": ContentBasedRecommender(db=session),
        "Hybrid": HybridRecommender(alpha=0.7, db=session),
    }

    results = compare_recommenders(recommenders, test_set=test_set, k_list=[2], db=session)
    assert len(results) == 3
    assert "Popularity Baseline" in results
    assert "Content-Based" in results
    assert "Hybrid" in results

    table_md = format_evaluation_markdown(results, k_list=[2])
    assert "| Algorithm |" in table_md
    assert "Precision@2" in table_md
    assert "Recall@2" in table_md
    assert "Popularity Baseline" in table_md


# ==============================================================================
# Hybrid Recommender Specific Tests (FR-R5, NFR-R2)
# ==============================================================================


def test_hybrid_recommender_interface():
    """NFR-R2: HybridRecommender implements the common Recommender interface."""
    hybrid = HybridRecommender()
    assert isinstance(hybrid, Recommender)


def test_hybrid_recommender_invalid_alpha():
    """HybridRecommender raises ValueError for alpha outside [0, 1]."""
    with pytest.raises(ValueError, match="alpha must be between 0.0 and 1.0"):
        HybridRecommender(alpha=-0.1)

    with pytest.raises(ValueError, match="alpha must be between 0.0 and 1.0"):
        HybridRecommender(alpha=1.5)


def test_hybrid_recommender_empty_catalog(session):
    """HybridRecommender returns empty list when catalog is empty."""
    hybrid = HybridRecommender(db=session)
    assert hybrid.recommend(user_id=1, n=5) == []


def test_hybrid_recommender_negative_or_zero_n(session):
    """HybridRecommender returns empty list for n <= 0."""
    _add_book(session, title="Book A")
    hybrid = HybridRecommender(db=session)
    assert hybrid.recommend(user_id=1, n=0) == []
    assert hybrid.recommend(user_id=1, n=-2) == []


def test_hybrid_recommender_cold_start_fallback(session):
    """FR-R3: Cold-start user falls back to popularity recommendations."""
    b1 = _add_book(session, title="Popular One", genre="Fiction")
    b2 = _add_book(session, title="Popular Two", genre="Fiction")

    # User 999 has no reading records
    hybrid = HybridRecommender(db=session)
    recs = hybrid.recommend(user_id=999, n=5)
    assert len(recs) == 2
    assert [r.book_id for r in recs] == [b1.id, b2.id]
    assert "Popular" in recs[0].reason


def test_hybrid_recommender_blended_scoring_and_ranking(session):
    """FR-R5: Hybrid blends content similarity with reader popularity."""
    # Seed books
    b_sci1 = _add_book(
        session, title="Deep Space One", genre="Sci-Fi", description="Spaceship galaxy"
    )
    b_sci2 = _add_book(
        session, title="Deep Space Two", genre="Sci-Fi", description="Spaceship stars"
    )
    b_rom1 = _add_book(session, title="Sweet Love", genre="Romance", description="Romance wedding")

    # Romance book has many library readers (high popularity)
    for u in range(10, 20):
        _add_record(session, user_id=u, book_id=b_rom1.id)

    # User 50 finished b_sci1 (strong content affinity for Sci-Fi)
    _add_record(session, user_id=50, book_id=b_sci1.id, status=FINISHED)

    hybrid = HybridRecommender(alpha=0.7, db=session)
    recs = hybrid.recommend(user_id=50, n=2)

    assert len(recs) == 2
    # Finished b_sci1 excluded (FR-R4)
    rec_bids = [r.book_id for r in recs]
    assert b_sci1.id not in rec_bids
    assert b_sci2.id in rec_bids
    # Scores are valid floats and sorted descending
    assert recs[0].score >= recs[1].score
    assert all(r.score > 0 for r in recs)


def test_hybrid_recommender_excludes_deleted_books(session):
    """FR-R4: Soft-deleted books are excluded from hybrid recommendations."""
    b1 = _add_book(session, title="Active Book", genre="Tech", description="Programming")
    b2 = _add_book(
        session, title="Deleted Book", genre="Tech", description="Programming", is_deleted=True
    )

    _add_record(session, user_id=60, book_id=b1.id, status=FINISHED)

    hybrid = HybridRecommender(db=session)
    recs = hybrid.recommend(user_id=60, n=10)
    assert b2.id not in [r.book_id for r in recs]
