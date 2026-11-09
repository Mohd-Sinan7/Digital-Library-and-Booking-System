# Requirements Traceability Matrix (RTM)

**Document ID:** DLBS-QA-RTM-01  
**Project:** Software Engineering Mini-Project — Digital Library and Booking System (DLBS)  
**QA Lead:** Marreddy Rushieswar Reddy (Member 4, SRN: PES1UG24AM158)  
**Planned Period:** Sprint 1 (29 Oct – 2 Nov 2026) & Sprint 2 (3 Nov – 8 Nov 2026)  
**Status:** All Sprint 1 & Sprint 2 Requirements Verified, Fully Traced, and Passed  

---

## 1. Traceability Overview and Methodology

The Requirements Traceability Matrix (RTM) ensures complete bi-directional visibility from user-level requirements defined in the Software Requirements Specification (SRS) and System Architecture Document (SAD) to their exact architectural components, source code implementations, automated verification test cases, sprint delivery milestones, and quality gate outcomes.

### 1.1 Traceability Schema
Each requirement is tracked with:
1. **Requirement ID:** Standardized SRS identifier (e.g., `FR-B1`, `NFR-B1`, `FR-C1`, `FR-U1`, `FR-R1`) and Jira delivery keys.
2. **Module & Owner:** Application module and the responsible team member.
3. **Requirement Description:** Concise functional or non-functional capability statement.
4. **Code Implementation Location:** Exact source files, classes, methods, or route handlers implementing the requirement.
5. **Automated Test Cases:** Test case IDs (from `docs/qa/test-cases.md`) and corresponding automated pytest test functions in `tests/`.
6. **Sprint Allocation:** Sprint 1 (Foundation) or Sprint 2 (Features & Integration).
7. **Verification Result:** Verification status based on the full regression test suite run.

---

## 2. Master Requirements Traceability Table

### 2.1 Book Catalog Module (Member 2 — Mallela Rishyendra)

| Requirement ID | Module | Description | Code Location | Test Case IDs & Test Functions | Sprint | Result |
|---|---|---|---|---|---|---|
| **FR-C1** | Book Catalog | Admin can add books; available copies initialized equal to total copies | `src/catalog/service.py:create_book`, `src/catalog/routes.py` | TC-C01, `test_create_book`, `test_create_book_success` | Sprint 1 | **Passed** |
| **FR-C2** | Book Catalog | Admin can edit any subset of book fields | `src/catalog/service.py:update_book`, `src/catalog/routes.py` | TC-C04, `test_update_book`, `test_update_book_partial` | Sprint 1 | **Passed** |
| **FR-C3** | Book Catalog | Admin can soft-delete books (`is_deleted=True`), preserving reading and booking records | `src/catalog/service.py:delete_book`, `src/catalog/routes.py` | TC-C05, `test_delete_book`, `test_soft_delete_preserves_records` | Sprint 1 | **Passed** |
| **FR-C4** | Book Catalog | Search books across title, author, or ISBN | `src/catalog/service.py:list_books` | TC-C06, `test_search_catalog`, `test_search_by_isbn` | Sprint 1 | **Passed** |
| **FR-C5** | Book Catalog | Filter books by genre and availability (`available_copies > 0`) | `src/catalog/service.py:list_books` | TC-C07, `test_filter_by_genre`, `test_filter_available_only` | Sprint 1 | **Passed** |
| **FR-C6** | Book Catalog | View book detail; 404 for deleted or nonexistent books | `src/catalog/service.py:get_book`, `src/catalog/routes.py` | TC-C08, TC-C09, `test_get_book`, `test_get_deleted_book_returns_404` | Sprint 1 | **Passed** |
| **FR-C7** | Book Catalog | Paginated catalog listing with configurable limit/offset | `src/catalog/service.py:list_books` | TC-C10, `test_pagination`, `test_pagination_bounds` | Sprint 1 | **Passed** |
| **FR-C8** | Book Catalog | Role authorization: mutating catalog endpoints require admin privileges (HTTP 401/403) | `src/catalog/routes.py:require_admin` | TC-C02, TC-C03, `test_admin_auth`, `test_member_mutation_rejected` | Sprint 1 | **Passed** |
| **FR-C9** (DLBS-24) | Book Catalog | Availability endpoint returning real-time available copy count | `src/catalog/routes.py:get_availability` | TC-C12, `test_availability_success`, `test_availability_404` | Sprint 2 | **Passed** |
| **FR-C10** (DLBS-23) | Book Catalog | Responsive web UI app shell and catalog browsing navigation | `src/web/index.html`, `src/web/js/app.js`, `src/web/css/app.css` | TC-C13, `test_app_shell_routes`, `test_main_mounts_static` | Sprint 2 | **Passed** |
| **NFR-C1** | Book Catalog | Search and catalog queries respond in under 1 second (< 50ms measured) | `src/catalog/service.py` | `test_catalog_latency` | Sprint 1 | **Passed** |
| **NFR-C2** | Book Catalog | Input validation on book attributes (page_count >= 1, copies >= 0, long authors) | `src/catalog/schemas.py`, `src/catalog/models.py` | TC-C11, `test_invalid_book_payload`, `tests/catalog/test_long_authors.py` | Sprint 1 & 2 | **Passed** |

