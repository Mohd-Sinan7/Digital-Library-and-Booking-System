"""Baseline popularity recommender implementation."""

from sqlalchemy.orm import Session

from src.catalog import service as catalog_service
from src.recommender.base import Recommendation, Recommender


class PopularityRecommender(Recommender):
    """Baseline recommender ranking books by popularity / catalog order.

    Serves as the default cold-start and baseline algorithm (FR-R3).
    """

    def __init__(self, db: Session | None = None):
        self.db = db

    def recommend(
        self, user_id: int, n: int = 10, db: Session | None = None
    ) -> list[Recommendation]:
        """Return top-n books based on catalog order as baseline recommendations."""
        if n <= 0:
            return []

        active_db = db if db is not None else self.db
        catalog_result = catalog_service.get_books(page=1, page_size=n, db=active_db)
        books = catalog_result.get("items", [])[:n]

        recommendations: list[Recommendation] = []
        for rank, book in enumerate(books):
            # Baseline score scaled from 1.0 downwards
            score = max(0.1, round(1.0 - (rank * 0.05), 2))
            recommendations.append(
                Recommendation(
                    book_id=book["id"],
                    score=score,
                    reason="Popular among library readers",
                )
            )
        return recommendations
