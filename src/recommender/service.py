"""Recommendation service layer managing pluggable algorithms, caching, and data enrichment."""

import inspect

from sqlalchemy.orm import Session

from src.catalog import service as catalog_service
from src.recommender.base import Recommender
from src.recommender.cache import recommendation_cache
from src.recommender.content_based import ContentBasedRecommender
from src.recommender.scoring import ensure_reason  # FR-R5 safety contract

# Default algorithm instance for Sprint 2 (FR-R2)
_active_recommender: Recommender = ContentBasedRecommender()


def get_recommender() -> Recommender:
    """Return the currently configured recommender algorithm (NFR-R2)."""
    return _active_recommender


def set_recommender(recommender: Recommender) -> None:
    """Plug in a different Recommender implementation without changing other modules (NFR-R2).

    Also clears the recommendation cache to avoid serving stale outputs from a previous model.

    Args:
        recommender: Any instance implementing the Recommender interface.
    """
    global _active_recommender
    if not isinstance(recommender, Recommender):
        raise TypeError("Recommender must implement the Recommender interface")
    _active_recommender = recommender
    recommendation_cache.clear()


def get_recommendations(
    user_id: int,
    limit: int = 10,
    genre: str | None = None,
    db: Session | None = None,
    use_cache: bool = True,
) -> list[dict]:
    """Generate and enrich top-n recommendations for a given user (FR-R1, FR-R2, NFR-R1).

    Calls the active recommender in-process, fetches book details from the
    Catalog module, and produces complete recommendation cards with title,
    author, cover_url, score, and reason for Member 2's home page.

    Results are cached in-memory for sub-millisecond retrieval (NFR-R1).
    Every item is guaranteed to carry a non-empty reason via ensure_reason()
    before enrichment (FR-R5).

    Args:
        user_id: The ID of the user.
        limit: Maximum number of recommendations to return.
        genre: Optional genre filter for cold start or genre-focused recs.
        db: Optional database session to reuse.
        use_cache: Whether to check and populate the in-memory cache (default True).

    Returns:
        A list of recommendation dictionaries sorted descending by score.
    """
    if limit <= 0:
        return []

    # Check cache first for sub-millisecond response (NFR-R1)
    if use_cache:
        cached = recommendation_cache.get(user_id=user_id, limit=limit, genre=genre)
        if cached is not None:
            return cached

    # Support flexible recommender signatures
    sig = inspect.signature(_active_recommender.recommend)
    kwargs = {"user_id": user_id, "n": limit}
    if "genre" in sig.parameters:
        kwargs["genre"] = genre
    if "db" in sig.parameters:
        kwargs["db"] = db

    recs = _active_recommender.recommend(**kwargs)  # type: ignore

    # FR-R5: enforce non-empty reason on every item before enrichment
    recs = ensure_reason(recs)

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
    result = enriched[:limit]

    # Store in cache
    if use_cache:
        recommendation_cache.set(user_id=user_id, limit=limit, genre=genre, value=result)

    return result


def refresh_recommendations(db: Session | None = None) -> dict:
    """Trigger a refresh / retrain of the recommendation models and clear cache (FR-R6).

    - Clears all cached recommendation responses.
    - Rebuilds model precomputations (TF-IDF vectorizer/catalog matrices) if supported.
    - Callable by administrators.

    Args:
        db: Optional database session to rebuild catalog representations from.

    Returns:
        A status dictionary confirming completion and eviction details.
    """
    cleared = recommendation_cache.clear()

    model_rebuilt = False
    active = _active_recommender
    if hasattr(active, "fit"):
        try:
            if db is not None:
                active.fit(db=db)
                model_rebuilt = True
            else:
                from src.db import SessionLocal

                with SessionLocal() as s:
                    active.fit(db=s)
                    model_rebuilt = True
        except Exception:
            pass

    return {
        "status": "ok",
        "message": "Recommendation models refreshed successfully",
        "cached_entries_cleared": cleared,
        "model_rebuilt": model_rebuilt,
    }