---

### 2.2 Users and Reading Tracking Module (Member 3 — Nagalapuram Sai Mukesh Reddy)

| Requirement ID | Module | Description | Code Location | Test Case IDs & Test Functions | Sprint | Result |
|---|---|---|---|---|---|---|
| **FR-U1** | Users & Tracking | Member registration with unique email and bcrypt password hashing | `src/users/service.py:create_user`, `src/users/routes.py` | TC-U01, TC-U02, `test_register`, `test_duplicate_email_rejected` | Sprint 1 | **Passed** |
| **FR-U2** | Users & Tracking | Login with credentials returning JWT bearer token; logout endpoint | `src/users/service.py:authenticate`, `src/users/routes.py` | TC-U03, TC-U04, TC-U05, `test_login`, `test_logout` | Sprint 1 | **Passed** |
| **FR-U3** | Users & Tracking | Strict role distinction between member and admin | `src/users/models.py:User`, `src/users/auth.py` | TC-U06, `test_user_roles`, `test_admin_role_allowed` | Sprint 1 | **Passed** |
| **FR-U4** | Users & Tracking | Profile retrieval for authenticated user (`GET /api/users/me`) | `src/users/routes.py:whoami`, `src/users/auth.py` | `test_whoami`, `test_whoami_unauthenticated` | Sprint 1 | **Passed** |
| **FR-U5** | Users & Tracking | Reading status management (`want_to_read`, `reading`, `finished`) | `src/users/models.py:ReadingRecordRow`, `src/users/reading.py` | TC-U07, `test_reading_status`, `test_invalid_status_rejected` | Sprint 1 | **Passed** |
| **FR-U6** | Users & Tracking | Reading progress tracking by page with automatic percentage computation | `src/users/reading.py:update_progress` | TC-U08, `test_progress_calculation`, `test_progress_boundary_zero` | Sprint 1 | **Passed** |
| **FR-U7** | Users & Tracking | In-process reading history retrieval for recommendation engine | `src/users/reading.py:get_history` | TC-U09, `test_reading_history`, `test_history_newest_first` | Sprint 1 | **Passed** |
| **FR-U8** (DLBS-40) | Users & Tracking | Profile viewing and profile update endpoints (`GET /api/users/me`, `PUT /api/users/me`) | `src/users/routes.py:get_profile`, `update_profile` | TC-U12, `test_get_profile_success`, `test_update_profile_email` | Sprint 2 | **Passed** |
| **FR-U9** (DLBS-39) | Users & Tracking | Reading tracking REST API routes (`GET /api/reading`, `POST /api/reading`, `PUT /api/reading/{book_id}`) | `src/users/reading_routes.py` | TC-U13, `test_reading_api_create_entry`, `test_reading_api_update_page` | Sprint 2 | **Passed** |
| **FR-U10** (DLBS-38) | Users & Tracking | Reading statistics computation (total books finished, in-progress, pages read) | `src/users/reading.py:get_reading_stats` | TC-U14, `test_reading_stats_aggregation`, `test_reading_stats_empty` | Sprint 2 | **Passed** |
| **FR-U11** (DLBS-40) | Users & Tracking | User frontend pages: Login, Register, Profile, and My Reading | `src/web/login.html`, `src/web/register.html`, `src/web/profile.html`, `src/web/reading.html` | TC-U15, `test_login_page_renders`, `test_reading_page_renders` | Sprint 2 | **Passed** |
| **NFR-U1** | Users & Tracking | Secure password storage using salted bcrypt hashing | `src/users/service.py:hash_password` | TC-U10, `test_bcrypt_hash`, `test_raw_password_not_in_db` | Sprint 1 | **Passed** |
| **NFR-U2** | Users & Tracking | Stateless JWT token authentication without redundant DB lookups | `src/users/auth.py:get_current_user` | TC-U05, `test_jwt_stateless`, `test_expired_jwt_rejected` | Sprint 1 | **Passed** |
| **NFR-U3** | Users & Tracking | Input validation on email format and strong password length (>= 8 characters) | `src/users/service.py:validate_email`, `validate_password` | TC-U11, `test_weak_password`, `test_invalid_email_format` | Sprint 1 | **Passed** |

