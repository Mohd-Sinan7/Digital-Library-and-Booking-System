# QA Test Cases: Booking and Borrowing

| ID | Scenario | Expected result | Priority |
|---|---|---|---|
| TC-01 | Reserve a book with available copies | Booking created with `reserved`; availability changes once | High |
| TC-02 | Reserve a book with zero available copies | Rejected with 409; no booking created | Critical |
| TC-03 | Reserve as unauthenticated user | Rejected with 401 | High |
| TC-04 | Member attempts sixth active booking | Rejected; existing bookings unchanged | High |
| TC-05 | Borrow a reserved booking | Status becomes `borrowed`; due date is 14 days later | Critical |
| TC-06 | Borrow a cancelled/returned booking | Rejected with 409 | High |
| TC-07 | Return a borrowed booking | Status becomes `returned`; availability restored once | Critical |
| TC-08 | Return the same booking twice | Second request rejected or idempotently handled; stock restored only once | Critical |
| TC-09 | Cancel a reserved booking | Status becomes `cancelled`; availability restored once | High |
| TC-10 | Cancel a borrowed booking | Rejected with 409 | High |
| TC-11 | Borrowed booking passes due date | Overdue flag is true | Medium |
| TC-12 | Two members reserve the last copy concurrently | Exactly one reservation succeeds | Critical |
| TC-13 | Request another member's booking by ID | No data leakage; return 403 or 404 per agreed policy | High |
| TC-14 | Fetch current member's bookings | Only authenticated member's bookings returned | High |
| TC-15 | Unknown booking ID on borrow/return/cancel | Rejected with 404 | Medium |

## Execution record

Record build/commit, tester, date, actual result, evidence link and Pass/Fail for each case during execution. Do not mark cases passed until run against the integrated application.
