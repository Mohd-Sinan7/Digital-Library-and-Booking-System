# QA Test Cases: Sprint 1 and Sprint 2 Full-Module Test Specifications

**Document ID:** DLBS-QA-TC-01  
**Project:** Software Engineering Mini-Project — Digital Library and Booking System (DLBS)  
**QA Lead:** Marreddy Rushieswar Reddy (Member 4, SRN: PES1UG24AM158)  
**Planned Period:** Sprint 1 (29 Oct – 2 Nov 2026) & Sprint 2 (3 Nov – 8 Nov 2026)  
**Standard Template:** `ID | Requirement | Preconditions | Steps | Expected Result | Actual Result | Status`

---

## 1. Booking and Borrowing Module (Member 4 — Marreddy Rushieswar Reddy)

| ID | Requirement | Preconditions | Steps | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|---|
| **TC-B01** | FR-B1 | Book with `available_copies = 1` exists in catalog; user authenticated as `member` with 0 active bookings. | Log in as member, reserve the book via `POST /api/bookings` with `{book_id: X}`. | Booking created with status `reserved`; `available_copies` becomes 0. | Booking created with status `reserved`; `available_copies` dropped to 0 (HTTP 201). | **Pass** |
| **TC-B02** | FR-B9 | Book has `available_copies = 0`; second user authenticated as `member`. | Second member attempts to reserve the same book via `POST /api/bookings` with `{book_id: X}`. | Rejected with HTTP 409 Conflict; clear error message; availability unchanged at 0. | Rejected with 409 Conflict: `No copies of ... are currently available`. | **Pass** |
| **TC-B03** | FR-B3 | User has an active booking with status `borrowed`; book has `available_copies = 0`. | Member calls `POST /api/bookings/{id}/return`. | Status transitions to `returned`; `available_copies` rises by 1 (becomes 1). | Status transitions to `returned`; `available_copies` restored to 1 (HTTP 200). | **Pass** |
| **TC-B04** | FR-B8 | Member currently holds 5 active bookings (`reserved` or `borrowed`). | Member attempts to reserve a 6th book via `POST /api/bookings`. | Rejected with HTTP 409 Conflict; error indicates maximum limit of 5 reached. | Rejected with 409 Conflict: `A member may have at most 5 active bookings`. | **Pass** |
| **TC-B05** | FR-B10 | Book reserved 2 days ago; not borrowed; current time past `expires_at`. | System/user reads or triggers expiration on booking past 2 calendar days. | Status transitions to `expired`; `available_copies` restored by +1. | Status becomes `expired`; available copies incremented by 1. | **Pass** |
| **TC-B06** | FR-B2 | Member holds booking with status `reserved`. | Member calls `POST /api/bookings/{id}/borrow`. | Status becomes `borrowed`; `due_date` set to 14 calendar days ahead; `available_copies` unchanged. | Status `borrowed`; `due_date` = +14 days; copy count unchanged (HTTP 200). | **Pass** |
| **TC-B07** | FR-B4 | Member holds booking with status `reserved`; book copies count is $N$. | Member calls `DELETE /api/bookings/{id}`. | Status becomes `cancelled`; `available_copies` rises to $N + 1$. | Status `cancelled`; copies restored to $N + 1$ (HTTP 200). | **Pass** |
| **TC-B08** | FR-B5 | Clean catalog book with 5 total copies. | Sequence of actions: 1. Reserve, 2. Borrow, 3. Return, 4. Re-reserve, 5. Cancel. Verify copies at each step. | Counts verified: 5 $\rightarrow$ 4 $\rightarrow$ 4 $\rightarrow$ 5 $\rightarrow$ 4 $\rightarrow$ 5. | Exact copy counts verified after every lifecycle mutation. | **Pass** |
| **TC-B09** | NFR-B1 | Book has exactly 1 available copy; 10 concurrent reservation threads launched. | Concurrently dispatch 10 reservation requests using `ThreadPoolExecutor`. | Exactly 1 reservation succeeds; 9 fail with 409; `available_copies` never drops below 0. | Exactly 1 success (201); 9 conflicts (409); copies = 0. No double booking. | **Pass** |
| **TC-B10** | BR-05 | Booking is in status `cancelled` or `returned`. | Attempt to borrow the inactive booking via `POST /api/bookings/{id}/borrow`. | Rejected with HTTP 409 Conflict; only reserved bookings can be borrowed. | Rejected with 409 Conflict: `Only a reserved booking can be borrowed`. | **Pass** |
| **TC-B11** | BR-07 | Booking is in status `reserved` (not yet borrowed). | Attempt to return the unborrowed booking via `POST /api/bookings/{id}/return`. | Rejected with HTTP 409 Conflict; only borrowed bookings can be returned. | Rejected with 409 Conflict: `Only a borrowed booking can be returned`. | **Pass** |
| **TC-B12** | BR-08 | Booking was already returned (`status = returned`). | Attempt to return the same booking a second time via `POST /api/bookings/{id}/return`. | Second return rejected with 409; copy count does NOT increment a second time. | Rejected with 409 Conflict; stock restored only once. | **Pass** |
| **TC-B13** | BR-09 | Booking is in status `borrowed`. | Attempt to cancel the active loan via `DELETE /api/bookings/{id}`. | Rejected with HTTP 409 Conflict; borrowed books must be returned, not cancelled. | Rejected with 409 Conflict: `Only a reserved booking can be cancelled`. | **Pass** |
| **TC-B14** | FR-B1 | Book is marked `is_deleted = True` in catalog. | Authenticated member attempts to reserve the removed book. | Rejected with HTTP 409 Conflict; cannot reserve a removed book. | Rejected with 409 Conflict: `Cannot reserve a removed book`. | **Pass** |
| **TC-B15** | BR-13 | Client has no `Authorization: Bearer <token>` header. | Send `POST /api/bookings` with valid book payload. | Request rejected with HTTP 401 Unauthorized. | Rejected with HTTP 401 Unauthorized (`Not authenticated`). | **Pass** |
| **TC-B16** | FR-B7 | User 1 has 3 bookings (1 reserved, 1 borrowed, 1 returned). | User 1 calls `GET /api/bookings/me` with bearer token. | Returns list of 3 bookings belonging to User 1, sorted newest first. | 200 OK; array of 3 booking objects matching User 1's ID. | **Pass** |
| **TC-B17** | BR-04 | User A tries to borrow or return User B's booking. | User A calls `POST /api/bookings/{id_of_user_b}/borrow`. | Rejected with HTTP 409 Conflict or 403 Forbidden. | Rejected with 409 Conflict (`Cannot borrow another member's booking`). | **Pass** |
| **TC-B18** | DLBS-47 | `data/books_sample.csv` exists with 20 books. | Execute `scripts/seed.py` via `seed_books(sample=True)` or CLI. | 20 books loaded via Member 2's `create_book`; shared `book_id` preserved as primary key `id`; idempotency skips existing on re-run. | 20 books loaded; `Book.id == CSV book_id`; re-run skips without duplicate error. | **Pass** |
| **TC-B19** | FR-B8 / DLBS-50 | Member holds mixed active bookings (e.g. 3 reserved and 2 borrowed). | Member attempts 6th booking via `POST /api/bookings`; returns 1 book and retries. | 6th attempt rejected with HTTP 409 Conflict; after return, reservation succeeds (HTTP 201). | Rejected with 409 Conflict: `A member may have at most 5 active bookings`; succeeds after return. | **Pass** |
| **TC-B20** | FR-B2 / DLBS-51 | Member borrows reserved book on 30 Oct 2026. | Call `calculate_due_date(date(2026, 10, 30))`. | Due date strictly computed as 14 calendar days ahead (13 Nov 2026). | Exact date verified as 2026-11-13; loan duration = 14 days. | **Pass** |
| **TC-B21** | FR-B6 / DLBS-51 | Booking has due date in past (`due_date < today`). | Inspect `Booking.is_overdue` property on read. | `is_overdue` evaluates to `True` for borrowed booking with past due date. | Evaluates dynamically without requiring background cron worker. | **Pass** |
| **TC-B22** | FR-B7 / DLBS-51 | Member with multiple past and current loans accesses personal bookings. | Call `GET /api/bookings/me` with JWT header. | Payload includes status badge metadata, formatted timestamps, and due dates. | 200 OK; full booking history array returned with correct badges. | **Pass** |
| **TC-B23** | FR-B10 / DLBS-51 | Reservation placed on 1 Nov 2026 at 10:00 UTC. | Advance simulated time past 3 Nov 2026 10:00 UTC (> 2 days hold). | Hold expires automatically; status transitions to `expired`; copy restored. | Expired status dynamically confirmed and catalog copy restored. | **Pass** |
| **TC-B24** | DLBS-56 | Full test suite executed with coverage measurement. | Execute `pytest --cov=src --cov-report=term-missing` and review RTM. | 100% of functional requirements covered; test summary documented. | All 372 tests passing; 97% overall coverage; QA sign-off complete. | **Pass** |
| **TC-B25** | NFR-B1 | High contention test: 1 available copy with 20 parallel threads. | Concurrently dispatch 20 `reserve_book` calls via `ThreadPoolExecutor`. | Exact atomicity maintained: 1 reservation succeeds, 19 rejected with 409, copy = 0. | Verified: 1 success, 19 conflicts, available copies = 0, no inventory negative underflow. | **Pass** |

---

## 2. Book Catalog Module (Member 2 — Mallela Rishyendra)

| ID | Requirement | Preconditions | Steps | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|---|
| **TC-C01** | FR-C1 | Authenticated user has role `admin`. | Send `POST /api/catalog` with valid book fields (`title`, `author`, `isbn`, `genre`, `page_count`, `total_copies`). | Book created with HTTP 201; `available_copies` initialized equal to `total_copies`. | 201 Created; book stored with matching initial availability. | **Pass** |
| **TC-C02** | FR-C8 | Authenticated user has role `member`. | Member attempts to create book via `POST /api/catalog`. | Rejected with HTTP 403 Forbidden. | 403 Forbidden (`Admin access required`). | **Pass** |
| **TC-C03** | FR-C8 | Unauthenticated client (no token). | Client attempts `POST /api/catalog`. | Rejected with HTTP 401 Unauthorized. | 401 Unauthorized. | **Pass** |
| **TC-C04** | FR-C2 | Book exists in catalog; authenticated as `admin`. | Send `PUT /api/catalog/{id}` with updated `title` and `author`. | Book updated; HTTP 200 returned with updated fields. | 200 OK; fields updated in database. | **Pass** |
| **TC-C05** | FR-C3 | Book exists in catalog; authenticated as `admin`. | Send `DELETE /api/catalog/{id}`. | Soft delete applied (`is_deleted=True`); HTTP 204 No Content; row retained in DB. | 204 No Content; `is_deleted` flag set to True. | **Pass** |
| **TC-C06** | FR-C4 | Catalog populated with sample books. | Send `GET /api/catalog?search=Python`. | Returns books matching "Python" in title, author, or ISBN. | 200 OK; matching results returned. | **Pass** |
| **TC-C07** | FR-C5 | Catalog populated with varied genres. | Send `GET /api/catalog?genre=Fiction&available_only=true`. | Only non-deleted fiction books with `available_copies > 0` returned. | 200 OK; filtered subset returned. | **Pass** |
| **TC-C08** | FR-C6 | Valid non-deleted book ID exists. | Send `GET /api/catalog/{id}`. | HTTP 200 with full book details (`page_count`, `isbn`, `available_copies`). | 200 OK; complete book payload returned. | **Pass** |
| **TC-C09** | FR-C6 | Book was soft-deleted (`is_deleted=True`) or ID does not exist. | Send `GET /api/catalog/{id}`. | HTTP 404 Not Found. | 404 Not Found (`Book not found`). | **Pass** |
| **TC-C10** | FR-C7 | Catalog contains 45 books. | Send `GET /api/catalog?page=1&page_size=20`. | Returns 20 items for page 1; `total_pages = 3`. | 200 OK; pagination metadata and exact page items returned. | **Pass** |
| **TC-C11** | NFR-C2 | Admin payload contains negative `page_count` or `total_copies < 0`. | Send `POST /api/catalog` with invalid negative numbers. | Rejected with HTTP 422 Unprocessable Entity by Pydantic validation. | 422 Unprocessable Entity. | **Pass** |
| **TC-C12** | FR-C9 / DLBS-24 | Book ID exists with 3 available copies. | Send `GET /api/catalog/{id}/availability`. | HTTP 200 returned with `{book_id: X, available_copies: 3, total_copies: 3}`. | 200 OK; real-time availability payload returned. | **Pass** |
| **TC-C13** | FR-C10 / DLBS-23 | App server running. | Request root path `GET /` and inspect static assets. | HTML app shell delivered with navigation links, catalog container, and CSS/JS. | 200 OK; responsive interface rendered. | **Pass** |
| **TC-C14** | NFR-C2 | Book with author name longer than 100 characters added. | Send `POST /api/catalog` with 250-character author list. | Accepted without database column truncation error (TEXT type support). | 201 Created; full author string stored. | **Pass** |

---

## 3. Users and Reading Tracking Module (Member 3 — Nagalapuram Sai Mukesh Reddy)

| ID | Requirement | Preconditions | Steps | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|---|
| **TC-U01** | FR-U1 | `asha@example.com` is not registered. | Send `POST /api/auth/register` with a name, that email and the password `readmore42`. | 201 Created; role `member`; the response has no password or password hash. | 201 Created, role `member`, no password in the body (`test_register_creates_a_member`). | **Pass** |
| **TC-U02** | FR-U1 | `asha@example.com` is already registered. | Register again with `ASHA@example.com`. | 409 Conflict with `Email already registered`; emails are compared without letter case. | 409 with that message (`tests/users/test_auth.py::test_duplicate_email_is_rejected`). | **Pass** |
| **TC-U03** | FR-U1, NFR-U3 | None. | Register with an invalid email (`not-an-email`, `asha@`, `@example.com`), a weak password (`short1`, `onlyletters`, `12345678`) or an empty name. | 422 for each: a password needs 8 or more characters with a letter and a digit. | 422 for every case (`test_invalid_email_is_rejected`, `test_weak_password_is_rejected`, `test_missing_name_is_rejected`). | **Pass** |
| **TC-U04** | FR-U2 | Asha is registered. | Send `POST /api/auth/login` with her email (any letter case) and password, then call a protected endpoint with the token. | 200 OK with a bearer token that expires after 60 minutes (`expires_in` 3600) and her id, name, email and role; the token is accepted. | 200 OK; the token works on a protected endpoint (`test_login_returns_a_token_that_protected_endpoints_accept`). | **Pass** |
| **TC-U05** | FR-U2 | Asha is registered. | Log in with a wrong password, then with an unknown email. | 401 Unauthorized with the same message both times: `Invalid email or password`. | Same 401 message for both (`test_wrong_password_or_unknown_email_gets_the_same_401`). | **Pass** |
| **TC-U06** | FR-U2 | Asha is logged in. | Send `POST /api/auth/logout` with her token, then without a token. Click **Log out** in the web app. | 204 No Content with the token; 401 without one. The web app deletes the stored token. | 204 and 401 (`test_logout_needs_a_token`). | **Pass** |
| **TC-U07** | FR-U3 | `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set. | Start the app twice; register a user; call an admin-only endpoint as a member and as the admin. | One admin account is created; new users are members; a member gets 403 `Admin privileges required` and the admin gets 200. | As expected (`test_admin_account_is_created_from_the_environment`, `test_admin_account_is_created_only_once`, `test_member_is_rejected_from_admin_endpoints`, `test_admin_is_allowed`). | **Pass** |
| **TC-U08** | FR-U4 | Asha is logged in. | Send `GET /api/users/me`, then `PUT /api/users/me` with a new name, then with an email or role change. Open the Profile page. | GET returns id, name, email and role; PUT changes the name only; email or role changes get 422 and change nothing. The Profile page shows and edits the name. | As expected (`test_get_profile_returns_id_name_email_and_role`, `test_put_changes_the_name_only`, `test_invalid_profile_changes_are_422_and_change_nothing`, `tests/users/test_pages.py`). | **Pass** |
| **TC-U09** | FR-U5 | Asha is logged in; book 42 is in the catalog. | Send `PUT /api/reading/status` with `want_to_read`, `reading` and `finished`, then with an unknown status, then for an unknown book. | One record per user and book holds the latest status; an unknown status gets 422; an unknown or removed book gets 404 `Book not found`. | As expected (`test_set_status_creates_the_record_with_book_details`, `test_status_is_saved_per_user_and_book`, `test_unknown_status_is_422`, `test_unknown_or_removed_book_is_404`). | **Pass** |
| **TC-U10** | FR-U6 | Book 42 has 320 pages. | Send `POST /api/reading/progress` with `current_page` 120, then with `percent` 37.5. | Page 120 and 37.5% both ways; the status becomes `reading`. | 120 and 37.5% (`test_page_120_of_320_is_37_5_percent`, `test_percent_is_turned_into_a_page`, `test_progress_moves_want_to_read_to_reading`). | **Pass** |
| **TC-U11** | FR-U6 | Book 42 has 320 pages. | Send page -1, page 321, -0.5% and 100.5%; then page 320 or 100%. | Each invalid value gets 422 and saves nothing; page 320 or 100% marks the book `finished`. | As expected (`test_invalid_progress_is_422`, `test_progress_past_the_last_page_says_why`, `test_reaching_100_percent_marks_the_book_finished`). | **Pass** |
| **TC-U12** | FR-U7 | Asha has records for several books; a new user has none. | Send `GET /api/reading/history`; call `reading.get_history(user_id)` in-process; open My Reading. | Newest first, with title, author, genre, status and progress; a new user gets `[]`; `get_history` returns the same records for the recommender. My Reading lists them with a progress bar. | As expected (`test_history_is_newest_first_with_book_details`, `test_empty_history`, `tests/users/test_reading.py::test_history_is_newest_first_and_only_for_that_user`, `test_empty_history_for_a_user_with_no_records`). | **Pass** |
| **TC-U13** | FR-U8 | Asha has one finished book (400 pages), one at page 120 and one on her want-to-read list. | Send `GET /api/reading/stats`. | `books_finished` 1, `books_reading` 1, `books_want_to_read` 1 and `pages_read` 520; all zero for a new user. | As expected (`test_stats_count_books_by_status_and_sum_pages_read`, `test_stats_are_zero_without_records`, `test_stats_follow_status_and_progress_changes`). | **Pass** |
| **TC-S01** | NFR-U1 | None. | Register, then read `users.password_hash` from the database. | A bcrypt hash, never the password itself; the password checks against it. | bcrypt hash stored (`test_password_is_stored_hashed`, `test_verify_password_rejects_garbage_hash`). | **Pass** |
| **TC-S02** | NFR-U2 | None. | Call every protected endpoint (`/api/users/me`, `/api/reading/*`, `/api/auth/logout`) without a token. | 401 Unauthorized from each one. | 401 everywhere (`test_missing_token_is_rejected`, `test_profile_needs_a_token`, `test_reading_endpoints_need_a_token`, `test_logout_needs_a_token`). | **Pass** |
| **TC-S03** | NFR-U2 | None. | Call a protected endpoint with an expired token, a token signed with another key, a token without an expiry time, a malformed token and a `Basic` header. | 401 Unauthorized for each one. | 401 for each (`test_expired_token_is_rejected`, `test_invalid_tokens_are_rejected`). | **Pass** |
| **TC-Q01** | NFR-U4 | None. | Run `pytest tests/users --cov=src/users`. | Coverage of `src/users` is at least 70%. | 98% (322 of 329 statements), 112 tests passed on 9 Nov. | **Pass** |

