"""REST endpoints for the Book Catalog module."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.catalog import service
from src.db import SessionLocal

router = APIRouter(prefix="/api/books", tags=["catalog"])


def get_db():
    with SessionLocal() as db:
        yield db


@router.get("")
def list_books(
    q: str | None = None,
    genre: str | None = None,
    available: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Search by title, author or ISBN, filter, and page (FR-C4, FR-C5, FR-C7). Public."""
    return service.get_books(q, genre, available, page, page_size, db=db)
