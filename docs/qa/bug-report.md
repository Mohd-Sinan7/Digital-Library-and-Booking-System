# Bug Report Log & Cross-Module Integration Report (DLBS-55)

**Document ID:** DLBS-QA-BR-01  
**Project:** Digital Library and Booking System (DLBS)  
**QA Lead:** Marreddy Rushieswar Reddy (Member 4, SRN: PES1UG24AM158)  
**Jira Card:** DLBS-55 — Integration tests and bug reporting  
**Bug Report Standard:** Title, Severity, Affected Requirement, Owner, Steps to Reproduce, Expected vs. Actual Result, Fix & Retest Verification (`To Do -> In Progress -> In Review -> Done`)

---

## 1. Cross-Module Integration Test Scope & Smoke Results

Automated end-to-end integration tests (`tests/test_integration_e2e.py`) verify every module connected together over the real FastAPI app (`src.main.create_app`) and shared SQLAlchemy database (`src.db.SessionLocal`):

1. **First Smoke Test (`test_smoke_test_login_search_and_reserve`):** `GET /health` $\rightarrow$ Admin login + Catalog book creation (`POST /api/books`) $\rightarrow$ Member register/login (`POST /api/auth/login`) $\rightarrow$ Search (`GET /api/books?q=...`) $\rightarrow$ Reserve (`POST /api/bookings`) $\rightarrow$ Catalog availability synchronized (`GET /api/books/{id}/availability`).
2. **Full 5-Module Flow (`test_e2e_full_journey_login_search_reserve_borrow_return_read_recommend`):** Login $\rightarrow$ Search $\rightarrow$ Reserve $\rightarrow$ Borrow (`due_date = +14 days`) $\rightarrow$ Return (`available_copies` restored) $\rightarrow$ Reading status/progress (`PUT /api/reading/status`, `POST /api/reading/progress`, `GET /api/reading/stats`) $\rightarrow$ Personalized recommendations (`GET /api/recommendations/me`).
3. **Soft-Deleted Book Lifecycle (`test_e2e_soft_deleted_book_blocks_reserve_but_allows_return`):** Soft-deleted catalog items reject new bookings (`409`) while allowing existing loans to return safely.
4. **Concurrency & Inventory Atomicity (`test_e2e_concurrent_last_copy_atomic_with_shared_db`):** 8 barrier-synchronized threads competing for 1 copy against shared database produce strictly 1 winner and `available_copies = 0`.
5. **On-Read Hold Expiry & Overdue Detection (`test_e2e_hold_expiry_and_overdue_flag_with_shared_catalog`):** Stale >2-day holds expire on read and restore real catalog copies; loans past `due_date` report `overdue = true`.
6. **Active Booking Allowance & Role Isolation (`test_e2e_cancel_restores_catalog_and_respects_5_booking_limit`, `test_e2e_role_and_user_isolation_across_modules`):** Validates 5-booking cap, cancellation copy restoration, 401/403 RBAC, and cross-user isolation.

---

## 2. Formal Jira Bug Log (Sprints 1 & 2 Integration & Hardening)

### BUG-07 (Caught in DLBS-55 Integration Testing)
- **Title:** Live app reservation returns HTTP 404 for catalog books due to disconnected `:memory:` SQLite connection
- **Severity:** **Critical / Blocker**
- **Affected Requirements:** FR-B1, FR-B5, FR-B9, NFR-B1 (Booking $\leftrightarrow$ Catalog Integration)
- **Owner:** Marreddy Rushieswar Reddy (Member 4)
- **Steps to Reproduce:**
  1. Start `src.main.app` (e.g., via Docker or `TestClient(create_app())`).
  2. Log in as Admin and create a book via `POST /api/books` (book ID `1` created in `books` table via `SessionLocal`).
  3. Log in as Member and reserve book ID `1` via `POST /api/bookings` `{"book_id": 1}`.
- **Expected Result:** HTTP `201 Created`, booking persisted in `bookings` table, and `books.available_copies` decremented by `1` in Catalog.
- **Actual Result:** HTTP `404 Not Found` (`"Book 1 not found in catalog."`) because `src/bookings/routes.py` initialized an isolated raw `:memory:` SQLite `BookingService()` instead of querying `src.db.SessionLocal` and calling `catalog.get_availability` / `catalog.change_available_copies`.
- **Root Cause:** Early Sprint 1 booking storage used standalone raw `sqlite3` `:memory:` connection; routes had not been switched to the shared SQLAlchemy session layer for runtime traffic.
- **Fix Applied:** Implemented `SessionBookingService` (`src/bookings/session_service.py`) using `src.db.SessionLocal`, `BookingRow`, `catalog.get_availability`, and `catalog.change_available_copies` (with PostgreSQL `FOR UPDATE` + thread lock), and wired `get_booking_service()` in `src/bookings/routes.py` to default to `SessionBookingService()` while preserving `set_booking_service()` for isolated unit tests.
- **Retest Verification & Status:** Verified by `tests/test_integration_e2e.py` (all 7 cross-module tests green) and regression run of existing unit tests $\rightarrow$ **Done / Closed**.

---

### Summary Defect Register (BUG-01 through BUG-07)

| Bug ID | Severity | Module | Summary | Steps / Root Cause | Fix & Retest Verification | Workflow Status |
|---|---|---|---|---|---|---|
| **BUG-01** | Critical | Booking | Double booking under concurrent burst on final copy | Non-serialized SQLite reads before decrements | Added `RLock` + `BEGIN IMMEDIATE` / `FOR UPDATE` locking. Retested with 8 & 20 concurrent threads (`test_concurrency_performance.py`, `test_integration_e2e.py`). | **Done** |
| **BUG-02** | High | Booking | Double return/cancel incremented copies multiple times | Missing state machine check before stock update | Added `validate_status_transition` rejecting duplicate returns/cancellations (`409`). Retested in `test_booking_rules.py`. | **Done** |
| **BUG-03** | High | Booking | User with 3 reserved + 2 borrowed allowed 6th reserve | Active booking query ignored `borrowed` status | Count now sums `reserved` + `borrowed`. Retested in `TC-B19` and `test_e2e_cancel_restores_catalog_and_respects_5_booking_limit`. | **Done** |
| **BUG-04** | Blocker | Catalog / Booking | Disconnected schema conventions in early Sprint 1 | Separate prototype book availability table | Aligned `BookingRow` and `Book.available_copies` via `catalog.get_availability` & `change_available_copies`. | **Done** |
| **BUG-05** | Medium | Recommender | Crash when cold-start user has zero reading records | `ContentBasedRecommender` assumed non-empty history | Added cold-start fallback to `PopularityRecommender`. Retested in `tests/recommender/`. | **Done** |
| **BUG-06** | Low | Catalog | Long multi-author strings truncated on insert | `VARCHAR(100)` column too narrow | Expanded `Book.author` to `String(1000)` / `Text`. Verified by `tests/catalog/test_long_authors.py`. | **Done** |
| **BUG-07** | Blocker | Booking $\leftrightarrow$ Catalog API | Live `POST /api/bookings` returned 404 against real catalog DB | `routes.py` defaulted to `:memory:` SQLite `BookingService` | Added `SessionBookingService` in `src/bookings/session_service.py` wired into `SessionLocal` & `catalog.service`. Verified by `tests/test_integration_e2e.py`. | **Done** |

---

## 3. QA Exit Decision for DLBS-55
- All cross-module workflows (`Auth -> Catalog -> Booking -> Reading -> Recommender`) verified end-to-end.
- Zero open Blocker, Critical, High, Medium, or Low integration defects.
- **Status:** **PASSED & READY FOR MERGE**.
