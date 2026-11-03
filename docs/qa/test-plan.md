# Master Test Plan: Digital Library and Booking System (DLBS)

**Document ID:** DLBS-QA-TP-01  
**Project:** Software Engineering Mini-Project — Digital Library and Booking System  
**QA Lead:** Marreddy Rushieswar Reddy (Member 4, SRN: PES1UG24AM158)  
**Planned Period:** Sprint 1 (29 Oct 2026 – 2 Nov 2026) to Sprint 2 (2 Nov 2026 – 7 Nov 2026)  
**Final Release & Presentations:** 8 Nov 2026 (Freeze) — 9/11/12 Nov 2026 (Presentation)

---

## 1. Objectives and Strategy

The primary goal of this Master Test Plan is to establish a rigorous, repeatable Quality Assurance framework for the **Digital Library and Booking System (DLBS)**. As QA Lead, Member 4 oversees quality across all four modules to ensure high reliability, zero data-corruption risks, verified access controls, and strict compliance with the Software Requirements Specification (SRS).

The QA strategy enforces:
1. **Automated Verification First:** Every functional requirement must have corresponding automated unit/integration tests running locally and on GitHub Actions CI.
2. **Quality Gates:** No pull request is merged into protected `main` without peer review, passing CI (linting and tests), and $\ge 70\%$ unit test coverage (NFR-B3).
3. **Transaction and Inventory Integrity:** Ensuring atomicity (`BEGIN IMMEDIATE`), concurrency safety (NFR-B1), and accurate inventory tracking across all reservation and loan lifecycles.
4. **End-to-End Traceability:** Complete mapping from SRS requirements (FRs and NFRs) to implementation code and test case IDs in the Requirements Traceability Matrix (`docs/qa/rtm.md`).

---

## 2. Scope of Testing

### 2.1 In Scope (All Four Modules)

Testing covers all four application modules defined in the SRS and System Architecture Document (SAD):

1. **Book Catalog Module (Member 2 — Mallela Rishyendra):**
   - Book addition, updating, and soft deletion (`is_deleted=True`) by Admin (FR-C1, FR-C2, FR-C3).
   - Search functionality across title, author, and ISBN (FR-C4).
   - Multi-parameter filtering by genre and availability (`available_copies > 0`) (FR-C5).
   - Book detail viewing and 404 handling for deleted/missing records (FR-C6).
   - Paginated listings with configurable page size (FR-C7).
   - Role-based authorization for administrative mutations (FR-C8).
   - Input validation on ISBN, page counts, and copy bounds (NFR-C2).

2. **Users and Reading Tracking Module (Member 3 — Nagalapuram Sai Mukesh Reddy):**
   - Member registration with duplicate email rejection (FR-U1, HTTP 409).
   - Authentication via credentials, issuance of stateless JWT bearer tokens, and logout (FR-U2).
   - Role enforcement distinguishing `member` and `admin` privileges (FR-U3).
   - Reading status transitions (`want_to_read`, `reading`, `finished`) (FR-U5).
   - Reading progress tracking by `current_page` and automatic percentage calculation (FR-U6).
   - In-process reading history export (`reading.get_history(user_id)`) consumed by the recommender (FR-U7).
   - Password security via salted bcrypt hashing (NFR-U1).
   - Stateless token verification with zero redundant database queries (NFR-U2).
   - Input format validation on email and strong password constraints (NFR-U3).

3. **Booking and Borrowing Module (Member 4 — Marreddy Rushieswar Reddy):**
   - Reservation with available copy check and atomic decrement of `available_copies` (FR-B1, FR-B9).
   - Borrowing transition with automatic 14-day due date calculation and unchanged stock (FR-B2).
   - Book return with single-increment inventory restoration and rejection of non-borrowed loans (FR-B3, BR-08).
   - Reservation cancellation with inventory restoration and rejection of active loans (FR-B4).
   - Invariant check of `available_copies` across all lifecycle operations (FR-B5).
   - Overdue calculation flag when current date exceeds `due_date` (FR-B6).
   - User bookings history retrieval (`GET /api/bookings/me`) (FR-B7).
   - Maximum limit enforcement of 5 active bookings per member (FR-B8).
   - Two-day reservation hold expiry and automatic copy restoration (FR-B10).
   - Atomic transactions and race-condition prevention under concurrent reservation attempts (NFR-B1).
   - Sub-second booking operation response latency (NFR-B2).

4. **Recommendation Engine Module (Member 1 — Mohammed Sinan M T):**
   - Generation of Top-$N$ book recommendations for logged-in users (FR-R1).
   - Delivery of ranking scores and human-readable recommendation reasons (FR-R2).
   - Popularity-based baseline algorithm for cold-start users with no reading history (FR-R3).
   - Content-based TF-IDF algorithm leveraging book metadata and reading history (FR-R4).
   - Dataset preparation and validation (`books.csv`, `users.csv`, `reading_records.csv`) with aligned foreign keys (FR-R5).
   - Adherence to the unified `BaseRecommender` interface (NFR-R2).

