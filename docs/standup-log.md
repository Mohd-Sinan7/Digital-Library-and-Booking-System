# Stand-up log

Daily 10-minute stand-up, run by the Scrum Master (Member 2). Three questions each:
what did you finish, what is next, what is blocking you. Write blockers as
`BLOCKER:` with the person chasing it, and close them in a later entry.

| Member | Name | Module |
|---|---|---|
| 1 | Mohammed Sinan M T | Recommendation Engine |
| 2 | M Rishyendra | Book Catalog, app shell, home page; Scrum Master |
| 3 | Nagalapuram Sai Mukesh Reddy | Users and Reading Tracking; DevOps |
| 4 | Rushi Eswar | Booking and Borrowing; QA |

---

## Sprint 1

### 31 Oct 2026

| Member | Finished | Next | Blockers |
|---|---|---|---|
| 1 Sinan | | | |
| 2 Rishyendra | DLBS-18, DLBS-19 merged to `main` (PR #4, #6); 27 tests pass | DLBS-21, DLBS-22 admin CRUD | |
| 3 Sai | | | |
| 4 Rushi | | | |

Notes:
-

### 1 Nov 2026

| Member | Finished | Next | Blockers |
|---|---|---|---|
| 1 Sinan | DLBS-8 dataset merged (PR #11) | | |
| 2 Rishyendra | DLBS-21, DLBS-22 admin CRUD merged (PR #13) | Sprint 1 report, demo | |
| 3 Sai | DLBS-34 login merged (PR #14) | | |
| 4 Rushi | DLBS-49 borrow, return, cancel merged (PR #12) | | |

### 2 Nov 2026

| Member | Finished | Next | Blockers |
|---|---|---|---|
| 1 Sinan | | | |
| 2 Rishyendra | Sprint 1 report draft | Sprint 1 demo (DLBS-20), Sprint 2 app shell (DLBS-23) | Needs `src/main.py` |
| 3 Sai | DLBS-36 reading history merged (PR #16) | | |
| 4 Rushi | | | |

Blockers:
- BLOCKER: no `src/main.py`, so the app cannot start and the Sprint 1 demo cannot be recorded. Owner: Sai. Needed by 3 Nov 10:00.
- BLOCKER: booking keeps its own `books` table in a separate SQLite connection. Reserving a catalog book returns 404 "Book 9 not found in catalog" (checked 2 Nov with all routers mounted). Fix: booking calls `catalog.get_availability()` and `catalog.change_available_copies()`. Owner: Rushi.

Notes:
- Team Jira is nsmr.atlassian.net (board 35). Commit keys must use that site's card numbers.

