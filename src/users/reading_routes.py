"""REST endpoints for reading status, progress, history and statistics (FR-U5 to FR-U8)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from src.users import reading
from src.users.auth import CurrentUser, get_current_user
from src.users.routes import get_db

router = APIRouter(prefix="/api/reading", tags=["reading"])

ReadingStatus = Literal["want_to_read", "reading", "finished"]


class StatusRequest(BaseModel):
    book_id: int
    status: ReadingStatus


class ProgressRequest(BaseModel):
    book_id: int
    current_page: int | None = Field(default=None, ge=0)
    percent: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.current_page is None) == (self.percent is None):
            raise ValueError("Send exactly one of current_page or percent")
        return self


def _book_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")


@router.put("/status")
def set_status(
    body: StatusRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set the reading status for a book (FR-U5). Creates the record if needed."""
    try:
        return reading.set_status(user.id, body.book_id, body.status, db)
    except reading.BookNotFoundError:
        raise _book_not_found() from None


@router.post("/progress")
def record_progress(
    body: ProgressRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record progress as current_page or percent (FR-U6)."""
    try:
        return reading.record_progress(
            user.id, body.book_id, db, current_page=body.current_page, percent=body.percent
        )
    except reading.BookNotFoundError:
        raise _book_not_found() from None
    except reading.InvalidProgressError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from None


@router.get("/history")
def history(
    status_filter: ReadingStatus | None = Query(default=None, alias="status"),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The current user's reading history, newest first (FR-U7). Optional ?status= filter."""
    return {"items": reading.list_history(user.id, db, status_filter)}


@router.get("/stats")
def stats(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """The current user's reading statistics (FR-U8)."""
    return reading.get_stats(user.id, db)
