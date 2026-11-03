# Sprint 1 report

DRAFT, figures from Jira (nsmr.atlassian.net, board 35) at 2 Nov 2026, 22:30 IST.
Refresh the table on 3 Nov just before closing the sprint, then delete this line.

| Item | Value |
|---|---|
| Sprint | DLBS Sprint 1 (Jira sprint 43) |
| Dates | 30 Oct 2026 23:59 IST to 3 Nov 2026 12:00 IST |
| Goal | Foundation: login and roles, user and reading tables, book catalog CRUD and search, reserve, borrow, return and cancel, baseline recommender with cold start, CI pipeline v1 (build and lint) |
| Committed | 20 cards, 73 story points |
| Done | 14 cards, 54 points (74%) |
| Not done | 6 cards, 19 points |

## Completed

| Card | Owner | Points | Evidence |
|---|---|---:|---|
| DLBS-7 Recommender skeleton and interface | Sinan | 3 | PR #7 |
| DLBS-8 Dataset preparation | Sinan | 5 | PR #11 |
| DLBS-18 Book table, model, availability function | Rishyendra | 3 | PR #4, #6 |
| DLBS-19 Search and pagination | Rishyendra | 5 | PR #4, #6 |
| DLBS-21 Admin CRUD with validation | Rishyendra | 5 | PR #13 |
| DLBS-22 CRUD unit tests (catalog coverage 98%) | Rishyendra | 3 | PR #13 |
| DLBS-33 User table | Sai | 2 | PR #6 |
| DLBS-34 Registration, login, JWT auth | Sai | 5 | PR #14 |
| DLBS-35 CI pipeline v1 | Sai | 3 | PR #2 |
| DLBS-36 Reading table and history function | Sai | 4 | PR #16 |
| DLBS-45 Bookings table and state rules | Rushi | 3 | |
| DLBS-46 Reserve with transaction safety | Rushi | 5 | PR #10 |
| DLBS-48 Test plan and Sprint 1 test cases | Rushi | 3 | |
| DLBS-49 Borrow, return, cancel | Rushi | 5 | PR #12 |

## Not completed (carry over or finish before close)

| Card | Owner | Points | Status on 2 Nov |
|---|---|---:|---|
| DLBS-9 Baseline popularity recommender | Sinan | 5 | In Progress |
| DLBS-10 Recommendation endpoint and API tests | Sinan | 5 | In Progress |
| DLBS-20 Sprint 1 demo video | Rishyendra | 1 | To Do, blocked by missing `src/main.py` |
| DLBS-37 Roles and admin-only decorator | Sai | 3 | In Progress (branch `feature/DLBS-37-roles` not merged) |
| DLBS-47 Seed script for books | Rushi | 2 | In Progress |
| DLBS-50 Booking limit and remaining tests | Rushi | 3 | In Progress |

## Test evidence

On `main` at 2 Nov: `ruff check --line-length 100 --select E,F,W,I .` passes and `pytest` runs
137 tests, all passing. Catalog coverage (`--cov=src/catalog`) is 98%.

## Integration check (2 Nov)

All four routers mounted in one app: register 201, login 200, catalog search 200,
recommendations 200. Reserve returned 404 because booking reads its own `books` table
instead of the catalog. See blockers in `docs/standup-log.md`.

## Burndown

Screenshot: `sprint-1-burndown.png` (Jira: Reports > Burndown chart > DLBS Sprint 1).

## Retrospective (fill in at the review on 3 Nov)

| What went well | What to improve | Action for Sprint 2 (owner) |
|---|---|---|
| | | |
| | | |
