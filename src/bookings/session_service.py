"""SQLAlchemy session-backed BookingService integrated with Catalog and DB (DLBS-55).

Used by FastAPI routes by default so bookings share the same SQLite/PostgreSQL
database (`src.db.SessionLocal`) and synchronize book `available_copies` through
Member 2's in-process catalog functions (`get_availability`, `change_available_copies`).
"""

import threading
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from typing import Iterator

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src import db as app_db
from src.catalog import service as catalog_service
from src.catalog.models import Book

from .models import Booking, BookingRow, BookingStatus
from .rules import (
    BookingRuleError,
    BookNotFoundError,
    BookRemovedError,
    MaxActiveBookingsLimitError,
    NoCopiesAvailableError,
    calculate_due_date,
    calculate_hold_expiry,
    ensure_can_borrow,
    ensure_can_cancel,
    ensure_can_expire,
    ensure_can_reserve,
    ensure_can_return,
)


def _to_date(value: datetime | date | None) -> date | None:
    """Normalize a date/datetime field to a calendar date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _to_utc_datetime(day: date) -> datetime:
    """Convert a calendar date to a timezone-aware UTC datetime."""
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _lock_row(query, db: Session):
    """Apply row-level locking on databases supporting FOR UPDATE (PostgreSQL)."""
    bind = db.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        return query.with_for_update()
    return query


def _orm_to_domain(row: BookingRow) -> Booking:
    """Convert a BookingRow ORM record to the Booking domain dataclass."""
    res_d = _to_date(row.reserved_at)
    exp_d = _to_date(row.expires_at) or (
        calculate_hold_expiry(res_d) if res_d else None
    )
    return Booking(
        id=row.id,
        user_id=row.user_id,
        book_id=row.book_id,
        status=BookingStatus(row.status),
        reserved_at=res_d,
        expires_at=exp_d,
        borrowed_at=_to_date(row.borrowed_at),
        due_date=_to_date(row.due_date),
        returned_at=_to_date(row.returned_at),
        created_at=res_d,
    )


class SessionBookingService:
    """Booking service backed by the shared SQLAlchemy session and Catalog API."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    @contextmanager
    def _db_session(self) -> Iterator[Session]:
        with app_db.SessionLocal() as session:
            yield session

    def _expire_if_needed(
        self, db: Session, row: BookingRow, current_date: date
    ) -> bool:
        """Transition overdue unborrowed holds (> 2 days) to expired and restore stock."""
        if row.status != BookingStatus.RESERVED.value:
            return False
        exp_d = _to_date(row.expires_at)
        if exp_d is None and row.reserved_at is not None:
            exp_d = calculate_hold_expiry(_to_date(row.reserved_at))
        if exp_d is not None and current_date > exp_d:
            row.status = BookingStatus.EXPIRED.value
            catalog_service.change_available_copies(row.book_id, 1, db=db)
            db.flush()
            return True
        return False

    def reserve_book(
        self,
        user_id: int,
        book_id: int,
        reserved_on: date | None = None,
    ) -> Booking:
        """Atomically reserve a book copy using shared catalog availability (FR-B1, NFR-B1)."""
        res_date = reserved_on or date.today()
        with self._lock, self._db_session() as db:
            try:
                db.scalar(_lock_row(select(Book).where(Book.id == book_id), db))
                # Release expired holds for this user/book before checking availability.
                pending_holds = list(
                    db.scalars(
                        select(BookingRow).where(
                            BookingRow.status == BookingStatus.RESERVED.value,
                            or_(BookingRow.user_id == user_id, BookingRow.book_id == book_id),
                        )
                    )
                )
                expired_any = False
                for hold in pending_holds:
                    if self._expire_if_needed(db, hold, res_date):
                        expired_any = True
                if expired_any:
                    db.commit()

                avail = catalog_service.get_availability(book_id, db=db)
                if avail is None:
                    raise BookNotFoundError(f"Book {book_id} not found in catalog.")

                active_rows = list(
                    db.scalars(
                        select(BookingRow.id).where(
                            BookingRow.user_id == user_id,
                            BookingRow.status.in_(
                                [
                                    BookingStatus.RESERVED.value,
                                    BookingStatus.BORROWED.value,
                                ]
                            ),
                        )
                    )
                )
                active_count = len(active_rows)

                ensure_can_reserve(
                    active_booking_count=active_count,
                    available_copies=avail["available_copies"],
                    is_removed=avail["is_deleted"],
                )

                catalog_service.change_available_copies(book_id, -1, db=db)
                exp_date = calculate_hold_expiry(res_date)
                row = BookingRow(
                    user_id=user_id,
                    book_id=book_id,
                    status=BookingStatus.RESERVED.value,
                    reserved_at=_to_utc_datetime(res_date),
                    expires_at=_to_utc_datetime(exp_date),
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                return _orm_to_domain(row)
            except (
                BookNotFoundError,
                BookRemovedError,
                NoCopiesAvailableError,
                MaxActiveBookingsLimitError,
            ):
                db.rollback()
                raise
            except Exception:
                db.rollback()
                raise

    def borrow_book(
        self,
        booking_id: int,
        user_id: int | None = None,
        borrowed_on: date | None = None,
    ) -> Booking:
        """Transition a valid reservation into borrowed with a 14-day due date (FR-B2)."""
        borrow_date = borrowed_on or date.today()
        with self._lock, self._db_session() as db:
            try:
                row = db.scalar(
                    _lock_row(select(BookingRow).where(BookingRow.id == booking_id), db)
                )
                if row is None:
                    raise BookingRuleError(f"Booking {booking_id} not found.")
                if user_id is not None and row.user_id != user_id:
                    raise BookingRuleError("Cannot borrow another member's booking.")

                if self._expire_if_needed(db, row, borrow_date):
                    exp_d = _to_date(row.expires_at)
                    db.commit()
                    raise BookingRuleError(
                        f"Reservation for booking {booking_id} expired on {exp_d} "
                        "and cannot be borrowed."
                    )

                ensure_can_borrow(row.status)
                due = calculate_due_date(borrow_date)
                row.status = BookingStatus.BORROWED.value
                row.borrowed_at = _to_utc_datetime(borrow_date)
                row.due_date = due
                db.commit()
                db.refresh(row)
                return _orm_to_domain(row)
            except Exception:
                db.rollback()
                raise

    def return_book(
        self,
        booking_id: int,
        user_id: int | None = None,
        returned_on: date | None = None,
    ) -> Booking:
        """Process return of borrowed book and restore catalog copy count (FR-B3)."""
        return_date = returned_on or date.today()
        with self._lock, self._db_session() as db:
            try:
                row = db.scalar(
                    _lock_row(select(BookingRow).where(BookingRow.id == booking_id), db)
                )
                if row is None:
                    raise BookingRuleError(f"Booking {booking_id} not found.")
                if user_id is not None and row.user_id != user_id:
                    raise BookingRuleError("Cannot return another member's booking.")

                ensure_can_return(row.status)
                row.status = BookingStatus.RETURNED.value
                row.returned_at = _to_utc_datetime(return_date)
                catalog_service.change_available_copies(row.book_id, 1, db=db)
                db.commit()
                db.refresh(row)
                return _orm_to_domain(row)
            except Exception:
                db.rollback()
                raise

    def cancel_booking(
        self,
        booking_id: int,
        user_id: int | None = None,
        cancelled_on: date | None = None,
    ) -> Booking:
        """Cancel a reserved booking and restore catalog copy count (FR-B4)."""
        cancel_date = cancelled_on or date.today()
        with self._lock, self._db_session() as db:
            try:
                row = db.scalar(
                    _lock_row(select(BookingRow).where(BookingRow.id == booking_id), db)
                )
                if row is None:
                    raise BookingRuleError(f"Booking {booking_id} not found.")
                if user_id is not None and row.user_id != user_id:
                    raise BookingRuleError("Cannot cancel another member's booking.")

                if self._expire_if_needed(db, row, cancel_date):
                    db.commit()
                    raise BookingRuleError(
                        f"Reservation for booking {booking_id} has expired."
                    )

                ensure_can_cancel(row.status)
                row.status = BookingStatus.CANCELLED.value
                catalog_service.change_available_copies(row.book_id, 1, db=db)
                db.commit()
                db.refresh(row)
                return _orm_to_domain(row)
            except Exception:
                db.rollback()
                raise

    def expire_booking(self, booking_id: int) -> Booking:
        """Explicitly expire a reservation and restore catalog copy count (FR-B10)."""
        with self._lock, self._db_session() as db:
            try:
                row = db.scalar(
                    _lock_row(select(BookingRow).where(BookingRow.id == booking_id), db)
                )
                if row is None:
                    raise BookingRuleError(f"Booking {booking_id} not found.")
                ensure_can_expire(row.status)
                row.status = BookingStatus.EXPIRED.value
                catalog_service.change_available_copies(row.book_id, 1, db=db)
                db.commit()
                db.refresh(row)
                return _orm_to_domain(row)
            except Exception:
                db.rollback()
                raise

    def get_booking(
        self, booking_id: int, as_of: date | None = None
    ) -> Booking | None:
        """Retrieve a booking by ID, dynamically expiring holds past 2 days (FR-B10)."""
        check_date = as_of or date.today()
        with self._lock, self._db_session() as db:
            row = db.get(BookingRow, booking_id)
            if row is None:
                return None
            if self._expire_if_needed(db, row, check_date):
                db.commit()
                db.refresh(row)
            return _orm_to_domain(row)

    def get_user_bookings(
        self, user_id: int, as_of: date | None = None
    ) -> list[Booking]:
        """List a member's bookings newest first, dynamically expiring holds (FR-B7, FR-B10)."""
        check_date = as_of or date.today()
        with self._lock, self._db_session() as db:
            rows = list(
                db.scalars(
                    select(BookingRow)
                    .where(BookingRow.user_id == user_id)
                    .order_by(BookingRow.id.desc())
                )
            )
            changed = False
            for row in rows:
                if self._expire_if_needed(db, row, check_date):
                    changed = True
            if changed:
                db.commit()
            return [_orm_to_domain(row) for row in rows]
