"""REST endpoints for the Recommendation Engine (FR-R1, FR-R6, NFR-R1)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.db import SessionLocal
from src.recommender import service
from src.users.auth import CurrentUser, get_current_user, require_admin

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


def get_db():
    """Dependency yielding a database session."""
    with SessionLocal() as db:
        yield db


@router.get("/me")
def get_my_recommendations(
    limit: int = Query(10, ge=1, le=50),
    genre: str | None = Query(None),
    nocache: bool = Query(False),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return top-N personalized or cold-start recommendations for the logged-in user (FR-R1).

    Returns at most `limit` items sorted by score descending, where each item holds:
    book_id, title, author, cover_url, score, and reason.
    Requires authentication (Bearer token). No token returns 401.
    """
    items = service.get_recommendations(
        user_id=user.id,
        limit=limit,
        genre=genre,
        db=db,
        use_cache=not nocache,
    )
    return {"items": items, "count": len(items)}


@router.post("/refresh")
def refresh_models(
    user: CurrentUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Trigger a refresh or retrain of the recommendation models (FR-R6).

    Administrator only. Returns 403 for regular members.
    Rebuilds the active recommendation model and clears the recommendation cache.
    """
    return service.refresh_recommendations(db=db)