### 2.2 Out of Scope
- Third-party library internal source testing (FastAPI, SQLAlchemy, PyJWT, scikit-learn).
- External network outage simulations or distributed denial of service (DDoS) testing.
- Physical server hardware failures.
- Production payment gateways (DLBS is a digital library system with no payment gateway requirements).

---

## 3. Test Levels and Ownership

| Test Level | Primary Owner | Focus & Execution | Tools & Harness |
|---|---|---|---|
| **Unit Testing** | Individual Developers (Members 1, 2, 3, 4) | Pure business logic, model validations, boundary conditions, state transition matrices, helper math. | `pytest`, `pytest-cov`, assertions |
| **Integration Testing** | QA Lead (Member 4) | Cross-module in-process function contracts (`catalog.get_availability`, `get_current_user`, `reading.get_history`), database session handling, foreign keys, transaction rollback. | `pytest`, `FastAPI TestClient`, SQLite in-memory |
| **System Testing** | QA Lead (Member 4) | Complete user journeys (Register $\rightarrow$ Search $\rightarrow$ Reserve $\rightarrow$ Borrow $\rightarrow$ Read $\rightarrow$ Return $\rightarrow$ Recommend), HTTP status codes (200, 201, 204, 401, 403, 404, 409, 422). | `httpx`, `TestClient`, automated script runners |
| **Acceptance Testing** | Whole Team | Validation against SRS criteria, acceptance demos, sprint sign-offs, and usability checks. | Team walk-throughs, demo seed scripts |

---

## 4. Test Approach and Tooling

### 4.1 Automated Testing
Automated testing is the foundation of DLBS quality assurance:
- **Test Runner:** `pytest` (v9.2.0) with discovery in `tests/`.
- **Coverage Analysis:** `pytest-cov` (v7.0.0) measuring statement and branch coverage.
- **HTTP Client:** `TestClient` from Starlette / FastAPI for API contract validation.
- **Database Engine:** Isolated SQLite in-memory databases (`sqlite3.connect(":memory:")`) created per test fixture to guarantee zero state contamination across tests.
- **Concurrency Test Harness:** Python `concurrent.futures.ThreadPoolExecutor` simulating concurrent user bursts on scarce resources (e.g., 10 concurrent requests for 1 copy).

### 4.2 Static Code Analysis & Formatting
- **Linter:** `ruff` (v0.17.3) configured with `--line-length 100 --select E,F,W,I` to enforce PEP 8 standards, import sorting, and flake8 compliance.
- **Compilation Check:** `python -m compileall -q src` ensuring syntax validity across the source tree before test execution.

### 4.3 CI/CD Pipeline
Continuous Integration runs on GitHub Actions (`.github/workflows/ci.yml`):
- Triggers on every push to any branch and every pull request targeting `main`.
- Environment: Ubuntu 22.04 LTS, Python 3.11 with pip caching.
- Build sequence: Install dependencies $\rightarrow$ `python -m compileall -q src` $\rightarrow$ `ruff check --line-length 100 --select E,F,W,I .` $\rightarrow$ `pytest`.
- Protection rule: Merges into `main` are strictly blocked if CI fails or if peer review is missing.

---

## 5. Entry and Exit Criteria

### 5.1 Entry Criteria (When Testing Starts)
1. Feature branch created following team naming convention: `feature/<JIRA-KEY>-short-name`.
2. Developer has written unit tests demonstrating functional implementation.
3. Code compiles without errors and passes static linting locally.
4. Pull Request opened against `main` linking the corresponding Jira card.

### 5.2 Exit Criteria (When a Feature / Sprint is Accepted)
1. **100% Pass Rate:** All automated unit, integration, and system tests pass.
2. **Zero Open Blocker/Critical/High Bugs:** All critical defects resolved and verified.
3. **Coverage Threshold Met:** $\ge 70\%$ test coverage on the module (NFR-B3) and $\ge 80\%$ on core business rules.
4. **Clean CI Run:** GitHub Actions workflow completes with status `success`.
5. **Peer Review Approval:** At least one team member has reviewed and approved the pull request.
6. **Documentation Updated:** API contract (`docs/api-contract.md`), state rules (`docs/booking-rules.md`), and RTM (`docs/qa/rtm.md`) updated.
7. **Jira Transition:** Jira story transitioned to `Done`.

---

## 6. Test Environments