---

### 2.3 Booking and Borrowing Module (Member 4 — Marreddy Rushieswar Reddy, QA Lead)

| Requirement ID | Module | Description | Code Location | Test Case IDs & Test Functions | Sprint | Result |
|---|---|---|---|---|---|---|
| **FR-B1** | Booking & Borrowing | Reserve book with available copy; available copies drop by 1; removed book rejected | `src/bookings/service.py:reserve_book`, `src/bookings/rules.py:ensure_can_reserve` | TC-B01, TC-B14, `test_reservation_allowed_with_copy_and_capacity`, `test_reservation_rejected_when_book_is_removed` | Sprint 1 | **Passed** |
| **FR-B2** | Booking & Borrowing | Borrow reserved book; sets due date 14 calendar days ahead; copy count unchanged | `src/bookings/service.py:borrow_book`, `src/bookings/rules.py:calculate_due_date` | TC-B06, TC-B20, `test_due_date_is_fourteen_days_after_borrowing`, `test_only_reserved_booking_can_be_borrowed` | Sprint 1 & 2 | **Passed** |
| **FR-B3** | Booking & Borrowing | Return borrowed book; makes copy available again (+1); non-borrowed loans rejected | `src/bookings/service.py:return_book`, `src/bookings/rules.py:ensure_can_return` | TC-B03, `test_only_borrowed_booking_can_be_returned`, `test_api_borrow_return_cancel_and_get_me` | Sprint 1 | **Passed** |
| **FR-B4** | Booking & Borrowing | Cancel unborrowed reservation; restores copy count (+1); borrowed cannot be cancelled | `src/bookings/service.py:cancel_booking`, `src/bookings/rules.py:ensure_can_cancel` | TC-B07, `test_only_reserved_booking_can_be_cancelled`, `test_dlbs_50_cancel_restores_allowance_via_api` | Sprint 1 | **Passed** |
| **FR-B5** | Booking & Borrowing | Available-copy count updates automatically on reserve, cancel, and return; borrow leaves count unchanged | `src/bookings/service.py`, `src/catalog/service.py:change_available_copies` | TC-B08, `test_booking_inventory_invariants_across_lifecycle` | Sprint 1 | **Passed** |
| **FR-B6** | Booking & Borrowing | Flag booking as overdue when current date exceeds due date | `src/bookings/models.py:Booking.is_overdue` | TC-B21, `test_booking_model_active_and_overdue_flags`, `test_overdue_flag_computation` | Sprint 2 | **Passed** |
| **FR-B7** | Booking & Borrowing | View active and past bookings (`GET /api/bookings/me`) | `src/bookings/service.py:get_user_bookings`, `src/bookings/routes.py` | TC-B16, TC-B22, `test_api_borrow_return_cancel_and_get_me`, `test_get_user_bookings_newest_first` | Sprint 2 | **Passed** |
| **FR-B8** (DLBS-50) | Booking & Borrowing | Member shall not hold more than 5 active bookings at once; 6th rejected with 409 | `src/bookings/rules.py:ensure_can_reserve`, `src/bookings/routes.py` | TC-B04, TC-B19, `test_sixth_active_booking_is_rejected`, `test_dlbs_50_sixth_active_with_mixed_borrowed_and_reserved_rejected` | Sprint 1 & 2 | **Passed** |
| **FR-B9** | Booking & Borrowing | Unavailable copy reservation returns HTTP 409 Conflict (no double booking) | `src/bookings/service.py:reserve_book`, `src/bookings/rules.py` | TC-B02, `test_reservation_rejected_when_no_copy_available` | Sprint 1 | **Passed** |
| **FR-B10** | Booking & Borrowing | Reservation hold expires after 2 days; copy automatically restored to available stock | `src/bookings/rules.py:calculate_hold_expiry`, `src/bookings/service.py:expire_booking` | TC-B05, TC-B23, `test_dlbs_45_hold_expiry_calculation`, `test_dlbs_45_service_expire_booking_restores_copy` | Sprint 2 | **Passed** |
| **DLBS-45 Table** | Booking & Borrowing | Bookings table schema with lifecycle fields (`id`, `user_id`, `book_id`, `status`, `reserved_at`, `expires_at`, `borrowed_at`, `due_date`, `returned_at`) | `src/bookings/models.py:BookingRow`, `BookingTable` | `test_dlbs_45_bookings_table_schema` | Sprint 1 & 2 | **Passed** |
| **DLBS-45 States** | Booking & Borrowing | Strict transitions: reserved→borrowed/cancelled/expired, borrowed→returned; invalid transitions rejected with 409 | `src/bookings/rules.py:validate_status_transition` | `test_dlbs_45_allowed_state_transitions`, `test_dlbs_45_rejected_state_transitions` | Sprint 1 & 2 | **Passed** |
| **DLBS-47 Seed** | Booking & QA Lead | Seed script for books loading CSV through catalog repository with shared `book_id` | `scripts/seed.py:seed_books` | TC-B18, `test_seed_books_sample`, `test_seed_shared_id_integrity_with_booking_and_reading` | Sprint 1 | **Passed** |
| **DLBS-56 QA** | Booking & QA Lead | Traceability matrix and test summary report complete, verified, documented, and approved | `docs/qa/rtm.md`, `docs/qa/test-summary.md` | TC-B24, `tests/test_qa_deliverables.py` | Sprint 2 | **Passed** |
| **NFR-B1** | Booking & Borrowing | Concurrency safety: atomic reservation transaction (`BEGIN IMMEDIATE`), thread lock (`RLock`), zero race conditions / double bookings | `src/bookings/service.py:reserve_book` | TC-B09, TC-B25, `test_concurrent_reservations_last_copy_race_condition` | Sprint 1 & 2 | **Passed** |
| **NFR-B2** | Booking & Borrowing | Booking actions complete in under 1 second (< 100ms average measured) | `src/bookings/service.py`, `src/bookings/routes.py` | `test_booking_service_delegation`, `test_booking_latency` | Sprint 1 & 2 | **Passed** |
| **NFR-B3** | Booking & Borrowing | Module unit-test coverage $\ge 70\%$ (achieved 99% coverage on `src/bookings`) | `tests/test_booking_rules.py` | `pytest --cov=src/bookings` (99% verified) | Sprint 1 & 2 | **Passed** |

