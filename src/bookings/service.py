"""Booking use-case boundary with transaction safety.

Implements reservation, borrowing, return, cancellation, and concurrency protection:
- FR-B1: Booking created as reserved and available copies drop by 1; removed books rejected.
- FR-B9: Reserving a book with 0 available copies returns conflict/error and changes nothing.
- NFR-B1: In concurrent reservations, exactly one succeeds and copies never drop below 0.
"""

import sqlite3
import threading
from datetime import date

from .models import Booking, BookingStatus
from .rules import (
    MAX_ACTIVE_BOOKINGS,
    BookingRuleError,
    BookNotFoundError,
    BookRemovedError,
    MaxActiveBookingsLimitError,
    NoCopiesAvailableError,
    calculate_due_date,
    ensure_can_borrow,
    ensure_can_cancel,
    ensure_can_reserve,
    ensure_can_return,
)


class BookingService:
    """Coordinates booking rules and persistent state with transaction safety."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            timeout=30.0,
            isolation_level=None,
        )
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    available_copies INTEGER NOT NULL CHECK(available_copies >= 0),
                    is_removed INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    book_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    due_date TEXT,
                    returned_at TEXT,
                    FOREIGN KEY(book_id) REFERENCES books(id)
                )
                """
            )
            self._conn.commit()

    def seed_book(
        self,
        book_id: int,
        title: str,
        available_copies: int,
        is_removed: bool = False,
    ) -> None:
        """Seed or update book availability for testing and catalog integration."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO books (id, title, available_copies, is_removed)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    available_copies=excluded.available_copies,
                    is_removed=excluded.is_removed
                """,
                (book_id, title, available_copies, 1 if is_removed else 0),
            )
            self._conn.commit()

    def get_book(self, book_id: int) -> dict | None:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT id, title, available_copies, is_removed FROM books WHERE id = ?",
                (book_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "title": row[1],
                "available_copies": row[2],
                "is_removed": bool(row[3]),
            }

    def validate_reservation(
        self,
        active_booking_count: int,
        available_copies: int,
        is_removed: bool = False,
    ) -> None:
        ensure_can_reserve(active_booking_count, available_copies, is_removed)

    def borrow_due_date(self, status: str, borrowed_on: date) -> date:
        ensure_can_borrow(status)
        return calculate_due_date(borrowed_on)

    def validate_cancellation(self, status: str) -> None:
        ensure_can_cancel(status)

    def validate_return(self, status: str) -> None:
        ensure_can_return(status)

    def reserve_book(self, user_id: int, book_id: int) -> Booking:
        """Reserve a book copy with strict transaction safety (FR-B1, FR-B9, NFR-B1)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute(
                    "SELECT id, title, available_copies, is_removed FROM books WHERE id = ?",
                    (book_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise BookNotFoundError(f"Book {book_id} not found in catalog.")

                _, title, available_copies, is_removed = row
                if bool(is_removed):
                    raise BookRemovedError(f"Book '{title}' is removed from catalog.")

                if available_copies < 1:
                    raise NoCopiesAvailableError(f"No copies of '{title}' are currently available.")

                cursor.execute(
                    """
                    SELECT COUNT(*) FROM bookings
                    WHERE user_id = ? AND status IN ('reserved', 'borrowed')
                    """,
                    (user_id,),
                )
                active_count = cursor.fetchone()[0]
                if active_count >= MAX_ACTIVE_BOOKINGS:
                    raise MaxActiveBookingsLimitError(
                        "A member may have at most 5 active bookings."
                    )

                cursor.execute(
                    """
                    UPDATE books
                    SET available_copies = available_copies - 1
                    WHERE id = ? AND available_copies > 0
                    """,
                    (book_id,),
                )
                if cursor.rowcount != 1:
                    raise NoCopiesAvailableError(f"No copies of '{title}' are currently available.")

                today = date.today()
                today_str = today.isoformat()
                cursor.execute(
                    """
                    INSERT INTO bookings (user_id, book_id, status, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, book_id, BookingStatus.RESERVED.value, today_str),
                )
                booking_id = cursor.lastrowid
                self._conn.commit()

                return Booking(
                    id=booking_id,
                    user_id=user_id,
                    book_id=book_id,
                    status=BookingStatus.RESERVED,
                    created_at=today,
                )
            except Exception:
                self._conn.rollback()
                raise

    def borrow_book(self, booking_id: int, user_id: int | None = None) -> Booking:
        """Transition a reserved booking to borrowed with 14-day due date (BR-05, BR-06)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute(
                    """
                    SELECT id, user_id, book_id, status, created_at, due_date, returned_at
                    FROM bookings WHERE id = ?
                    """,
                    (booking_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise BookingRuleError(f"Booking {booking_id} not found.")

                b_id, b_user_id, b_book_id, status_str, created_at_str, _, _ = row
                if user_id is not None and b_user_id != user_id:
                    raise BookingRuleError("Cannot borrow another member's booking.")

                ensure_can_borrow(status_str)

                borrow_date = date.today()
                due = calculate_due_date(borrow_date)
                cursor.execute(
                    "UPDATE bookings SET status = ?, due_date = ? WHERE id = ?",
                    (BookingStatus.BORROWED.value, due.isoformat(), booking_id),
                )
                self._conn.commit()

                return Booking(
                    id=b_id,
                    user_id=b_user_id,
                    book_id=b_book_id,
                    status=BookingStatus.BORROWED,
                    created_at=date.fromisoformat(created_at_str),
                    due_date=due,
                )
            except Exception:
                self._conn.rollback()
                raise

    def return_book(self, booking_id: int, user_id: int | None = None) -> Booking:
        """Process book return and restore available copy once (BR-07, BR-08)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute(
                    """
                    SELECT id, user_id, book_id, status, created_at, due_date, returned_at
                    FROM bookings WHERE id = ?
                    """,
                    (booking_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise BookingRuleError(f"Booking {booking_id} not found.")

                b_id, b_user_id, b_book_id, status_str, created_at_str, due_date_str, _ = row
                if user_id is not None and b_user_id != user_id:
                    raise BookingRuleError("Cannot return another member's booking.")

                ensure_can_return(status_str)

                return_date = date.today()
                cursor.execute(
                    "UPDATE bookings SET status = ?, returned_at = ? WHERE id = ?",
                    (BookingStatus.RETURNED.value, return_date.isoformat(), booking_id),
                )
                cursor.execute(
                    "UPDATE books SET available_copies = available_copies + 1 WHERE id = ?",
                    (b_book_id,),
                )
                self._conn.commit()

                return Booking(
                    id=b_id,
                    user_id=b_user_id,
                    book_id=b_book_id,
                    status=BookingStatus.RETURNED,
                    created_at=date.fromisoformat(created_at_str),
                    due_date=date.fromisoformat(due_date_str) if due_date_str else None,
                    returned_at=return_date,
                )
            except Exception:
                self._conn.rollback()
                raise

    def cancel_booking(self, booking_id: int, user_id: int | None = None) -> Booking:
        """Cancel a reserved booking and restore available copy (BR-09)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute(
                    """
                    SELECT id, user_id, book_id, status, created_at, due_date, returned_at
                    FROM bookings WHERE id = ?
                    """,
                    (booking_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise BookingRuleError(f"Booking {booking_id} not found.")

                b_id, b_user_id, b_book_id, status_str, created_at_str, _, _ = row
                if user_id is not None and b_user_id != user_id:
                    raise BookingRuleError("Cannot cancel another member's booking.")

                ensure_can_cancel(status_str)

                cursor.execute(
                    "UPDATE bookings SET status = ? WHERE id = ?",
                    (BookingStatus.CANCELLED.value, booking_id),
                )
                cursor.execute(
                    "UPDATE books SET available_copies = available_copies + 1 WHERE id = ?",
                    (b_book_id,),
                )
                self._conn.commit()

                return Booking(
                    id=b_id,
                    user_id=b_user_id,
                    book_id=b_book_id,
                    status=BookingStatus.CANCELLED,
                    created_at=date.fromisoformat(created_at_str),
                )
            except Exception:
                self._conn.rollback()
                raise

    def get_user_bookings(self, user_id: int) -> list[Booking]:
        """Fetch all bookings for a user, newest first."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT id, user_id, book_id, status, created_at, due_date, returned_at
                FROM bookings
                WHERE user_id = ?
                ORDER BY id DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
            return [
                Booking(
                    id=row[0],
                    user_id=row[1],
                    book_id=row[2],
                    status=BookingStatus(row[3]),
                    created_at=date.fromisoformat(row[4]),
                    due_date=date.fromisoformat(row[5]) if row[5] else None,
                    returned_at=date.fromisoformat(row[6]) if row[6] else None,
                )
                for row in rows
            ]
