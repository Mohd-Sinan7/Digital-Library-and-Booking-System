# Booking and Borrowing Rules

## Scope
Member 4 owns reservation and loan behaviour. Catalog owns book records; Member 3 owns users and authentication. Booking code must use their shared interfaces rather than create duplicate user, book, or availability tables.

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

## Integration agreements

- User IDs and authentication come from `src/users/auth.py` (`CurrentUser`).
- Book IDs and `available_copies` come from Member 2's catalog.
- Only one component should decrement/increment `available_copies`; confirm ownership with Member 2.
- Persistence/session conventions must match the app's shared database setup.
- Use integer IDs, snake_case JSON, UTC ISO 8601 timestamps and `{"detail": "..."}` errors.
- Use HTTP 409 for unavailable copies or invalid booking-state conflicts; 401 for missing/invalid authentication; 404 for missing resources; 422 for malformed input.

## Open decisions before full route implementation

1. Reservation expiry duration and whether expiry is in Sprint 1 or later.
2. Whether the five-item limit counts borrowed items as well as reservations. This document assumes yes, matching “active bookings”.
3. Whether a member may reserve a title they are already borrowing.
4. Exact catalog availability update function and transaction/locking strategy.
5. Whether admin users can create bookings on behalf of members.
