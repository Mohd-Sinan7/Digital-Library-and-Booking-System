# Requirements Traceability Matrix

| Requirement | Description | Test cases | Status |
|---|---|---|---|
| FR-B1 / BR-01 | Signed-in member can reserve; available copies drop by 1; removed book rejected | TC-01, TC-03, TC-16 | Passed |
| FR-B2 | Status becomes borrowed, due date is 14 days after borrowing, available copies unchanged | TC-B01 | Passed |
| FR-B3 | Status becomes returned and available copies rise by one; returning a non-borrowed booking rejected | TC-B03 | Passed |
| FR-B4 | Status becomes cancelled and available copies rise by one; a borrowed booking cannot be cancelled | TC-B05 | Passed |
| FR-B5 | Counts checked after every action in TC-B01, TC-B03, TC-B05 and TC-B08 | TC-B01, TC-B03, TC-B05, TC-B08 | Passed |
| FR-B9 / BR-02 | Copy must be available; 0 copies returns 409 and changes nothing | TC-01, TC-02, TC-17 | Passed |
| NFR-B1 / BR-12| In concurrent test exactly one reservation succeeds; copies never < 0 | TC-12 | Passed |
| BR-03 | Maximum five active bookings | TC-04 | Passed |
| BR-04 | Booking belongs to member and book | TC-01, TC-13, TC-14 | Passed |
| BR-05 | Only reserved booking can be borrowed | TC-05, TC-06 | Passed |
| BR-06 | Due date is 14 days after borrowing | TC-05, TC-B01 | Passed |
| BR-07 | Only borrowed booking can be returned | TC-07, TC-08, TC-B03 | Passed |
| BR-08 | Return restores stock once; repeated return does not increment stock | TC-07, TC-08, TC-B03 | Passed |
| BR-09 | Only reserved booking can be cancelled; restores stock once | TC-09, TC-10, TC-B05 | Passed |
| BR-10 | Overdue detection | TC-11 | Passed |
| BR-11 | Terminal statuses are not active | TC-04, TC-06, TC-10 | Passed |
| BR-13 | Protected endpoints require authentication (401 without token) | TC-03, TC-13, TC-14 | Passed |
