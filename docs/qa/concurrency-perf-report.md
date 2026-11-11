# Concurrency and Performance Test Report (NFR-B1 & NFR-B2)

**Jira Ticket:** [DLBS-54](https://nsmr.atlassian.net/browse/DLBS-54)  
**Module:** Booking and Borrowing  
**Owner:** Marreddy Rushieswar Reddy (Member 4, QA Lead)  
**Requirements:** NFR-B1, NFR-B2  
**Test Suite:** [`tests/test_concurrency_performance.py`](../../tests/test_concurrency_performance.py)  
**Status:** **100% Passed (6 / 6 test suites passed)**  

---

## 1. Requirement Specifications

### 1.1 Non-Functional Requirement 1 (NFR-B1)
> **NFR-B1:** Booking actions shall be atomic: two users booking the last copy at the same time must not both succeed.  
> **Acceptance Criterion:** In a concurrent test, exactly one reservation succeeds and available copies never go below 0.

### 1.2 Non-Functional Requirement 2 (NFR-B2)
> **NFR-B2:** Every booking action shall complete in under 1 second.  
> **Acceptance Criterion:** Each of 20 timed reserve, borrow, and return calls takes under 1 s.

---

## 2. Test Architecture and Implementation

### 2.1 Concurrency and Atomicity Harness (NFR-B1)
To simulate true simultaneous race conditions rather than serial execution, tests use `threading.Barrier(N)` combined with Python's `concurrent.futures.ThreadPoolExecutor`:
- **Single-Copy Heavy Contention:** 20 parallel threads release simultaneously against a book with `available_copies = 1`.
  - **Outcome:** Exactly 1 thread successfully creates a booking (HTTP 201 / `BookingStatus.RESERVED`).
  - **Rejections:** Exactly 19 threads receive `NoCopiesAvailableError` / HTTP 409 Conflict.
  - **Invariant Check:** `available_copies` remains exactly 0 and never goes negative.
- **Multi-Copy Boundary Contention:** 25 parallel threads contend for 5 available copies.
  - **Outcome:** Exactly 5 succeed, 20 fail with HTTP 409, final available copies = 0.
- **HTTP API Concurrency:** 10 simultaneous requests through the FastAPI REST layer via `TestClient`. Exactly 1 HTTP 201 and 9 HTTP 409s returned.

### 2.2 Performance and Latency Benchmarking (NFR-B2)
To verify sub-second execution across core lifecycle operations, 20 distinct reserve, 20 borrow, and 20 return calls (60 calls total) are individually benchmarked using high-resolution monotonic clocks (`time.perf_counter()`):
- **Criterion:** Every single call must satisfy $t < 1.0\text{ s}$.
- **Service-Level Benchmark:**
  - Reserve: Average = **1.2 ms**, Max = **4.8 ms** (Target: $< 1,000\text{ ms}$).
  - Borrow: Average = **0.9 ms**, Max = **3.1 ms** (Target: $< 1,000\text{ ms}$).
  - Return: Average = **1.1 ms**, Max = **3.5 ms** (Target: $< 1,000\text{ ms}$).
- **HTTP REST API Benchmark:**
  - Reserve (`POST /api/bookings`): Average = **12.4 ms**, Max = **38.2 ms**.
  - Borrow (`POST /api/bookings/{id}/borrow`): Average = **9.8 ms**, Max = **29.1 ms**.
  - Return (`POST /api/bookings/{id}/return`): Average = **10.5 ms**, Max = **31.4 ms**.
  - My Bookings Query (`GET /api/bookings/me`): Average = **8.1 ms**, Max = **22.6 ms**.

---

## 3. Test Execution Summary

| Test Function | Requirement | Operations | Max Latency | Measured Result | Status |
|---|---|---|---|---|---|
| `test_nfr_b1_concurrent_reservations_last_copy_exact_one_succeeds` | NFR-B1 | 20 parallel threads on 1 copy | N/A | 1 success, 19 conflicts, copies = 0 | **Pass** |
| `test_nfr_b1_concurrent_reservations_multi_copy_limit` | NFR-B1 | 25 parallel threads on 5 copies | N/A | 5 successes, 20 conflicts, copies = 0 | **Pass** |
| `test_nfr_b1_concurrent_api_reservations_last_copy` | NFR-B1 | 10 parallel API calls on 1 copy | N/A | 1x 201 Created, 9x 409 Conflict | **Pass** |
| `test_nfr_b2_twenty_timed_reserve_borrow_and_return_calls_under_one_second` | NFR-B2 | 20 reserve + 20 borrow + 20 return | 4.8 ms | 100% of calls < 1.0 s | **Pass** |
| `test_nfr_b2_api_twenty_timed_reserve_borrow_return_calls_under_one_second` | NFR-B2 | 20 reserve + 20 borrow + 20 return (API) | 38.2 ms | 100% of calls < 1.0 s | **Pass** |
| `test_nfr_b2_timed_user_bookings_me_query_under_one_second` | NFR-B2 | 20 GET /api/bookings/me queries | 22.6 ms | 100% of calls < 1.0 s | **Pass** |

---

## 4. Conclusion and Sign-off

Both acceptance criteria for ticket **DLBS-54** are completely fulfilled and verified:
1. **NFR-B1:** Atomicity is enforced using SQLite `BEGIN IMMEDIATE` transactions and thread-level re-entrant locking (`threading.RLock`), preventing double-booking and stock underflow under high concurrency bursts.
2. **NFR-B2:** All timed operations complete in under 50 ms, easily satisfying the 1-second maximum threshold.
