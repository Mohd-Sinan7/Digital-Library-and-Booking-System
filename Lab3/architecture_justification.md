# System Architecture Justification (Lab 3 Deliverable)

**Project:** Digital Library and Booking System (DLBS)  
**Document ID:** DLBS-SAD-LAB3-01  
**Architecture Owner:** Mohammed Sinan M T (Member 1 — Recommendation Engine & Presentation Lead)  
**Sprint Allocation:** Setup / Lab 3 Deliverable  
**Associated Jira Story:** [DLBS-6](https://pes-se.atlassian.net/browse/DLBS-6)  

---

## 1. Architectural Style: Layered Modular Monolith

The Digital Library and Booking System (DLBS) is designed as a **Layered Modular Monolith**. The application is structured into four cohesive functional modules—**Book Catalog (`src/catalog`)**, **Users & Reading Tracking (`src/users`)**, **Booking & Borrowing (`src/bookings`)**, and **Recommendation Engine (`src/recommender`)**—united within a single deployable Python process running on FastAPI and SQLAlchemy 2.0.

### Why this style suits our team and timeline:
- **Team Size & Velocity (4 Developers, Two 4-day Sprints):** A microservice architecture would introduce severe distributed systems overhead: separate repositories, independent CI/CD pipelines, inter-service HTTP serialization, network timeout handling, and distributed transaction management (Saga patterns). For a team of four working across tight sprint deadlines, an in-process modular monolith eliminates deployment friction while enforcing strict code boundaries.
- **Standalone, Self-Contained Deployment:** The entire system compiles and runs as a single deployable unit. It requires zero external cloud dependencies, third-party managed APIs, or external message queues. With dual-database support—in-memory SQLite for instant, zero-configuration local testing and PostgreSQL via Docker Compose for production—the application is 100% self-contained.

---

## 2. Component Single Responsibility Principle (SRP)

Every component within the modular monolith possesses a strictly defined single responsibility:

| Component | Lead Owner | Single Responsibility (SRP) |
|---|---|---|
| **Web UI** | M Rishyendra | Render responsive user interfaces (App shell, catalog browsing, reading dashboard, authentication) and interact with backend REST APIs via JWT bearer tokens. |
| **API Gateway / Router (`src/main.py`)** | N. Sai Mukesh Reddy | Centralized request routing, CORS configuration, schema validation, HTTP error translation, and dependency injection (`get_current_user`, `require_admin`). |
| **Book Catalog Service (`src/catalog`)** | M Rishyendra | Complete lifecycle management of books: admin CRUD, soft-deletion (`is_deleted=True`), multi-field search (title, author, ISBN), genre filtering, and stock availability tracking. |
| **Users & Reading Service (`src/users`)** | N. Sai Mukesh Reddy | User identity, salted `bcrypt` password hashing, stateless JWT creation/verification, role-based access control, and page-by-page reading progress tracking. |
| **Booking & Borrowing Service (`src/bookings`)** | M. Rushieswar Reddy | Enforcing loan rules (14-day borrowing, 2-day reservation hold), state machine transitions (`reserved`, `borrowed`, `returned`, `cancelled`), active loan caps (max 5), and ACID-safe stock adjustment. |
| **Recommendation Engine (`src/recommender`)** | Mohammed Sinan M T | Machine learning discovery combining popularity baseline fallback (FR-R3), content-based TF-IDF with cosine similarity (FR-R2), hybrid score blending (FR-R5), in-memory TTL caching (NFR-R1), and admin refresh (FR-R6). |
| **Relational Database** | Shared Engine | ACID-compliant persistent storage with shared primary keys (`book_id`, `user_id`) ensuring relational consistency without distributed joins. |
| **CI/CD Pipeline** | N. Sai Mukesh Reddy | Automated quality gate enforcing byte-compilation, PEP 8 linting (Ruff), multi-stage Docker builds, and automated pytest execution with a 70% coverage gate. |

---

## 3. Key Interfaces & Loose Coupling

Modules interact exclusively through explicit, documented interfaces defined in `docs/api-contract.md`:

1. **Client-to-Application Interface:**
   - Stateless REST endpoints communicating via JSON over HTTP.
   - Protected using standard `Authorization: Bearer <JWT>` headers, decoupling the presentation client from backend data schemas.
2. **In-Process Module-to-Module Interfaces:**
   - **Recommendation to Catalog:** Recommender calls `catalog.get_books()` and `catalog.get_book(id)` in-process to retrieve book metadata for vectorization and card enrichment.
   - **Recommendation to Reading Tracking:** Recommender calls `reading.get_history(user_id)` in-process to build user profiles without HTTP latency.
   - **Booking to Catalog:** Booking calls `catalog.get_availability()` and `catalog.change_available_copies()` to coordinate reservation holds and stock returns atomically.
3. **Pluggable Algorithm Strategy (NFR-R2):**
   - The `Recommender` abstract base class (`src/recommender/base.py`) defines a clean contract: `recommend(user_id, n, genre, db) -> list[Recommendation]`.
   - Implementations (`PopularityRecommender`, `ContentBasedRecommender`, `HybridRecommender`) can be hot-swapped via `set_recommender()` with zero changes to caller or route code.

---

## 4. Quality Attributes Justification

### A. Performance (NFR-R1)
- **Sub-Millisecond In-Process Calls:** Internal service calls occur via Python in-memory function calls rather than loopback HTTP roundtrips.
- **Model Precomputation & Caching:** `ContentBasedRecommender.fit()` precalculates TF-IDF matrices upon initialization or admin refresh, allowing uncached requests to execute in ~140ms and cached requests in < 0.05ms, comfortably surpassing the 2-second NFR-R1 threshold.

### B. Concurrency & Data Integrity (NFR-B1)
- **Atomic Transactions:** Booking operations wrap catalog copy decrements within SQLite `BEGIN IMMEDIATE` transactions and `threading.RLock()`, guaranteeing zero double-booking under concurrent traffic.
- **Soft-Deletion Integrity:** Catalog soft-deletes preserve historical booking and reading records without broken foreign key references.

### C. Maintainability & Loose Coupling (NFR-R2)
- **Independent Module Directories:** Each module resides in its own isolated package (`src/catalog`, `src/users`, `src/bookings`, `src/recommender`) with dedicated test suites.
- **Contract Enforcement:** Strict type annotations and domain dataclasses prevent hidden state mutations across packages.

### D. Security (NFR-U1, NFR-U2)
- **Stateless Authentication:** HS256 JWT tokens carry identity and role claims, eliminating per-request database authorization queries.
- **Cryptographic Hashing:** Salted `bcrypt` hashing guarantees user credentials are secure against rainbow-table attacks.

### E. Testability & CI/CD Verification
- **Deterministic In-Memory Testing:** All 345+ automated tests execute in under 15 seconds against in-memory SQLite tables without external dependencies.
- **Automated Quality Gates:** GitHub Actions CI automatically runs byte-compilation, Ruff linting, and coverage gates on every pull request.