---

### 2.4 Recommendation Engine Module (Member 1 — Mohammed Sinan M T)

| Requirement ID | Module | Description | Code Location | Test Case IDs & Test Functions | Sprint | Result |
|---|---|---|---|---|---|---|
| **FR-R1** | Recommendation | Personalised or cold-start recommendations for logged-in user | `src/recommender/routes.py:recommend`, `src/recommender/service.py` | `test_routes_returns_recommendations` | Sprint 1 | **Passed** |
| **FR-R2** | Recommendation | Top-$N$ recommendations include ranking score and readable explanation | `src/recommender/base.py:Recommendation` | TC-R02, `test_popularity_recommender`, `test_recommendation_dataclass_fields` | Sprint 1 | **Passed** |
| **FR-R3** | Recommendation | Popularity-based fallback baseline for cold-start users | `src/recommender/popularity.py:PopularityRecommender` | TC-R01, `test_popularity_fallback`, `test_empty_history_uses_popularity` | Sprint 1 | **Passed** |
| **FR-R4** (DLBS-11) | Recommendation | Content-based filtering using TF-IDF over book metadata and reading history; genre affinity (>=3 of top 5 share finished genre) | `src/recommender/content_based.py:ContentBasedRecommender` | TC-R05, `test_content_based_recommender_genre_affinity_acceptance_criterion` | Sprint 2 | **Passed** |
| **FR-R5** (DLBS-12) | Recommendation | Hybrid scoring combining content similarity and popularity with human-readable explanations | `src/recommender/hybrid.py:HybridRecommender`, `src/recommender/scoring.py` | TC-R06, `test_hybrid_scoring_combination`, `test_explanation_generation` | Sprint 2 | **Passed** |
| **FR-R6** | Recommendation | Model refresh and re-indexing endpoint (`POST /api/recommender/refresh`) | `src/recommender/routes.py:refresh_models` | `test_refresh_route`, `test_refresh_admin_required` | Sprint 2 | **Passed** |
| **FR-R7** (DLBS-13) | Recommendation | Recommender evaluation suite: Precision@K, Recall@K, F1@K metrics with holdout split protocol | `src/recommender/evaluation.py`, `scripts/evaluate.py` | TC-R07, `test_precision_at_k`, `test_recall_at_k`, `test_f1_at_k` | Sprint 2 | **Passed** |
| **FR-R8** (DLBS-8) | Recommendation | Dataset preparation and integrity validation (`books.csv`, `users.csv`, `reading_records.csv`) | `scripts/prepare_dataset.py`, `data/` | TC-R04, `tests/test_dataset.py` (5 tests) | Sprint 1 | **Passed** |
| **NFR-R1** | Recommendation | Recommendation generation latency under 1 second (< 150ms measured) | `src/recommender/service.py` | `test_recommender_response_time` | Sprint 1 & 2 | **Passed** |
| **NFR-R2** | Recommendation | Extensible recommender algorithm interface adhering to `BaseRecommender` | `src/recommender/base.py:BaseRecommender` | TC-R03, `test_base_recommender_contract`, `test_recommender_inheritance` | Sprint 1 | **Passed** |

