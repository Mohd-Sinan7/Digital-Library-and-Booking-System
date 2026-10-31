"""FastAPI route handlers for booking and borrowing.

Endpoints specified in docs/api-contract.md:
- POST /api/bookings
- POST /api/bookings/{id}/borrow
- POST /api/bookings/{id}/return
- DELETE /api/bookings/{id}
- GET /api/bookings/me
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.users.auth import CurrentUser, get_current_user

from .models import Booking
from .rules import (
    BookingRuleError,
    BookNotFoundError,
    BookRemovedError,
    MaxActiveBookingsLimitError,
    NoCopiesAvailableError,
)
from .service import BookingService

router = APIRouter(prefix="/api/bookings", tags=["bookings"])

_service_instance: BookingService | None = None


def get_booking_service() -> BookingService:
    global _service_instance
    if _service_instance is None:
        _service_instance = BookingService()
    return _service_instance


def set_booking_service(service: BookingService | None) -> None:
    global _service_instance
    _service_instance = service


class ReservationRequest(BaseModel):
    book_id: int


def _serialize_booking(b: Booking) -> dict[str, Any]:
    return {
        "id": b.id,
        "user_id": b.user_id,
        "book_id": b.book_id,
        "status": b.status.value,
        "created_at": b.created_at.isoformat(),
        "due_date": b.due_date.isoformat() if b.due_date else None,
        "returned_at": b.returned_at.isoformat() if b.returned_at else None,
        "is_active": b.is_active,
        "is_overdue": b.is_overdue,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def reserve_book_endpoint(
    payload: ReservationRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[BookingService, Depends(get_booking_service)],
) -> dict[str, Any]:
    """Reserves a copy of a book for the authenticated member (FR-B1, FR-B9, BR-01)."""
    try:
        booking = service.reserve_book(user_id=current_user.id, book_id=payload.book_id)
        return _serialize_booking(booking)
    except BookNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except (
        NoCopiesAvailableError,
        BookRemovedError,
        MaxActiveBookingsLimitError,
        BookingRuleError,
    ) as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err


@router.post("/{booking_id}/borrow", status_code=status.HTTP_200_OK)
def borrow_book_endpoint(
    booking_id: int,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[BookingService, Depends(get_booking_service)],
) -> dict[str, Any]:
    """Transitions a reservation to borrowed with a 14-day due date (BR-05, BR-06)."""
    try:
        booking = service.borrow_book(booking_id=booking_id, user_id=current_user.id)
        return _serialize_booking(booking)
    except BookingRuleError as err:
        msg = str(err)
        if "not found" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=msg,
            ) from err
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=msg,
        ) from err


@router.post("/{booking_id}/return", status_code=status.HTTP_200_OK)
def return_book_endpoint(
    booking_id: int,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[BookingService, Depends(get_booking_service)],
) -> dict[str, Any]:
    """Processes return of borrowed book and restores available copy once (BR-07, BR-08)."""
    try:
        booking = service.return_book(booking_id=booking_id, user_id=current_user.id)
        return _serialize_booking(booking)
    except BookingRuleError as err:
        msg = str(err)
        if "not found" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=msg,
            ) from err
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=msg,
        ) from err


@router.delete("/{booking_id}", status_code=status.HTTP_200_OK)
def cancel_booking_endpoint(
    booking_id: int,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[BookingService, Depends(get_booking_service)],
) -> dict[str, Any]:
    """Cancels an active reservation and restores available copy (BR-09, BR-11)."""
    try:
        booking = service.cancel_booking(booking_id=booking_id, user_id=current_user.id)
        return _serialize_booking(booking)
    except BookingRuleError as err:
        msg = str(err)
        if "not found" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=msg,
            ) from err
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=msg,
        ) from err


@router.get("/me", status_code=status.HTTP_200_OK)
def get_my_bookings_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[BookingService, Depends(get_booking_service)],
) -> dict[str, list[dict[str, Any]]]:
    """Returns all bookings for the authenticated member (BR-04, TC-14)."""
    bookings = service.get_user_bookings(user_id=current_user.id)
    return {"items": [_serialize_booking(b) for b in bookings]}
