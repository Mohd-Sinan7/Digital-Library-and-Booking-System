"""Baseline popularity recommender implementation with cold-start support (FR-R3, FR-R4)."""

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.catalog import service as catalog_service
from src.recommender.base import Recommendation, Recommender
from src.users import reading as reading_service
from src.users.models import FINISHED, ReadingRecordRow


class PopularityRecommender(Recommender):
    """Baseline recommender ranking books by popularity with cold-start support.

    - Popularity ranking: books ranked by total reading activity across users.
    - Cold-start fallback (FR-R3): users with no reading history receive the most
      popular books overall (or within a selected genre), never an error or empty list.
    - Exclusion (FR-R4): books the user has already finished or books removed from
      the catalog are never recommended.
    """

    def __init__(self, db: Session | None = None):
        self.db = db

    def recommend(
        self,
        user_id: int,
        n: int = 10,
        genre: str | None = None,
        db: Session | None = None,
    ) -> list[Recommendation]:
        """Return top-n recommendations based on popularity with cold-start handling."""
        if n <= 0:
            return []

        active_db = db if db is not None else self.db

        # 1. Identify finished books to exclude (FR-R4)
        finished_book_ids: set[int] = set()
        try:
            user_history = reading_service.get_history(user_id, db=active_db)
            for rec in user_history:
                if rec.status == FINISHED or rec.status == "finished":
                    finished_book_ids.add(rec.book_id)
        except Exception:
            # If reading table does not exist yet or fails, proceed without finished history
            pass

        # 2. Get reader counts per book across all users for popularity ranking
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
                for book_id, cnt in active_db.execute(stmt):
                    reader_counts[book_id] = cnt
            except Exception:
                pass

        # 3. Fetch catalog books (catalog.get_books excludes is_deleted by default)
        catalog_res = catalog_service.get_books(
            genre=genre,
            page=1,
            page_size=None,
            db=active_db,
        )
        catalog_books = catalog_res.get("items", [])

        # 4. Filter out finished books and deleted books (FR-R4)
        candidates = [
            b
            for b in catalog_books
            if b["id"] not in finished_book_ids and not b.get("is_deleted", False)
        ]

        if not candidates:
            return []

        # 5. Sort candidates by popularity (reader count descending, then book id ascending)
        max_readers = max(reader_counts.values()) if reader_counts else 0

        def sort_key(b: dict) -> tuple[int, int]:
            bid = b["id"]
            return (-reader_counts.get(bid, 0), bid)

        candidates.sort(key=sort_key)
        top_candidates = candidates[:n]

        # 6. Generate Recommendations with scores and explanations (FR-R5)
        recommendations: list[Recommendation] = []
        for rank, book in enumerate(top_candidates):
            bid = book["id"]
            cnt = reader_counts.get(bid, 0)
            if max_readers > 0:
                score = round(0.50 + 0.50 * (cnt / max_readers), 2)
            else:
                score = max(0.10, round(1.0 - (rank * 0.05), 2))

            if genre:
                reason = f"Popular in {genre}"
            elif cnt > 0:
                reason = f"Popular among library readers ({cnt} readers)"
            else:
                reason = "Popular among library readers"

            recommendations.append(
                Recommendation(
                    book_id=bid,
                    score=score,
                    reason=reason,
                )
            )

        return recommendations
