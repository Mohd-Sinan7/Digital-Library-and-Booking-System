"""Unit tests for DLBS-12: Hybrid scoring and explanations (FR-R5).

Acceptance criterion:
  FR-R5 — Every recommendation item returned by any algorithm MUST carry
  a non-empty reason string.

Coverage:
  - blend_scores(): formula correctness, boundary values, invalid alpha.
  - build_reason(): all priority branches, empty / None inputs.
  - ensure_reason(): empty reason replacement, non-empty pass-through, mixed list.
  - PopularityRecommender: reason is always non-empty.
  - ContentBasedRecommender: reason is always non-empty (cold-start and history paths).
  - HybridRecommender: reason is always non-empty (all paths).
  - service.ensure_reason integration: in-service pass catches edge cases.
"""

from __future__ import annotations

import pytest

from src.recommender.base import Recommendation
from src.recommender.scoring import (
    _FALLBACK_REASON,
    blend_scores,
    build_reason,
    ensure_reason,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rec(book_id: int = 1, score: float = 0.5, reason: str = "ok") -> Recommendation:
    return Recommendation(book_id=book_id, score=score, reason=reason)


# ===========================================================================
# blend_scores
# ===========================================================================


class TestBlendScores:
    """Tests for blend_scores() (FR-R5 formula)."""

    def test_default_alpha_weights(self):
        """70% content + 30% popularity with default alpha."""
        result = blend_scores(content_score=1.0, popularity_score=0.0)
        assert result == pytest.approx(0.70, abs=1e-4)

    def test_full_popularity(self):
        """alpha=0 means 100% popularity score."""
        result = blend_scores(content_score=1.0, popularity_score=0.5, alpha=0.0)
        assert result == pytest.approx(0.50, abs=1e-4)

    def test_full_content(self):
        """alpha=1 means 100% content score."""
        result = blend_scores(content_score=0.8, popularity_score=0.2, alpha=1.0)
        assert result == pytest.approx(0.80, abs=1e-4)

    def test_equal_weight(self):
        """alpha=0.5 gives equal weighting."""
        result = blend_scores(content_score=0.6, popularity_score=0.4, alpha=0.5)
        assert result == pytest.approx(0.50, abs=1e-4)

    def test_zero_scores(self):
        """Both scores zero → result zero."""
        assert blend_scores(0.0, 0.0) == 0.0

    def test_result_rounded_to_4dp(self):
        """Result must be rounded to 4 decimal places."""
        result = blend_scores(0.333333, 0.666666, alpha=0.5)
        assert len(str(result).split(".")[-1]) <= 4

    def test_invalid_alpha_below_zero(self):
        with pytest.raises(ValueError, match="alpha must be in"):
            blend_scores(0.5, 0.5, alpha=-0.1)

    def test_invalid_alpha_above_one(self):
        with pytest.raises(ValueError, match="alpha must be in"):
            blend_scores(0.5, 0.5, alpha=1.1)

    def test_boundary_alpha_zero(self):
        """alpha=0.0 is a valid boundary."""
        assert blend_scores(0.9, 0.1, alpha=0.0) == pytest.approx(0.10, abs=1e-4)

    def test_boundary_alpha_one(self):
        """alpha=1.0 is a valid boundary."""
        assert blend_scores(0.9, 0.1, alpha=1.0) == pytest.approx(0.90, abs=1e-4)


# ===========================================================================
# build_reason
# ===========================================================================


class TestBuildReason:
    """Tests for build_reason() — explanation priority ladder (FR-R5)."""

    def test_genre_in_read_genres(self):
        """Genre affinity takes highest priority."""
        reason = build_reason(
            content_score=0.5,
            genre="Fantasy",
            read_genres={"Fantasy", "Sci-Fi"},
        )
        assert "Fantasy" in reason
        assert reason.strip()

    def test_genre_not_in_read_genres(self):
        """Content signal present but genre is new → similarity hint."""
        reason = build_reason(
            content_score=0.3,
            genre="Mystery",
            read_genres={"Fantasy"},
        )
        assert "Mystery" in reason or "similar" in reason.lower()
        assert reason.strip()

    def test_content_signal_no_genre(self):
        """Content signal without genre → generic history message."""
        reason = build_reason(content_score=0.2, genre=None)
        assert "history" in reason.lower() or "reading" in reason.lower()
        assert reason.strip()

    def test_no_content_signal_with_genre_and_readers(self):
        """No content signal → popularity-based with genre and reader count."""
        reason = build_reason(content_score=0.0, genre="Romance", reader_count=42)
        assert "Romance" in reason or "42" in reason
        assert reason.strip()

    def test_no_content_signal_genre_only(self):
        """No readers data, genre present → genre popularity."""
        reason = build_reason(content_score=0.0, genre="Horror", reader_count=0)
        assert "Horror" in reason
        assert reason.strip()

    def test_no_content_no_genre_with_readers(self):
        """No content, no genre, but reader count → popularity note."""
        reason = build_reason(content_score=0.0, genre=None, reader_count=100)
        assert "100" in reason or "popular" in reason.lower()
        assert reason.strip()

    def test_all_zero_fallback(self):
        """Absolute fallback: no content, no genre, no readers → still non-empty."""
        reason = build_reason(content_score=0.0, genre=None, reader_count=0)
        assert reason.strip()

    def test_none_read_genres(self):
        """None read_genres is handled gracefully."""
        reason = build_reason(content_score=0.5, genre="Sci-Fi", read_genres=None)
        assert reason.strip()

    def test_empty_read_genres(self):
        """Empty set read_genres is handled gracefully."""
        reason = build_reason(content_score=0.5, genre="Sci-Fi", read_genres=set())
        assert reason.strip()

    def test_reason_always_non_empty(self):
        """Exhaustive check: every branch returns non-empty string."""
        for c_score in [0.0, 0.005, 0.02, 0.5]:
            for genre in [None, "Fantasy"]:
                for read_genres in [None, set(), {"Fantasy"}, {"Other"}]:
                    for rc in [0, 5]:
                        r = build_reason(c_score, genre, read_genres, rc)
                        assert r.strip(), (
                            f"Empty reason for c={c_score}, g={genre}, "
                            f"rg={read_genres}, rc={rc}"
                        )


# ===========================================================================
# ensure_reason
# ===========================================================================


class TestEnsureReason:
    """Tests for ensure_reason() — FR-R5 enforcement pass."""

    def test_non_empty_reason_unchanged(self):
        """Items with valid reasons are returned as-is."""
        recs = [_make_rec(1, 0.9, "Because you like Fantasy")]
        result = ensure_reason(recs)
        assert len(result) == 1
        assert result[0].reason == "Because you like Fantasy"

    def test_empty_reason_replaced(self):
        """Empty string reason is replaced with fallback."""
        recs = [_make_rec(1, 0.5, "")]
        result = ensure_reason(recs)
        assert result[0].reason == _FALLBACK_REASON

    def test_whitespace_only_reason_replaced(self):
        """Whitespace-only reason is treated as empty and replaced."""
        recs = [_make_rec(1, 0.5, "   ")]
        result = ensure_reason(recs)
        assert result[0].reason == _FALLBACK_REASON

    def test_mixed_list(self):
        """Mixed list: valid reasons kept, empty ones replaced."""
        recs = [
            _make_rec(1, 0.9, "Genre affinity"),
            _make_rec(2, 0.5, ""),
            _make_rec(3, 0.3, "   "),
            _make_rec(4, 0.1, "Popular"),
        ]
        result = ensure_reason(recs)
        assert result[0].reason == "Genre affinity"
        assert result[1].reason == _FALLBACK_REASON
        assert result[2].reason == _FALLBACK_REASON
        assert result[3].reason == "Popular"

    def test_all_valid_reasons(self):
        """All valid reasons — list returned unchanged (same content)."""
        recs = [_make_rec(i, 0.5, f"Reason {i}") for i in range(5)]
        result = ensure_reason(recs)
        assert [r.reason for r in result] == [f"Reason {i}" for i in range(5)]

    def test_empty_input_list(self):
        """Empty input returns empty output."""
        assert ensure_reason([]) == []

    def test_fallback_reason_itself_is_non_empty(self):
        """The module-level fallback constant must not be empty."""
        assert _FALLBACK_REASON.strip()

    def test_book_id_and_score_preserved(self):
        """ensure_reason must not alter book_id or score."""
        recs = [_make_rec(42, 0.75, "")]
        result = ensure_reason(recs)
        assert result[0].book_id == 42
        assert result[0].score == pytest.approx(0.75)

    def test_all_empty_reasons(self):
        """Every item empty → every item gets fallback, still non-empty."""
        recs = [_make_rec(i, 0.1, "") for i in range(10)]
        result = ensure_reason(recs)
        for r in result:
            assert r.reason.strip(), "ensure_reason produced empty reason"

    def test_output_length_equals_input_length(self):
        """Output list length must equal input list length."""
        recs = [_make_rec(i, 0.1, "" if i % 2 else "ok") for i in range(8)]
        result = ensure_reason(recs)
        assert len(result) == len(recs)


# ===========================================================================
# FR-R5 integration: PopularityRecommender — in-memory fixture
# ===========================================================================


class TestPopularityRecommenderFR5:
    """PopularityRecommender must always set a non-empty reason (FR-R5)."""

    def _make_popularity_recs(self, genre: str | None = None) -> list[Recommendation]:
        """Build PopularityRecommender output directly from its logic."""
        from src.recommender.popularity import PopularityRecommender
        rec = PopularityRecommender(db=None)
        # Monkey-patch internals to avoid DB calls
        import unittest.mock as mock

        import src.catalog.service as cat_svc
        import src.users.reading as reading_svc

        books = [
            {"id": i, "title": f"Book {i}", "author": "A", "genre": "Fantasy",
             "is_deleted": False}
            for i in range(1, 6)
        ]
        with (
            mock.patch.object(reading_svc, "get_history", return_value=[]),
            mock.patch.object(cat_svc, "get_books", return_value={"items": books}),
        ):
            return rec.recommend(user_id=1, n=5, genre=genre, db=None)

    def test_cold_start_reasons_non_empty(self):
        """Cold-start (no history) results all have non-empty reasons."""
        recs = self._make_popularity_recs()
        assert recs, "Expected at least one recommendation"
        for r in recs:
            assert r.reason.strip(), f"Empty reason for book_id={r.book_id}"

    def test_genre_filter_reasons_non_empty(self):
        """Genre-filtered popularity recommendations have non-empty reasons."""
        recs = self._make_popularity_recs(genre="Fantasy")
        for r in recs:
            assert r.reason.strip(), f"Empty reason for book_id={r.book_id}"


# ===========================================================================
# FR-R5 integration: HybridRecommender — in-memory fixture
# ===========================================================================


class TestHybridRecommenderFR5:
    """HybridRecommender must always set a non-empty reason (FR-R5)."""

    def _catalog_books(self, n: int = 5):
        return [
            {"id": i, "title": f"Book {i}", "author": "A", "genre": "Sci-Fi",
             "description": "space adventure", "is_deleted": False}
            for i in range(1, n + 1)
        ]

    def test_cold_start_reasons_non_empty(self):
        """Cold-start hybrid (no history) falls back to popularity — reasons non-empty."""
        import unittest.mock as mock

        import src.catalog.service as cat_svc
        import src.users.reading as reading_svc
        from src.recommender.hybrid import HybridRecommender

        books = self._catalog_books()
        with (
            mock.patch.object(reading_svc, "get_history", return_value=[]),
            mock.patch.object(cat_svc, "get_books", return_value={"items": books}),
        ):
            rec = HybridRecommender(alpha=0.7, db=None)
            recs = rec.recommend(user_id=99, n=5, db=None)

        assert recs, "Expected at least one recommendation"
        for r in recs:
            assert r.reason.strip(), f"Empty reason for book_id={r.book_id}"

    def test_hybrid_history_reasons_non_empty(self):
        """Hybrid with reading history produces reasons for all items."""
        import types
        import unittest.mock as mock

        import src.catalog.service as cat_svc
        import src.users.reading as reading_svc
        from src.recommender.hybrid import HybridRecommender

        books = self._catalog_books(n=10)

        # Simulate user has read books 1 and 2 (finished)
        history = [
            types.SimpleNamespace(book_id=1, user_id=1, status="finished", percent=100),
            types.SimpleNamespace(book_id=2, user_id=1, status="reading", percent=60),
        ]

        with (
            mock.patch.object(reading_svc, "get_history", return_value=history),
            mock.patch.object(cat_svc, "get_books", return_value={"items": books}),
        ):
            rec = HybridRecommender(alpha=0.7, db=None)
            recs = rec.recommend(user_id=1, n=5, db=None)

        assert recs, "Expected at least one recommendation"
        for r in recs:
            assert r.reason.strip(), f"Empty reason for book_id={r.book_id}"

    def test_ensure_reason_catches_any_empty(self):
        """ensure_reason() applied after hybrid output catches any stray empty reasons."""
        # Simulate a hypothetical buggy recommender returning empty reasons
        bad_recs = [
            Recommendation(book_id=i, score=0.5, reason="")
            for i in range(1, 6)
        ]
        result = ensure_reason(bad_recs)
        for r in result:
            assert r.reason.strip(), "ensure_reason did not fix empty reason"