---

## 4. Recommendation Engine and Dataset Module (Member 1 — Mohammed Sinan M T)

| ID | Requirement | Preconditions | Steps | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|---|
| **TC-R01** | FR-R3 | New user has zero reading history (cold-start). | Request recommendations for new user via `recommender.recommend(user_id, top_n=5)`. | Popularity-based fallback returns top 5 globally popular books. | Top 5 popular books returned with popularity score and explanation. | **Pass** |
| **TC-R02** | FR-R2 | User requests recommendations. | Inspect returned recommendation objects. | Each recommendation contains `book_id`, `score` (float), and `reason` (string). | Frozen dataclass `Recommendation` validated with score and human reason. | **Pass** |
| **TC-R03** | NFR-R2 | Custom or baseline recommender implemented. | Verify algorithm class inherits from `BaseRecommender`. | Implements abstract methods `fit(data)` and `recommend(user_id, top_n)`. | Consistent interface adherence verified. | **Pass** |
| **TC-R04** | FR-R8 / DLBS-8 | Dataset generation script executed (`scripts/prepare_dataset.py`). | Run `prepare_dataset.py` and inspect `data/books.csv`, `data/users.csv`, `data/reading_records.csv`. | All files present, correctly structured, foreign keys align (`book_id`, `user_id`). | Validated by `tests/test_dataset.py` (5 tests passed). | **Pass** |
| **TC-R05** | FR-R4 / DLBS-11 | User finished several books of one genre (e.g. Sci-Fi). | Request top 5 recommendations via `recommend(user_id, n=5)`. | At least 3 of top 5 share finished genre; finished/deleted books excluded. | Validated: >=3 of top 5 share genre, finished excluded, scores sorted descending. | **Pass** |
| **TC-R06** | FR-R5 / DLBS-12 | Hybrid recommender configured with weights $\alpha=0.7, \beta=0.3$. | Score candidate books combining TF-IDF content similarity and popularity. | Returns blended score and explainability string referencing similar finished titles. | Validated: composite score matches linear combination formula with clear rationale. | **Pass** |
| **TC-R07** | FR-R7 / DLBS-13 | Recommendation test split prepared with ground truth holdouts. | Run evaluation suite calculating Precision@K, Recall@K, and F1@K. | Precision and recall metrics computed according to standard ranking formulas. | Validated by `tests/recommender/test_evaluation.py` (17 tests passed). | **Pass** |

