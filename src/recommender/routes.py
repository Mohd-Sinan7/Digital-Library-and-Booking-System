"""REST endpoints for the Recommendation Engine."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.db import SessionLocal
from src.recommender import service
from src.users.auth import CurrentUser, get_current_user
from src.users.models import ADMIN

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


def get_db():
    """Dependency yielding a database session."""
    with SessionLocal() as db:
        yield db


@router.get("/me")
def get_my_recommendations(
    limit: int = Query(10, ge=1, le=50),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return personalized or cold-start recommendations for the logged-in user (FR-R1).

    Each item carries book_id, title, author, cover_url, score, and reason.
    Requires authentication (Bearer token).
    """
    items = service.get_recommendations(user_id=user.id, limit=limit, db=db)
    return {"items": items, "count": len(items)}


@router.post("/refresh")
def refresh_models(
    user: CurrentUser = Depends(get_current_user),
):
    """Trigger a refresh or retrain of the recommendation models (FR-R6).

    Administrator only. Returns 403 for regular members.
    """
    if user.role != ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return service.refresh_recommendations()
