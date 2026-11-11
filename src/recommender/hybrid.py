"""Hybrid recommendation engine combining content-based TF-IDF and popularity (FR-R5, NFR-R2)."""

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.catalog import service as catalog_service
from src.recommender.base import Recommendation, Recommender
from src.recommender.content_based import ContentBasedRecommender
from src.recommender.popularity import PopularityRecommender
from src.users import reading as reading_service
from src.users.models import FINISHED, ReadingRecordRow


class HybridRecommender(Recommender):
    """Hybrid recommender blending content-based TF-IDF similarity with popularity baseline.

    - Formula (FR-R5):
        score = alpha * content_score + (1 - alpha) * popularity_score
      Default alpha = 0.7 (70% content similarity, 30% library reader popularity).
    - Cold-start fallback (FR-R3): users with zero reading history smoothly fall back
      to popularity recommendations.
    - Exclusions (FR-R4): finished books and soft-deleted books are never recommended.
    - Explanations (FR-R5): human-readable explanations based on genre interest and popularity.
    - Model rebuilding (FR-R6): fit() rebuilds underlying models.
    """

    def __init__(self, alpha: float = 0.7, db: Session | None = None):
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("alpha must be between 0.0 and 1.0")
        self.alpha = alpha
        self.db = db
        self.content_recommender = ContentBasedRecommender(db=db)
        self.popularity_recommender = PopularityRecommender(db=db)

    def fit(self, db: Session | None = None) -> None:
        """Precompute and cache model representations (FR-R6)."""
        active_db = db if db is not None else self.db
        self.content_recommender.fit(db=active_db)

    def recommend(
        self,
        user_id: int,
        n: int = 10,
        genre: str | None = None,
        db: Session | None = None,
    ) -> list[Recommendation]:
        """Generate top-n hybrid recommendations for a given user.

        Args:
            user_id: ID of the user requesting recommendations.
            n: Number of recommendations to return.
            genre: Optional genre filter.
            db: Optional database session to reuse.

        Returns:
            A list of Recommendation objects ranked by blended score.
        """
        if n <= 0:
            return []

        active_db = db if db is not None else self.db

        # 1. Fetch user reading history
        user_history = []
        try:
            user_history = reading_service.get_history(user_id, db=active_db)
        except Exception:
            pass

        # Cold-start fallback if user has no reading history (FR-R3)
        if not user_history:
            return self.popularity_recommender.recommend(
                user_id=user_id, n=n, genre=genre, db=active_db
            )

        finished_book_ids: set[int] = {
            rec.book_id
            for rec in user_history
            if rec.status == FINISHED or rec.status == "finished"
        }

        # 2. Retrieve catalog books
        catalog_res = catalog_service.get_books(
            genre=genre,
            page=1,
            page_size=None,
            db=active_db,
        )
        catalog_books = catalog_res.get("items", [])

        # Filter out finished and deleted books (FR-R4)
        candidates = [
            b
            for b in catalog_books
            if b["id"] not in finished_book_ids and not b.get("is_deleted", False)
        ]
        if not candidates:
            return []

        # 3. Retrieve reader counts for popularity component
        reader_counts: dict[int, int] = {}
        if active_db is not None:
            try:
                stmt = (
                    select(
                        ReadingRecordRow.book_id,
                        func.count(ReadingRecordRow.user_id).label("cnt"),
                    )
                    .group_by(ReadingRecordRow.book_id)
                    .order_by(desc("cnt"))
                )
                for bid, cnt in active_db.execute(stmt):
                    reader_counts[bid] = cnt
            except Exception:
                pass

        max_readers = max(reader_counts.values()) if reader_counts else 0

        # 4. Compute content-based scores
        content_recs = self.content_recommender.recommend(
            user_id=user_id,
            n=len(candidates),
            genre=genre,
            db=active_db,
        )
        content_scores: dict[int, float] = {r.book_id: r.score for r in content_recs}
        content_reasons: dict[int, str] = {r.book_id: r.reason for r in content_recs}

        # 5. Blend scores
        scored_candidates: list[tuple[float, dict, str]] = []
        for book in candidates:
            bid = book["id"]
            c_score = content_scores.get(bid, 0.0)

            # Popularity score normalized to [0.0, 1.0]
            cnt = reader_counts.get(bid, 0)
            p_score = (cnt / max_readers) if max_readers > 0 else 0.50

            # Linear hybrid combination (FR-R5)
            hybrid_score = round(self.alpha * c_score + (1.0 - self.alpha) * p_score, 4)

            # Informative reason
            if c_score > 0.01 and bid in content_reasons:
                reason = content_reasons[bid]
            elif genre:
                reason = f"Popular in {genre}"
            elif cnt > 0:
                reason = f"Popular among library readers ({cnt} readers)"
            else:
                reason = "Popular among library readers"

            scored_candidates.append((hybrid_score, book, reason))

        def sort_key(item: tuple[float, dict, str]):
            score_val, b, _ = item
            bid = b["id"]
            return (-score_val, -reader_counts.get(bid, 0), bid)

        scored_candidates.sort(key=sort_key)
        top_candidates = scored_candidates[:n]

        # 6. Format recommendations
        return [
            Recommendation(
                book_id=b["id"],
                score=score_val,
                reason=reason_val,
            )
            for score_val, b, reason_val in top_candidates
        ]