| Environment | Purpose | Configuration | Data Store |
|---|---|---|---|
| **Local Developer** | Fast feedback loop, TDD, debugging | Windows 11 / macOS / Linux, Python 3.11, dedicated virtualenv | SQLite file / memory |
| **Continuous Integration** | Automated gate on pull requests | GitHub Actions runner (`ubuntu-latest`), Python 3.11 | SQLite in-memory |
| **Staging / Deployed App** | End-to-end rehearsal and live presentation | Docker container / VM running Uvicorn server | SQLite / PostgreSQL with seed scripts |

---

## 7. Sprint Schedule and QA Milestones

```
+-----------------------------------------------------------------------------------------+
| Sprint 1 (29 Oct - 2 Nov)   | Sprint 2 (2 Nov - 7 Nov)    | Hardening & Demo (8-12 Nov) |
+-----------------------------+-----------------------------+-----------------------------+
| * Test Plan Skeleton        | * Cross-Module Integration  | * Full Regression Suite     |
| * Sprint 1 Test Cases       | * Concurrency & Perf Tests  | * Bug Retesting & Sign-off  |
| * Booking Unit Tests        | * Recommender E2E Tests     | * Test Summary Report       |
| * Catalog & Auth Test Gates | * Smoke Tests on App Shell  | * Final Presentation Demo   |
+-----------------------------------------------------------------------------------------+
```

- **Sprint 1 (29 Oct – 2 Nov):**
  - Establish QA framework, test plan skeleton, and Sprint 1 test cases across all 4 modules.
  - Implement and verify table design and state transition rules (DLBS-45, DLBS-46, DLBS-49).
  - Verify baseline dataset integrity (`scripts/prepare_dataset.py`, `data/books.csv`).
- **Sprint 2 (2 Nov – 7 Nov):**
  - Multi-module integration tests: Auth $\rightarrow$ Catalog $\rightarrow$ Booking $\rightarrow$ Reading $\rightarrow$ Recommender.
  - Concurrency tests for atomic booking (NFR-B1) and response latency tests (NFR-B2, NFR-C1).
  - UI smoke testing inside app shell.
- **Hardening and Presentation (8 Nov – 12 Nov):**
  - 8 Nov: Code freeze. Full regression run across entire test suite.
  - 9–10 Nov: Hardening only — fix discovered bugs, re-test, zero new features.
  - 10 Nov: Finalize Test Summary Report (`docs/qa/test-summary.md`).
  - 9, 11, or 12 Nov: Software Engineering project presentation.

---

## 8. Risks and Mitigation Strategies

| Risk | Impact | Likelihood | Mitigation Strategy |
|---|---|---|---|
| **Late Integration Across Modules** | High | Medium | Define rigid in-process interfaces and JSON contracts upfront in `docs/api-contract.md`; stub dependencies with mock models until merged. |
| **Shared Database Conflicts & Dirty State** | High | Low | Use in-memory SQLite instances per test session; enforce foreign keys and database constraints (`CHECK`); use explicit transaction rollbacks. |
| **Missing or Inconsistent Test Data** | Medium | Medium | Maintain version-controlled CSV files in `data/` (`books.csv`, `users.csv`, `reading_records.csv`) with shared primary keys populated via deterministic seed scripts. |
| **Race Conditions in Booking Last Copy** | Critical | Medium | Protect stock decrement with SQLite `BEGIN IMMEDIATE` and thread re-entrant locks (`RLock`); verify with multi-threaded stress tests. |

---

## 9. Bug Reporting Standard (Section 6.4)

Every defect identified during testing must be logged in Jira using the following standardized template:

### 9.1 Jira Bug Format
- **Issue Type:** `Bug`
- **Summary:** `[<Module>] <Concise summary of failure>` (e.g., `[Booking] Double-booking occurs when 2 users reserve simultaneously`)
- **Affects Requirement:** (e.g., `FR-B9`, `NFR-B1`)
- **Severity:**
  - `Critical`: System crash, data loss, stock underflow, security breach.
  - `High`: Major functional requirement failed with no workaround.
  - `Medium`: Secondary requirement failed, edge case, or non-blocking UI defect.
  - `Low`: Cosmetic issue, typo in documentation or error message.
- **Steps to Reproduce:**
  1. Step 1 (e.g., Log in as Member A)
  2. Step 2 (e.g., Send POST `/api/bookings` for book_id 1 with 0 available copies)
- **Expected Result:** Clear statement of expected behavior (e.g., HTTP 409 Conflict returned, copies remain 0).
- **Actual Result:** Observed behavior (e.g., HTTP 201 Created returned, available_copies dropped to -1).
- **Environment:** Local / CI / Staging, OS version, commit SHA.

### 9.2 Defect Workflow
`To Do` $\longrightarrow$ `In Progress` $\longrightarrow$ `In Review` (QA Lead re-tests with regression tests) $\longrightarrow$ `Done`
