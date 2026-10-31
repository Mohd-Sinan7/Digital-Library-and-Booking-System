# QA Test Plan: Booking and Borrowing

## Objective
Verify reservation, borrowing, return, cancellation, overdue and availability rules, including authentication and concurrent access to the final copy (satisfying FR-B1, FR-B9, and NFR-B1).

## Scope

**In scope:** booking limits, copy availability, transaction safety, booking state transitions, due-date calculation, overdue detection, idempotent return, API status codes (401, 404, 409), authentication and concurrent access safety.

**Out of scope until interfaces are agreed:** UI testing, load testing beyond concurrency thresholds, reservation-expiry duration.

## Test levels

1. Unit: pure business rules, date calculations, and status validation (`tests/test_booking_rules.py`).
2. Concurrency: multiple threads attempting to reserve the last remaining copy concurrently (`test_nfr_b1_concurrent_reservations_single_copy`).
3. Persistence & Transaction Safety: SQLite ACID transaction testing, rollbacks on rule errors, `CHECK(available_copies >= 0)` constraint enforcement.
4. API integration: FastAPI test client endpoint validation, HTTP status codes (201, 200, 401, 404, 409) and JSON serialization.

## Entry criteria

- Shared auth dependency and catalog interface available.
- Booking service and routes implemented with transaction boundaries.
- Isolated test database per test execution.

## Exit criteria

- All critical and high-priority cases pass (100% test pass rate).
- Concurrency test passes: no duplicate reservation for a single remaining copy, available copies never negative (NFR-B1).
- No duplicate stock increment on repeated return (BR-08).
- `ruff check .` and `pytest --cov=src.bookings` pass with zero linter errors and >85% coverage.

## Environment
Python 3.11+, pytest, pytest-cov, ruff, SQLite memory/file backend, FastAPI TestClient.

## Risks & Mitigations
- Concurrency race conditions: Mitigated by SQLite transaction isolation (`BEGIN IMMEDIATE`) and re-entrant mutex locking.
- Stock inconsistency: Mitigated by database CHECK constraints and unified availability updates in `BookingService`.
