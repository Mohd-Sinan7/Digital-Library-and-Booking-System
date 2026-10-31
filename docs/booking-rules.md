# Booking and Borrowing Rules

## Scope
Member 4 owns reservation and loan behaviour. Catalog owns book records; Member 3 owns users and authentication. Booking code must use their shared interfaces rather than create duplicate user, book, or availability tables.

## Requirements and Acceptance Criteria (DLBS-46 / Sprint 1)

| Requirement | Acceptance Criteria | Implementation / Verification |
|---|---|---|
| **FR-B1** | Booking created as `reserved` and available copies drop by one; a removed book is rejected. | `BookingService.reserve_book` atomically decrements `available_copies` by 1 and creates a booking record with status `reserved`. If `is_removed` is true, rejects with `BookRemovedError` / HTTP 409. |
| **FR-B9** | Reserving a book with 0 available copies returns 409 and changes nothing. | When `available_copies < 1`, transaction raises `NoCopiesAvailableError` / HTTP 409, rolls back, and leaves copies and bookings untouched. |
| **NFR-B1** | In a concurrent test exactly one reservation succeeds and available copies never go below 0. | Protected with atomic transactions (`BEGIN IMMEDIATE`) and locking. Verified with multi-threaded concurrent test (`test_nfr_b1_concurrent_reservations_single_copy`). |

## Business rules

| ID | Rule |
|---|---|
| BR-01 | A signed-in member can reserve a book. |
| BR-02 | A reservation requires at least one available copy. |
| BR-03 | A member can have at most five active bookings (reserved + borrowed). |
| BR-04 | A reservation must identify one member and one book. |
| BR-05 | A reserved booking can be borrowed. |
| BR-06 | Borrowing sets the due date to 14 calendar days after the borrowing date. |
| BR-07 | Only a borrowed booking can be returned. |
| BR-08 | A return is processed once; repeated returns must not increase availability again. |
| BR-09 | Only a reserved booking can be cancelled. |
| BR-10 | A borrowed booking past its due date is overdue. |
| BR-11 | A cancelled, returned or expired booking is not active. |
| BR-12 | Concurrent requests for the final copy must not create two successful reservations. |
| BR-13 | Protected booking endpoints require the shared CurrentUser dependency. |

## Status lifecycle

`reserved -> borrowed -> returned`

`reserved -> cancelled`

`reserved -> expired` (if reservation expiry is adopted by the team; expiry duration must be agreed before implementation).

No transition from `returned`, `cancelled` or `expired` back to an active state.

## Concurrency and Transaction Safety Strategy

To satisfy **NFR-B1**, **FR-B1**, and **FR-B9**:
- SQLite database transactions use `BEGIN IMMEDIATE` and an internal re-entrant mutex (`RLock`) ensuring serialized execution of reservation and availability updates.
- The `books` table enforces a database constraint `CHECK(available_copies >= 0)` preventing underflow at the storage layer.
- `UPDATE books SET available_copies = available_copies - 1 WHERE id = ? AND available_copies > 0` verifies that only positive stock is decremented.
- Any business rule violation triggers an immediate `ROLLBACK`, guaranteeing that availability counts and booking records remain strictly unchanged.

## Integration agreements

- User IDs and authentication come from `src/users/auth.py` (`CurrentUser`).
- Book IDs and `available_copies` come from Member 2's catalog.
- Only one component should decrement/increment `available_copies`; booking service owns availability updates for reservations, returns, and cancellations.
- Persistence/session conventions match the app's shared database setup (`sqlite3` / SQLAlchemy).
- Use integer IDs, snake_case JSON, UTC ISO 8601 timestamps and `{"detail": "..."}` errors.
- Use HTTP 409 for unavailable copies or invalid booking-state conflicts; 401 for missing/invalid authentication; 404 for missing resources; 422 for malformed input.