---

## 5. Cross-Cutting, CI/CD, and Deployment (Member 3 & Whole Team)

| ID | Requirement | Preconditions | Steps | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|---|
| **TC-D01** | DLBS-16 | Pull Request created or commit pushed. | GitHub Actions CI runner triggered on Ubuntu container. | Installs dependencies, runs compile check, executes ruff lint, runs pytest. | Build green; pipeline exits with code 0 on valid PRs. | **Pass** |
| **TC-D02** | DLBS-41 | CI test step executes with coverage gate set to 70%. | Run `pytest --cov=src --cov-fail-under=70`. | Total statement coverage exceeds 70%; gate passes. | Total coverage 96% on 9 Nov (372 tests); gate passes. | **Pass** |
| **TC-D03** | DLBS-42 | Docker is running. | Run `docker compose up --build --wait`, then `python scripts/smoke_test.py http://localhost:8000`. | The app and PostgreSQL 16 start, the tables are created, the books load in the background, and `GET /health` answers `{"status": "ok"}`. | Passes in the CI `docker` job on every push; `tests/test_start.py` (11 tests) and `tests/test_smoke_test.py` (10 tests) pass. | **Pass** |
| **TC-D04** | DLBS-43 | `main` has a finished CI run. | Open `docs/cicd.md` and `README.md` on GitHub. | The diagram shows the `ci`, `docker` and `deploy` jobs; the badge shows the latest result on `main`. | The diagram renders and the badge shows the result. | **Pass** |
| **TC-D05** | DLBS-42 | The Render service is set up; the `RENDER_DEPLOY_HOOK_URL` secret and the `APP_URL` variable are added on GitHub. | Merge a pull request to `main`, or **Actions** → **CI** → **Run workflow**. | The `deploy` job deploys that commit, and the live `GET /health` answers ok with that commit in `X-App-Version`. | Not run yet: Render is not set up, so the `deploy` job skips with a warning. | **Not run** |

---

## 6. Execution Summary and Release Quality Gate Results


- **Critical Defects Open:** **0**.
- **Module Statement Coverage:**
  - `src/bookings`: **97%** (Target: $\ge 70\%$, NFR-B3)
  - `src/catalog`: **97%**
  - `src/users`: **98%**
  - `src/recommender`: **93%**
  - `src/db.py` & `src/main.py`: **100%**
  - **Overall Project Statement Coverage:** **97%** (1436 statements covered).
- **Quality Gate Assessment:** **APPROVED / READY FOR SPRINT 2 CLOSE & HARDENING REHEARSAL**.
