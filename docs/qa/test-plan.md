# QA Test Plan: Booking and Borrowing

## Objective
Verify reservation, borrowing, return, cancellation, overdue and availability rules, including authentication and concurrent access to the final copy.

## Scope

**In scope:** booking limits, copy availability, booking state transitions, due-date calculation, overdue detection, idempotent return, API status codes, authentication and integration with catalog/user modules.

**Out of scope until interfaces are agreed:** UI testing, load testing thresholds, reservation-expiry duration, deployment-specific database performance.

## Test levels

1. Unit: pure business rules and date calculations.
2. API integration: endpoint validation, authentication, status codes and JSON shape.
3. Integration: catalog availability and user identity.
4. Concurrency: two requests competing for the final available copy.

## Entry criteria

- Shared auth dependency and catalog interface are available.
- Booking routes are mounted in the FastAPI app.
- Test database can be reset between tests.

## Exit criteria

- All critical and high-priority cases pass.
- No duplicate reservation for a single remaining copy.
- No duplicate stock increment on repeated return.
- `ruff check .` and `pytest` pass.

## Environment
Python 3.11+, project dependencies from `requirements.txt`, isolated test database, pytest. Never run destructive tests against real/demo production data.

## Risks
Concurrency bugs, inconsistent availability counts, timezone/date-boundary errors, and mismatch between catalog and booking state. Use database transactions and a single stock-update owner to mitigate these risks.
