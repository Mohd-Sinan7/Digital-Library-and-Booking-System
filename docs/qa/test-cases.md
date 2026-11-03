# QA Test Cases: Sprint 1 and All-Module Test Specifications

**Document ID:** DLBS-QA-TC-01  
**Project:** Software Engineering Mini-Project — Digital Library and Booking System (DLBS)  
**QA Lead:** Marreddy Rushieswar Reddy (Member 4, SRN: PES1UG24AM158)  
**Standard Template:** `ID | Requirement | Preconditions | Steps | Expected Result | Actual Result | Status`

---

## 1. Booking and Borrowing Module (Member 4)

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

---

## 2. Book Catalog Module (Member 2)

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

---

## 3. Users and Reading Tracking Module (Member 3)

| ID | Requirement | Preconditions | Steps | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|---|
| **TC-U01** | FR-U1 | Email `newuser@example.com` not in database. | Send `POST /api/users/register` with valid name, email, password. | User created with HTTP 201; role set to `member`; password stored as bcrypt hash. | 201 Created; user inserted; hash verified. | **Pass** |
| **TC-U02** | FR-U1 | Email `existing@example.com` already registered. | Send `POST /api/users/register` with duplicate email. | Rejected with HTTP 409 Conflict. | 409 Conflict (`Email already registered`). | **Pass** |
| **TC-U03** | FR-U2 | Registered user exists in database. | Send `POST /api/users/login` with correct email and password. | HTTP 200 returned with valid JWT access token and user metadata. | 200 OK; signed bearer token returned. | **Pass** |
| **TC-U04** | FR-U2 | Registered user exists in database. | Send `POST /api/users/login` with incorrect password. | Rejected with HTTP 401 Unauthorized. | 401 Unauthorized (`Incorrect email or password`). | **Pass** |
| **TC-U05** | FR-U2 | User is logged in. | Send `POST /api/users/logout` with bearer token. | HTTP 204 No Content; client instructed to discard token. | 204 No Content. | **Pass** |
| **TC-U06** | FR-U3 | Admin and Member accounts created in system. | Inspect role field in database and JWT payload. | Admin role is `admin`; regular member role is `member`. | Enforced by `ck_users_role` constraint and JWT claims. | **Pass** |
| **TC-U07** | FR-U5 | Member logged in; book exists in catalog. | Set reading status to `want_to_read`, then `reading`, then `finished`. | Reading record created/updated with matching status. | Record updated in `reading_records` table. | **Pass** |
| **TC-U08** | FR-U6 | Book has `page_count = 300`; member sets `current_page = 150`. | Update progress via `reading.update_progress(user_id, book_id, 150)`. | `percent` calculated as `50.0%`; `current_page = 150`. | Progress recorded with exact percentage (50.0%). | **Pass** |
| **TC-U09** | FR-U7 | Member has 3 reading records in database. | In-process call `reading.get_history(user_id)`. | Returns list of reading history records with status, current page, and percent. | 3 records returned matching user history. | **Pass** |
| **TC-U10** | NFR-U1 | User registration performed. | Inspect `users.password_hash` column in database. | Raw password is never stored; bcrypt hash string ($2b$...) present. | Salted bcrypt hash verified. | **Pass** |
| **TC-U11** | NFR-U3 | Register payload contains password shorter than 8 characters. | Send `POST /api/users/register` with `pwd="123"`. | Rejected with HTTP 422 / ValueError (password too short). | Rejected: `Password must be at least 8 characters`. | **Pass** |

---

## 4. Recommendation Engine and Dataset Module (Member 1)

| ID | Requirement | Preconditions | Steps | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|---|
| **TC-R01** | FR-R3 | New user has zero reading history (cold-start). | Request recommendations for new user via `recommender.recommend(user_id, top_n=5)`. | Popularity-based fallback returns top 5 globally popular books. | Top 5 popular books returned with popularity score and explanation. | **Pass** |
| **TC-R02** | FR-R2 | User requests recommendations. | Inspect returned recommendation objects. | Each recommendation contains `book_id`, `score` (float), and `reason` (string). | Frozen dataclass `Recommendation` validated with score and human reason. | **Pass** |
| **TC-R03** | NFR-R2 | Custom or baseline recommender implemented. | Verify algorithm class inherits from `BaseRecommender`. | Implements abstract methods `fit(data)` and `recommend(user_id, top_n)`. | Consistent interface adherence verified. | **Pass** |
| **TC-R04** | FR-R5 | Dataset generation script executed (`scripts/prepare_dataset.py`). | Run `prepare_dataset.py` and inspect `data/books.csv`, `data/users.csv`, `data/reading_records.csv`. | All files present, correctly structured, foreign keys align (`book_id`, `user_id`). | Validated by `tests/test_dataset.py` (5 tests passed). | **Pass** |

---

## 5. Execution Summary and Quality Gate Results

- **Total Test Cases Specified:** 42 test cases across 4 modules.
- **Automated Tests Executed:** 142 automated tests passing in test suite (`tests/`).
- **Regression Pass Rate:** **100% (142 / 142 passed)**.
- **Critical Defects Open:** **0**.
- **Module Coverage:**
  - `src/bookings`: **93%** (exceeds $\ge 70\%$ requirement).
  - `src/users`: **91%**.
  - `src/catalog`: **88%**.
  - `src/recommender`: **89%**.
- **Overall System Status:** **GREEN / Ready for Sprint 1 Acceptance**.
