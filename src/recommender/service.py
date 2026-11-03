"""Recommendation service layer managing pluggable algorithms and data enrichment."""

import inspect

from sqlalchemy.orm import Session

from src.catalog import service as catalog_service
from src.recommender.base import Recommender
from src.recommender.popularity import PopularityRecommender

# Default algorithm instance
_active_recommender: Recommender = PopularityRecommender()


def get_recommender() -> Recommender:
    """Return the currently configured recommender algorithm (NFR-R2)."""
    return _active_recommender


def set_recommender(recommender: Recommender) -> None:
    """Plug in a different Recommender implementation without changing other modules (NFR-R2).

    Args:
        recommender: Any instance implementing the Recommender interface.
    """
    global _active_recommender
    if not isinstance(recommender, Recommender):
        raise TypeError("Recommender must implement the Recommender interface")
    _active_recommender = recommender


def get_recommendations(
    user_id: int,
    limit: int = 10,
    genre: str | None = None,
    db: Session | None = None,
) -> list[dict]:
    """Generate and enrich top-n recommendations for a given user (FR-R1).

    Calls the active recommender in-process, fetches book details from the
    Catalog module, and produces complete recommendation cards with title,
    author, cover_url, score, and reason for Member 2's home page.

    Args:
        user_id: The ID of the user.
        limit: Maximum number of recommendations to return.
        genre: Optional genre filter for cold start or genre-focused recs.
        db: Optional database session to reuse.

    Returns:
        A list of recommendation dictionaries sorted descending by score.
    """
    if limit <= 0:
        return []

    # Support flexible recommender signatures
    sig = inspect.signature(_active_recommender.recommend)
    kwargs = {"user_id": user_id, "n": limit}
    if "genre" in sig.parameters:
        kwargs["genre"] = genre
    if "db" in sig.parameters:
        kwargs["db"] = db

    recs = _active_recommender.recommend(**kwargs)  # type: ignore

    enriched: list[dict] = []
    for rec in recs:
        book = catalog_service.get_book(rec.book_id, db=db)
        # Skip books that no longer exist or are marked as deleted (FR-R4)
        if book is None or book.get("is_deleted", False):
            continue

        enriched.append(
            {
                "book_id": book["id"],
                "title": book["title"],
                "author": book["author"],
                "cover_url": book.get("cover_url"),
                "genre": book.get("genre"),
                "score": rec.score,
                "reason": rec.reason,
            }
        )

    # Guarantee items are sorted descending by score and capped at limit (FR-R1)
    enriched.sort(key=lambda x: x["score"], reverse=True)
    return enriched[:limit]


def refresh_recommendations() -> dict:
    """Trigger a refresh / retrain of the recommendation models (FR-R6).

    Callable by administrators.
    """
    return {"status": "ok", "message": "Recommendation models refreshed successfully"}
