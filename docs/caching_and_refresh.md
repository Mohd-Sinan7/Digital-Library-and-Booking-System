# DLBS-14: Integration, Caching, and Admin Refresh

**Jira Issue:** [DLBS-14](https://pes-se.atlassian.net/browse/DLBS-14)  
**Parent:** DLBS-4 Recommendations  
**Sprint:** DLBS Sprint 2 (3 – 8 Nov)  
**Story Points:** 5  
**Owner:** Mohammed Sinan M T (Member 1 — Recommendation Engine Lead)  

---

## 1. Requirements & Acceptance Criteria

| Requirement | Description | Acceptance Criteria |
|---|---|---|
| **FR-R6** | Model Retrain & Refresh | `POST /api/recommendations/refresh` by an admin rebuilds the model and clears the cache; a regular member receives HTTP 403 Forbidden. |
| **NFR-R1** | Performance & Latency | Each of 20 uncached requests on the seeded catalog takes under 2 seconds; repeated/cached requests respond in sub-millisecond time. |
| **NFR-R2** | Pluggable Architecture | Swapping recommenders via `set_recommender()` automatically purges stale cached responses across algorithms. |

---

## 2. Caching Architecture (`src/recommender/cache.py`)

To satisfy **NFR-R1** and prevent redundant computations, recommendation responses are cached using a thread-safe, in-memory cache (`RecommendationCache`).

### Key Characteristics

- **Cache Key:** `(user_id: int, limit: int, genre: str | None)`
- **Default TTL:** 300 seconds (5 minutes)
- **Concurrency Control:** `threading.RLock()` protects concurrent reads and writes.
- **Eviction Policy:**
  - **TTL-based:** Expired entries are discarded upon access.
  - **Capacity-based:** Oldest entries are evicted if cache reaches `max_size` (default 1,000 entries).
- **Deep-Copy Isolation:** Cache reads return independent copies, ensuring callers cannot mutate cached state.
- **Operational Metrics:** Tracks `hits`, `misses`, `size`, and `hit_ratio`.

### Invalidation Triggers

1. **Admin Model Refresh (FR-R6):** Full purge of all cached entries via `cache.clear()`.
2. **Algorithm Swap (NFR-R2):** `set_recommender()` automatically purges the cache to prevent cross-model response pollution.
3. **Targeted Invalidation:** `cache.invalidate_user(user_id)` supports purging records when a user updates their reading history.

---

## 3. Model Precomputation & Lifecycle (`fit()` Method)

Previously, `ContentBasedRecommender.recommend()` computed TF-IDF vectorization across the entire catalog on every invocation. For catalogs of 10,000 books, this added significant latency to every request.

With DLBS-14:
1. `ContentBasedRecommender.fit(db)` precomputes and caches:
   - All non-deleted book metadata
   - Fitted `TfidfVectorizer`
   - Precomputed `tfidf_matrix`
   - Direct `book_id -> vector` mappings
2. `recommend()` reuses precomputed vectors and only calculates the user's reading profile and candidate cosine similarities.
3. `HybridRecommender.fit(db)` delegates to underlying content and popularity models.
4. Calling `POST /api/recommendations/refresh` rebuilds this state from the database.

---

## 4. Admin Refresh Endpoint (`POST /api/recommendations/refresh`)

Protected endpoint enforcing role-based access control (RBAC):

- **Unauthenticated (no Bearer token):** Returns `401 Unauthorized`.
- **Regular Member (`role: member`):** Returns `403 Forbidden` (`{"detail": "Admin privileges required"}`).
- **Administrator (`role: admin`):** Returns `200 OK`, rebuilds the recommendation model, and purges the response cache.

### Response Shape

```json
{
  "status": "ok",
  "message": "Recommendation models refreshed successfully",
  "cached_entries_cleared": 12,
  "model_rebuilt": true
}
```

---

## 5. Performance Verification (NFR-R1 Benchmark)

### 20 Uncached Requests Benchmark

A dedicated automated test (`TestPerformanceRequirementNFR1.test_twenty_uncached_requests_each_under_two_seconds`) executes 20 distinct uncached requests against a seeded catalog:

| Metric | Measured Value | Requirement (NFR-R1) | Status |
|---|---|---|---|
| **Max Request Latency** | ~280 ms | < 2,000 ms (2.0 s) | ✅ PASSED |
| **Average Request Latency** | ~140 ms | < 500 ms target | ✅ PASSED |
| **Cached Request Latency** | < 0.05 ms | Sub-millisecond | ✅ PASSED |
| **All 20 Requests < 2.0s?** | **100% (20/20)** | 100% | ✅ PASSED |

---

## 6. Test Suite Coverage

**Test File:** `tests/recommender/test_caching_and_refresh.py`

| Test Category | Test Count | Description |
|---|---|---|
| `TestRecommendationCache` | 7 tests | Set/get, TTL expiration, cache clearing, user invalidation, max size eviction, thread safety |
| `TestModelRebuilding` | 3 tests | ContentBased `fit()` precomputation, empty catalog handling, Hybrid `fit()` delegation |
| `TestServiceCaching` | 3 tests | Response caching, `use_cache=False` bypass, `set_recommender()` cache clear |
| `TestAdminRefreshEndpointFR6` | 4 tests | 401 unauthenticated, 403 member rejection, 200 admin refresh, direct service call |
| `TestPerformanceRequirementNFR1` | 1 test | 20 uncached requests verified under 2.0s each |
| **Total New Tests** | **18 tests** | **All 18 passed** |
