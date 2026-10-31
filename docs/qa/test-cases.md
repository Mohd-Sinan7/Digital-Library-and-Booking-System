# QA Test Cases: Booking and Borrowing

| ID | Scenario | Expected result | Priority |
|---|---|---|---|
| TC-01 | Reserve a book with available copies (FR-B1) | Booking created with `reserved`; availability decreases by 1 | High |
| TC-02 | Reserve a book with zero available copies (FR-B9) | Rejected with 409; no booking created; stock unchanged | Critical |
| TC-03 | Reserve as unauthenticated user | Rejected with 401 | High |
| TC-04 | Member attempts sixth active booking | Rejected with 409; existing bookings unchanged | High |
| TC-05 | Borrow a reserved booking | Status becomes `borrowed`; due date is 14 days later | Critical |
| TC-06 | Borrow a cancelled/returned booking | Rejected with 409 | High |
| TC-07 | Return a borrowed booking | Status becomes `returned`; availability restored once | Critical |
| TC-08 | Return the same booking twice | Second request rejected; stock restored only once | Critical |
| TC-09 | Cancel a reserved booking | Status becomes `cancelled`; availability restored once | High |
| TC-10 | Cancel a borrowed booking | Rejected with 409 | High |
| TC-11 | Borrowed booking passes due date | Overdue flag is true | Medium |
| TC-12 | Two or more members reserve the last copy concurrently (NFR-B1) | Exactly one reservation succeeds; available copies never go below 0 | Critical |
| TC-13 | Request another member's booking by ID | Rejected with 409 / forbidden | High |
| TC-14 | Fetch current member's bookings | Only authenticated member's bookings returned | High |
| TC-15 | Unknown booking ID on borrow/return/cancel | Rejected with 404 | Medium |
| TC-16 | Reserve a removed book (FR-B1) | Rejected with 409; available copies unchanged | High |
| TC-17 | Zero-copies reservation via API returns 409 (FR-B9) | Rejected with HTTP 409 conflict and error detail | High |

## Execution Record (Sprint 1 - 31 Oct 2026)

| ID | Test Case Description | Build / Commit | Tester | Execution Date | Status |
|---|---|---|---|---|---|
| TC-01 | Reserve book with available copies | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-02 | Reserve book with zero available copies | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-03 | Reserve as unauthenticated user | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-04 | Member attempts 6th active booking | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-05 | Borrow reserved booking | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-06 | Borrow cancelled/returned booking | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-07 | Return borrowed booking | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-08 | Return same booking twice | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-09 | Cancel reserved booking | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-10 | Cancel borrowed booking | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-11 | Overdue flag calculation | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-12 | Concurrent reservations for single copy (NFR-B1) | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-13 | Inter-member booking access isolation | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-14 | Fetch authenticated member's bookings | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-15 | Unknown book / booking ID returns 404 | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-16 | Reserve removed book rejected (FR-B1) | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
| TC-17 | Reserve with 0 copies returns 409 (FR-B9) | DLBS-46 | Rushi Eswar (Member 4) | 2026-10-31 | Pass |
