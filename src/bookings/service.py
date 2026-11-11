"""Booking use-case boundary with transaction safety.

Implements reservation, borrowing, return, cancellation, and concurrency protection:
- FR-B1: Booking created as reserved and available copies drop by 1; removed books rejected.
- FR-B2: Status becomes borrowed, due date is 14 days after borrowing, copies unchanged.
- FR-B3: Status becomes returned and available copies rise by one; non-borrowed rejected.
- FR-B4: Status becomes cancelled and available copies rise by one; borrowed cannot cancel.
- FR-B5: Counts checked after every action in TC-B01, TC-B03, TC-B05 and TC-B08.
- FR-B6: A borrowed booking read after its due date shows overdue = true.
- FR-B7: GET /api/bookings/me lists only the member's bookings with status, dates and overdue flag.
- FR-B9: Reserving a book with 0 available copies returns conflict/error and changes nothing.
- FR-B10: Hold expires after 2 days; copy becomes available again (dynamic on-read expiry).
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
    calculate_hold_expiry,
    ensure_can_borrow,
    ensure_can_cancel,
    ensure_can_expire,
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
                    status TEXT NOT NULL CHECK(
                        status IN ('reserved', 'borrowed', 'returned', 'cancelled', 'expired')
                    ),
                    reserved_at TEXT NOT NULL,
                    expires_at TEXT,
                    borrowed_at TEXT,
                    due_date TEXT,
                    returned_at TEXT,
                    created_at TEXT,
                    FOREIGN KEY(book_id) REFERENCES books(id)
                )
                """
            )
            # Ensure compatibility with shared catalog and booking tables in SQLite
            cursor.execute("PRAGMA table_info(books)")
            cols = [col[1] for col in cursor.fetchall()]
            if cols and "is_removed" not in cols:
                cursor.execute("ALTER TABLE books ADD COLUMN is_removed INTEGER NOT NULL DEFAULT 0")
                if "is_deleted" in cols:
                    cursor.execute("UPDATE books SET is_removed = is_deleted")

            cursor.execute("PRAGMA table_info(bookings)")
            bcols = [col[1] for col in cursor.fetchall()]
            if bcols and "created_at" not in bcols:
                cursor.execute("ALTER TABLE bookings ADD COLUMN created_at TEXT")

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

    def _row_to_booking(
        self,
        cursor: sqlite3.Cursor,
        row: tuple,
        as_of: date | None = None,
    ) -> Booking:
        """Parse DB row into domain model, applying dynamic hold expiry on read (FR-B10)."""
        (
            b_id,
            b_user_id,
            b_book_id,
            status_str,
            created_at_str,
            due_date_str,
            returned_at_str,
            reserved_at_str,
            expires_at_str,
            borrowed_at_str,
        ) = row

        current_date = as_of or date.today()

        # Dynamic hold expiry on read (FR-B10):
        # A reservation read > 2 days after creation shows expired and copy is restored.
        if status_str == BookingStatus.RESERVED.value:
            exp_date: date | None = None
            if expires_at_str:
                exp_date = date.fromisoformat(expires_at_str.split("T")[0])
            elif reserved_at_str:
                res_d = date.fromisoformat(reserved_at_str.split("T")[0])
                exp_date = calculate_hold_expiry(res_d)

            if exp_date is not None and current_date > exp_date:
                # Atomically expire hold and restore copy
                cursor.execute(
                    "UPDATE bookings SET status = ? WHERE id = ? AND status = ?",
                    (BookingStatus.EXPIRED.value, b_id, BookingStatus.RESERVED.value),
                )
                if cursor.rowcount == 1:
                    cursor.execute(
                        "UPDATE books SET available_copies = available_copies + 1 WHERE id = ?",
                        (b_book_id,),
                    )
                    self._conn.commit()
                status_str = BookingStatus.EXPIRED.value

        created_d = (
            date.fromisoformat(created_at_str.split("T")[0]) if created_at_str else None
        )
        reserved_d = (
            date.fromisoformat(reserved_at_str.split("T")[0])
            if reserved_at_str
            else created_d
        )
        expires_d = (
            date.fromisoformat(expires_at_str.split("T")[0])
            if expires_at_str
            else (calculate_hold_expiry(reserved_d) if reserved_d else None)
        )
        borrowed_d = (
            date.fromisoformat(borrowed_at_str.split("T")[0])
            if borrowed_at_str
            else None
        )
        due_d = date.fromisoformat(due_date_str.split("T")[0]) if due_date_str else None
        returned_d = (
            date.fromisoformat(returned_at_str.split("T")[0])
            if returned_at_str
            else None
        )

        return Booking(
            id=b_id,
            user_id=b_user_id,
            book_id=b_book_id,
            status=BookingStatus(status_str),
            reserved_at=reserved_d,
            expires_at=expires_d,
            borrowed_at=borrowed_d,
            due_date=due_d,
            returned_at=returned_d,
            created_at=created_d,
        )

    def reserve_book(
        self,
        user_id: int,
        book_id: int,
        reserved_on: date | None = None,
    ) -> Booking:
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
                    raise NoCopiesAvailableError(
                        f"No copies of '{title}' are currently available."
                    )

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
                    raise NoCopiesAvailableError(
                        f"No copies of '{title}' are currently available."
                    )

                res_date = reserved_on or date.today()
                res_date_str = res_date.isoformat()
                expires = calculate_hold_expiry(res_date)
                expires_str = expires.isoformat()
                cursor.execute(
                    """
                    INSERT INTO bookings (
                        user_id, book_id, status, reserved_at, expires_at, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        book_id,
                        BookingStatus.RESERVED.value,
                        res_date_str,
                        expires_str,
                        res_date_str,
                    ),
                )
                booking_id = cursor.lastrowid
                self._conn.commit()

                return Booking(
                    id=booking_id,
                    user_id=user_id,
                    book_id=book_id,
                    status=BookingStatus.RESERVED,
                    reserved_at=res_date,
                    expires_at=expires,
                    created_at=res_date,
                )
            except Exception:
                self._conn.rollback()
                raise

    def borrow_book(
        self,
        booking_id: int,
        user_id: int | None = None,
        borrowed_on: date | None = None,
    ) -> Booking:
        """Transition a reserved booking to borrowed with 14-day due date (FR-B2, FR-B6, FR-B10)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute(
                    """
                    SELECT id, user_id, book_id, status, created_at, due_date, returned_at,
                           reserved_at, expires_at, borrowed_at
                    FROM bookings WHERE id = ?
                    """,
                    (booking_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise BookingRuleError(f"Booking {booking_id} not found.")

                (
                    b_id,
                    b_user_id,
                    b_book_id,
                    status_str,
                    created_at_str,
                    _,
                    _,
                    reserved_at_str,
                    expires_at_str,
                    _,
                ) = row

                if user_id is not None and b_user_id != user_id:
                    raise BookingRuleError("Cannot borrow another member's booking.")

                borrow_date = borrowed_on or date.today()

                # Check if hold expired before borrowing (FR-B10)
                exp_date: date | None = None
                if expires_at_str:
                    exp_date = date.fromisoformat(expires_at_str.split("T")[0])
                elif reserved_at_str:
                    exp_date = calculate_hold_expiry(
                        date.fromisoformat(reserved_at_str.split("T")[0])
                    )

                if (
                    status_str == BookingStatus.RESERVED.value
                    and exp_date is not None
                    and borrow_date > exp_date
                ):
                    cursor.execute(
                        "UPDATE bookings SET status = ? WHERE id = ? AND status = ?",
                        (
                            BookingStatus.EXPIRED.value,
                            booking_id,
                            BookingStatus.RESERVED.value,
                        ),
                    )
                    if cursor.rowcount == 1:
                        cursor.execute(
                            "UPDATE books SET available_copies = available_copies + 1 WHERE id = ?",
                            (b_book_id,),
                        )
                        self._conn.commit()
                    raise BookingRuleError(
                        f"Reservation for booking {booking_id} expired on {exp_date} "
                        "and cannot be borrowed."
                    )

                ensure_can_borrow(status_str)

                due = calculate_due_date(borrow_date)
                cursor.execute(
                    "UPDATE bookings SET status = ?, borrowed_at = ?, due_date = ? WHERE id = ?",
                    (
                        BookingStatus.BORROWED.value,
                        borrow_date.isoformat(),
                        due.isoformat(),
                        booking_id,
                    ),
                )
                self._conn.commit()

                res_d = (
                    date.fromisoformat(reserved_at_str.split("T")[0])
                    if reserved_at_str
                    else date.fromisoformat(created_at_str.split("T")[0])
                )
                return Booking(
                    id=b_id,
                    user_id=b_user_id,
                    book_id=b_book_id,
                    status=BookingStatus.BORROWED,
                    reserved_at=res_d,
                    borrowed_at=borrow_date,
                    created_at=res_d,
                    due_date=due,
                    expires_at=exp_date,
                )
            except Exception:
                self._conn.rollback()
                raise

    def return_book(
        self,
        booking_id: int,
        user_id: int | None = None,
        returned_on: date | None = None,
    ) -> Booking:
        """Process book return and restore available copy once (FR-B3, FR-B5)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute(
                    """
                    SELECT id, user_id, book_id, status, created_at, due_date, returned_at,
                           reserved_at, expires_at, borrowed_at
                    FROM bookings WHERE id = ?
                    """,
                    (booking_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise BookingRuleError(f"Booking {booking_id} not found.")

                (
                    b_id,
                    b_user_id,
                    b_book_id,
                    status_str,
                    created_at_str,
                    due_date_str,
                    _,
                    reserved_at_str,
                    expires_at_str,
                    borrowed_at_str,
                ) = row

                if user_id is not None and b_user_id != user_id:
                    raise BookingRuleError("Cannot return another member's booking.")

                ensure_can_return(status_str)

                return_date = returned_on or date.today()
                cursor.execute(
                    "UPDATE bookings SET status = ?, returned_at = ? WHERE id = ?",
                    (BookingStatus.RETURNED.value, return_date.isoformat(), booking_id),
                )
                cursor.execute(
                    "UPDATE books SET available_copies = available_copies + 1 WHERE id = ?",
                    (b_book_id,),
                )
                self._conn.commit()

                res_d = (
                    date.fromisoformat(reserved_at_str.split("T")[0])
                    if reserved_at_str
                    else date.fromisoformat(created_at_str.split("T")[0])
                )
                return Booking(
                    id=b_id,
                    user_id=b_user_id,
                    book_id=b_book_id,
                    status=BookingStatus.RETURNED,
                    reserved_at=res_d,
                    created_at=res_d,
                    due_date=(
                        date.fromisoformat(due_date_str.split("T")[0])
                        if due_date_str
                        else None
                    ),
                    returned_at=return_date,
                    borrowed_at=(
                        date.fromisoformat(borrowed_at_str.split("T")[0])
                        if borrowed_at_str
                        else None
                    ),
                    expires_at=(
                        date.fromisoformat(expires_at_str.split("T")[0])
                        if expires_at_str
                        else None
                    ),
                )
            except Exception:
                self._conn.rollback()
                raise

    def cancel_booking(
        self,
        booking_id: int,
        user_id: int | None = None,
        cancelled_on: date | None = None,
    ) -> Booking:
        """Cancel a reserved booking and restore available copy (FR-B4, FR-B5)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute(
                    """
                    SELECT id, user_id, book_id, status, created_at, due_date, returned_at,
                           reserved_at, expires_at, borrowed_at
                    FROM bookings WHERE id = ?
                    """,
                    (booking_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise BookingRuleError(f"Booking {booking_id} not found.")

                (
                    b_id,
                    b_user_id,
                    b_book_id,
                    status_str,
                    created_at_str,
                    _,
                    _,
                    reserved_at_str,
                    expires_at_str,
                    _,
                ) = row

                if user_id is not None and b_user_id != user_id:
                    raise BookingRuleError("Cannot cancel another member's booking.")

                current_date = cancelled_on or date.today()
                exp_date: date | None = None
                if expires_at_str:
                    exp_date = date.fromisoformat(expires_at_str.split("T")[0])
                elif reserved_at_str:
                    exp_date = calculate_hold_expiry(
                        date.fromisoformat(reserved_at_str.split("T")[0])
                    )

                if (
                    status_str == BookingStatus.RESERVED.value
                    and exp_date is not None
                    and current_date > exp_date
                ):
                    cursor.execute(
                        "UPDATE bookings SET status = ? WHERE id = ? AND status = ?",
                        (
                            BookingStatus.EXPIRED.value,
                            booking_id,
                            BookingStatus.RESERVED.value,
                        ),
                    )
                    if cursor.rowcount == 1:
                        cursor.execute(
                            "UPDATE books SET available_copies = available_copies + 1 WHERE id = ?",
                            (b_book_id,),
                        )
                        self._conn.commit()
                    raise BookingRuleError(
                        f"Reservation for booking {booking_id} has expired."
                    )

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

                res_d = (
                    date.fromisoformat(reserved_at_str.split("T")[0])
                    if reserved_at_str
                    else date.fromisoformat(created_at_str.split("T")[0])
                )
                return Booking(
                    id=b_id,
                    user_id=b_user_id,
                    book_id=b_book_id,
                    status=BookingStatus.CANCELLED,
                    reserved_at=res_d,
                    created_at=res_d,
                )
            except Exception:
                self._conn.rollback()
                raise

    def expire_booking(self, booking_id: int) -> Booking:
        """Expire a reservation past 2 days and restore available copy (FR-B10)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute(
                    """
                    SELECT id, user_id, book_id, status, created_at, due_date, returned_at,
                           reserved_at, expires_at, borrowed_at
                    FROM bookings WHERE id = ?
                    """,
                    (booking_id,),
                )
                row = cursor.fetchone()
                if not row:
                    raise BookingRuleError(f"Booking {booking_id} not found.")

                (
                    b_id,
                    b_user_id,
                    b_book_id,
                    status_str,
                    created_at_str,
                    _,
                    _,
                    reserved_at_str,
                    expires_at_str,
                    _,
                ) = row
                ensure_can_expire(status_str)

                cursor.execute(
                    "UPDATE bookings SET status = ? WHERE id = ?",
                    (BookingStatus.EXPIRED.value, booking_id),
                )
                cursor.execute(
                    "UPDATE books SET available_copies = available_copies + 1 WHERE id = ?",
                    (b_book_id,),
                )
                self._conn.commit()

                res_d = (
                    date.fromisoformat(reserved_at_str.split("T")[0])
                    if reserved_at_str
                    else date.fromisoformat(created_at_str.split("T")[0])
                )
                exp_d = (
                    date.fromisoformat(expires_at_str.split("T")[0])
                    if expires_at_str
                    else None
                )
                return Booking(
                    id=b_id,
                    user_id=b_user_id,
                    book_id=b_book_id,
                    status=BookingStatus.EXPIRED,
                    reserved_at=res_d,
                    created_at=res_d,
                    expires_at=exp_d,
                )
            except Exception:
                self._conn.rollback()
                raise

    def get_booking(
        self, booking_id: int, as_of: date | None = None
    ) -> Booking | None:
        """Fetch a single booking by ID with dynamic hold expiry on read (FR-B10)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT id, user_id, book_id, status, created_at, due_date, returned_at,
                       reserved_at, expires_at, borrowed_at
                FROM bookings
                WHERE id = ?
                """,
                (booking_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_booking(cursor, row, as_of)

    def get_user_bookings(
        self, user_id: int, as_of: date | None = None
    ) -> list[Booking]:
        """Fetch all bookings for a user, newest first, with dynamic hold expiry (FR-B7, FR-B10)."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT id, user_id, book_id, status, created_at, due_date, returned_at,
                       reserved_at, expires_at, borrowed_at
                FROM bookings
                WHERE user_id = ?
                ORDER BY id DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_booking(cursor, row, as_of) for row in rows]