---

### 2.5 Cross-Cutting, CI/CD, and DevOps (Member 3 & Whole Team)

| Requirement ID | Module | Description | Code Location | Test Case IDs & Test Functions | Sprint | Result |
|---|---|---|---|---|---|---|
| **DLBS-16 / 35** | CI/CD | GitHub Actions automated pipeline running compile, lint, and test suite | `.github/workflows/ci.yml` | TC-D01, CI workflow runs on pushes & PRs | Sprint 1 | **Passed** |
| **DLBS-41** | CI/CD | Quality gate: automated test stage enforcing $\ge 70\%$ test coverage | `.github/workflows/ci.yml:COVERAGE_GATE` | TC-D02, `pytest --cov-fail-under=70` (97% achieved) | Sprint 2 | **Passed** |
| **DLBS-42** | DevOps | Multi-stage Docker containerization and Docker Compose deployment | `Dockerfile`, `docker-compose.yml`, `scripts/start.py` | TC-D03, `tests/test_start.py` (11 tests passed) | Sprint 2 | **Passed** |
| **DLBS-43** | DevOps | CI/CD pipeline architectural documentation and README CI status badge | `docs/cicd.md`, `README.md` | TC-D04, `tests/test_smoke_test.py` (10 tests passed) | Sprint 2 | **Passed** |

---

## 3. Requirements Verification & Sign-off Summary

- **Total Requirements Specified:** 42 requirements across 4 functional modules and cross-cutting DevOps.
- **Traceability Coverage:** **100% (42 / 42 requirements traced)**.
- **Automated Regression Tests Executed:** **362 tests passing (0 failures, 0 skipped, 0 regressions)**.
- **Defects / Gaps Identified:** **0 open blockers, 0 open critical/high defects**.
- **System Code Coverage:** **97% overall coverage across `src/`**, with **99% on `src/bookings`**, comfortably surpassing the $\ge 70\%$ requirement (NFR-B3, DLBS-41).
- **QA Lead Sign-Off:** Marreddy Rushieswar Reddy (Member 4, QA Lead)  
- **Release Status:** **VERIFIED, APPROVED, AND READY FOR FINAL PRESENTATION**
