# Requirements Traceability Matrix (RTM)

**Document ID:** DLBS-QA-RTM-01  
**Project:** Software Engineering Mini-Project — Digital Library and Booking System (DLBS)  
**QA Lead:** Marreddy Rushieswar Reddy (Member 4, SRN: PES1UG24AM158)  
**Status:** All Sprint 1 Requirements Verified and Traced

---

## 1. Traceability Overview

This matrix maps every functional requirement (FR) and non-functional requirement (NFR) across all four system modules to its exact code implementation location, automated test case IDs, sprint allocation, and verification result.

---

## 2. Master Requirements Traceability Table

| Requirement ID | Module | Description | Code Location | Test Case IDs | Sprint | Result |
|---|---|---|---|---|---|---|
| **FR-C1** | Book Catalog | Admin can add books; available copies initialized equal to total copies | `src/catalog/service.py:create_book`, `src/catalog/routes.py` | TC-C01, `test_create_book` | Sprint 1 | **Passed** |
| **FR-C2** | Book Catalog | Admin can edit any subset of book fields | `src/catalog/service.py:update_book`, `src/catalog/routes.py` | TC-C04, `test_update_book` | Sprint 1 | **Passed** |
| **FR-C3** | Book Catalog | Admin can soft-delete books (`is_deleted=True`), preserving records | `src/catalog/service.py:delete_book`, `src/catalog/routes.py` | TC-C05, `test_delete_book` | Sprint 1 | **Passed** |
| **FR-C4** | Book Catalog | Search books by title, author, or ISBN | `src/catalog/service.py:list_books` | TC-C06, `test_search_catalog` | Sprint 1 | **Passed** |
| **FR-C5** | Book Catalog | Filter books by genre and availability (`available_copies > 0`) | `src/catalog/service.py:list_books` | TC-C07, `test_filter_by_genre` | Sprint 1 | **Passed** |
| **FR-C6** | Book Catalog | View book detail; 404 for deleted or nonexistent books | `src/catalog/service.py:get_book`, `src/catalog/routes.py` | TC-C08, TC-C09, `test_get_book` | Sprint 1 | **Passed** |
| **FR-C7** | Book Catalog | Paginated catalog listing with configurable limit/offset | `src/catalog/service.py:list_books` | TC-C10, `test_pagination` | Sprint 1 | **Passed** |
| **FR-C8** | Book Catalog | Role authorization: mutating endpoints require admin privileges (401/403) | `src/catalog/routes.py:require_admin` | TC-C02, TC-C03, `test_admin_auth` | Sprint 1 | **Passed** |
| **NFR-C1** | Book Catalog | Search and catalog queries respond in under 1 second | `src/catalog/service.py` | `test_catalog_latency` | Sprint 1 | **Passed** |
| **NFR-C2** | Book Catalog | Input validation on book attributes (page_count >= 1, copies >= 0) | `src/catalog/schemas.py`, `src/catalog/models.py` | TC-C11, `test_invalid_book_payload` | Sprint 1 | **Passed** |
| **FR-U1** | Users & Tracking | Member registration with unique email and bcrypt password hashing | `src/users/service.py:create_user`, `src/users/routes.py` | TC-U01, TC-U02, `test_register` | Sprint 1 | **Passed** |
| **FR-U2** | Users & Tracking | Login with credentials returning JWT bearer token; logout endpoint | `src/users/service.py:authenticate`, `src/users/routes.py` | TC-U03, TC-U04, TC-U05, `test_login` | Sprint 1 | **Passed** |
| **FR-U3** | Users & Tracking | Role distinction between member and admin | `src/users/models.py:User`, `src/users/auth.py` | TC-U06, `test_user_roles` | Sprint 1 | **Passed** |
| **FR-U4** | Users & Tracking | Profile retrieval for authenticated user | `src/users/routes.py`, `src/users/auth.py` | `test_whoami` | Sprint 1 | **Passed** |
| **FR-U5** | Users & Tracking | Reading status management (`want_to_read`, `reading`, `finished`) | `src/users/models.py:ReadingRecordRow`, `src/users/reading.py` | TC-U07, `test_reading_status` | Sprint 1 | **Passed** |
| **FR-U6** | Users & Tracking | Reading progress tracking by page with automatic percentage computation | `src/users/reading.py:update_progress` | TC-U08, `test_progress_calculation` | Sprint 1 | **Passed** |
| **FR-U7** | Users & Tracking | In-process reading history retrieval for recommendation engine | `src/users/reading.py:get_history` | TC-U09, `test_reading_history` | Sprint 1 | **Passed** |
| **NFR-U1** | Users & Tracking | Secure password storage using salted bcrypt hashing | `src/users/service.py:hash_password` | TC-U10, `test_bcrypt_hash` | Sprint 1 | **Passed** |
| **NFR-U2** | Users & Tracking | Stateless JWT token authentication without redundant DB lookups | `src/users/auth.py:get_current_user` | TC-U05, `test_jwt_stateless` | Sprint 1 | **Passed** |
| **NFR-U3** | Users & Tracking | Input validation on email format and strong password length (>=8 chars) | `src/users/service.py:validate_email`, `validate_password` | TC-U11, `test_weak_password` | Sprint 1 | **Passed** |
| **FR-B1** | Booking & Borrowing | Reserve book with available copy; available copies drop by 1; removed book rejected | `src/bookings/service.py:reserve_book`, `src/bookings/rules.py` | TC-B01, TC-B14, `test_fr_b1_reserve` | Sprint 1 | **Passed** |
| **FR-B2** | Booking & Borrowing | Borrow reserved book; sets due date 14 days ahead; copy count unchanged | `src/bookings/service.py:borrow_book`, `src/bookings/rules.py` | TC-B06, `test_tc_b01_borrow` | Sprint 1 | **Passed** |
| **FR-B3** | Booking & Borrowing | Return borrowed book; restores available copy by 1; non-borrowed rejected | `src/bookings/service.py:return_book`, `src/bookings/rules.py` | TC-B03, `test_tc_b03_return` | Sprint 1 | **Passed** |
| **FR-B4** | Booking & Borrowing | Cancel unborrowed reservation; restores copy by 1; borrowed cannot cancel | `src/bookings/service.py:cancel_booking`, `src/bookings/rules.py` | TC-B07, `test_tc_b05_cancel` | Sprint 1 | **Passed** |
| **FR-B5** | Booking & Borrowing | Automatic copy count update on reserve, cancel, return; borrow leaves unchanged | `src/bookings/service.py` | TC-B08, `test_tc_b08_counts` | Sprint 1 | **Passed** |
| **FR-B6** | Booking & Borrowing | Flag booking as overdue when current date exceeds due date | `src/bookings/models.py:Booking.is_overdue` | `test_booking_model_active_and_overdue` | Sprint 2 | **Passed** |
| **FR-B7** | Booking & Borrowing | View active and past bookings (`GET /api/bookings/me`) | `src/bookings/service.py:get_user_bookings`, `src/bookings/routes.py` | TC-B16, `test_api_borrow_return_cancel_and_get_me` | Sprint 2 | **Passed** |
| **FR-B8** | Booking & Borrowing | Maximum limit of 5 active bookings per member | `src/bookings/rules.py:ensure_can_reserve`, `src/bookings/routes.py` | TC-B04, TC-B19, `test_max_five_active_bookings`, `test_dlbs_50_api_sixth_active_booking_rejected_with_409` | Sprint 1 | **Passed** |
| **FR-B9** | Booking & Borrowing | Unavailable copy reservation returns 409 conflict and changes nothing | `src/bookings/service.py:reserve_book`, `src/bookings/rules.py` | TC-B02, `test_fr_b9_reserve_zero` | Sprint 1 | **Passed** |
| **FR-B10**| Booking & Borrowing | Reservation hold expires after 2 days; copy restored to available count | `src/bookings/rules.py:calculate_hold_expiry`, `src/bookings/service.py:expire_booking` | TC-B05, `test_dlbs_45_hold_expiry_calculation`, `test_dlbs_45_service_expire_booking_restores_copy` | Sprint 2 | **Passed** |
| **DLBS-45 Table** | Booking & Borrowing | Bookings table schema with lifecycle fields (id, user_id, book_id, status, reserved_at, expires_at, borrowed_at, due_date, returned_at) | `src/bookings/models.py:BookingRow` | `test_dlbs_45_bookings_table_schema` | Sprint 2 | **Passed** |
| **DLBS-45 States** | Booking & Borrowing | Strict transitions: reserved→borrowed/cancelled/expired and borrowed→returned; all other transitions rejected | `src/bookings/rules.py:validate_status_transition` | `test_dlbs_45_allowed_state_transitions`, `test_dlbs_45_rejected_state_transitions` | Sprint 2 | **Passed** |
| **DLBS-47 Seed** | Booking & QA Lead | Seed script for books loading CSV through catalog repository with shared book_id | `scripts/seed.py:seed_books` | TC-B18, `tests/test_seed.py` | Sprint 1 | **Passed** |
| **NFR-B1**| Booking & Borrowing | Concurrency safety: atomic reservation transaction (`BEGIN IMMEDIATE`), no double booking | `src/bookings/service.py:reserve_book` (RLock + IMMEDIATE) | TC-B09, `test_nfr_b1_concurrent` | Sprint 1 | **Passed** |
| **NFR-B2**| Booking & Borrowing | Booking actions complete in under 1 second | `src/bookings/service.py` | `test_booking_service_delegation` | Sprint 1 | **Passed** |
| **NFR-B3**| Booking & Borrowing | Module unit-test coverage $\ge 70\%$ | `tests/test_booking_rules.py` | `pytest --cov=src.bookings` (99%) | Sprint 1 | **Passed** |
| **DLBS-50 Limits** | Booking & Borrowing | Enforce 5 active bookings limit (FR-B8) and achieve $\ge 70\%$ test coverage (NFR-B3) | `src/bookings/routes.py`, `src/bookings/rules.py` | TC-B04, TC-B19, `tests/test_booking_rules.py` | Sprint 1 | **Passed** |
| **FR-R1** | Recommendation | Deliver personalised or cold-start recommendations for logged-in user | `src/recommender/routes.py:recommend` | `test_routes_returns_recommendations` | Sprint 1 | **Passed** |
| **FR-R2** | Recommendation | Top-$N$ recommendations include ranking score and readable explanation | `src/recommender/base.py:Recommendation` | TC-R02, `test_popularity_recommender` | Sprint 1 | **Passed** |
| **FR-R3** | Recommendation | Popularity-based fallback baseline for cold-start users | `src/recommender/popularity.py:PopularityRecommender` | TC-R01, `test_popularity_fallback` | Sprint 1 | **Passed** |
| **DLBS-11 (FR-R2)** | Recommendation | Content-based filtering with TF-IDF; user profile weighted by progress; genre affinity (>=3 of top 5 share finished genre) | `src/recommender/content_based.py:ContentBasedRecommender` | TC-R05, `test_content_based_recommender_genre_affinity_acceptance_criterion` | Sprint 2 | **Passed** |
| **FR-R4** | Recommendation | Content-based filtering using book features (genre/description) | `src/recommender/service.py` | `test_recommender_pipeline` | Sprint 2 | **Passed** |
| **FR-R5** | Recommendation | Dataset preparation (`books.csv`, `users.csv`, `reading_records.csv`) | `scripts/prepare_dataset.py`, `data/` | TC-R04, `tests/test_dataset.py` | Sprint 1 | **Passed** |
| **FR-R6** | Recommendation | Model refresh and re-indexing endpoint | `src/recommender/routes.py:refresh_models` | `test_refresh_route` | Sprint 2 | **Passed** |
| **NFR-R1**| Recommendation | Recommendation generation latency under 1 second | `src/recommender/service.py` | `test_recommender_response_time` | Sprint 1 | **Passed** |
| **NFR-R2**| Recommendation | Extensible recommender algorithm interface (`BaseRecommender`) | `src/recommender/base.py:BaseRecommender` | TC-R03, `test_base_recommender_contract` | Sprint 1 | **Passed** |

---

## 3. Coverage and Traceability Sign-off

- **Traceability Completion:** 100% of defined requirements mapped to code and tests.
- **Missing Requirements / Gaps:** 0 gaps identified for Sprint 1.
- **QA Lead Verification:** Marreddy Rushieswar Reddy (Member 4)
- **Sprint 1 Status:** **Verified & Approved**
