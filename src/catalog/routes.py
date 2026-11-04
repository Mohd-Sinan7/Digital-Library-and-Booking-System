"""REST endpoints for the Book Catalog module."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from src.catalog import service
from src.catalog.schemas import BookCreate, BookUpdate
from src.db import SessionLocal
from src.users.auth import CurrentUser, get_current_user
from src.users.models import ADMIN

router = APIRouter(prefix="/api/books", tags=["catalog"])


def get_db():
    with SessionLocal() as db:
        yield db


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """401 without a token (from get_current_user), 403 for members (FR-C8)."""
    # shortcut: local copy until src.users.auth.require_admin (DLBS-37) is on main, then use that.
    if user.role != ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user


def _not_found():
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")


@router.get("")
def list_books(
    q: str | None = None,
    genre: str | None = None,
    available: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Search by title, author or ISBN, filter, and page (FR-C4, FR-C5, FR-C7). Public."""
    return service.get_books(q, genre, available, page, page_size, db=db)


@router.get("/genres")
def list_genres(db: Session = Depends(get_db)):
    """Genres for the catalog filter dropdown (FR-C5). Public."""
    return {"items": service.get_genres(db=db)}


@router.get("/{book_id}/availability")
def get_availability(book_id: int, db: Session = Depends(get_db)):
    """Copy counts for the UI (FR-C5). Public. 404 for missing or deleted books."""
    data = service.get_availability(book_id, db=db)
    if data is None or data["is_deleted"]:
        raise _not_found()
    return {k: data[k] for k in ("book_id", "total_copies", "available_copies", "is_available")}


@router.get("/{book_id}")
def get_book(book_id: int, db: Session = Depends(get_db)):
    """Book detail (FR-C6). Public. 404 for missing or deleted books."""
    book = service.get_book(book_id, db=db)
    if book is None:
        raise _not_found()
    return book


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_book(body: BookCreate, db: Session = Depends(get_db)):
    """Add a book (FR-C1). Admin only."""
    try:
        return service.create_book(body.model_dump(), db)
    except service.DuplicateIsbnError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.put("/{book_id}", dependencies=[Depends(require_admin)])
def update_book(book_id: int, body: BookUpdate, db: Session = Depends(get_db)):
    """Edit any subset of fields (FR-C2). Admin only."""
    try:
        book = service.update_book(book_id, body.model_dump(exclude_unset=True), db)
    except (service.DuplicateIsbnError, service.CopiesBelowZeroError) as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e)) from e
    if book is None:
        raise _not_found()
    return book


@router.delete(
    "/{book_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)]
)
def delete_book(book_id: int, db: Session = Depends(get_db)):
    """Soft delete (FR-C3). Admin only."""
    if not service.delete_book(book_id, db):
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
