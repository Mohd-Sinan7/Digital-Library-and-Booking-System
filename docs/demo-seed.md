# Demo Seed Script (`scripts/seed_demo.py`) — DLBS-52

**Story:** DLBS-52 — Demo seed script (members, admin, reading records)  
**Owner:** Marreddy Rushieswar Reddy (Member 4)

## Overview

`scripts/seed_demo.py` populates a working demo database for rehearsal, personalised recommendation testing (Member 1), reading tracking (Member 3), and booking flows (Member 4):

1. **Books Alignment:** Automatically invokes `scripts/seed.py` (`seed_books`) when the catalog is empty (`--seed-books auto|sample|full|none`) so every `book_id` matches Member 1's `data/books.csv` or `data/books_sample.csv`.
2. **Demo Members (`role="member"`):** Creates demo member accounts from `data/users.csv` (e.g., `member@example.com`, `user3@example.com`, ...) using **Member 3's `src.users.service.create_user()`** so password validation (NFR-U3) and bcrypt hashing (NFR-U1) match live user registration.
3. **Admin Account (`role="admin"`):** Creates the demo admin account (`admin@example.com`) using `create_user(..., role="admin")`.
4. **Synthetic Reading Records:** Loads reading histories (`want_to_read`, `reading`, `finished`, progress, and UTC timestamps) from `data/reading_records.csv`, mapping CSV users and `book_id`s directly to the database rows. Reading histories are immediately readable through Member 3's `src.users.reading.get_history(user_id)` and Member 1's recommender (`/api/recommendations/me`).

## Commands

Run from the repository root:

```bash
# Quick demo setup (auto-seeds books if empty, 25 demo members, 1 admin, matching reading records)
python -m scripts.seed_demo

# Sample catalog mode (uses 20-book data/books_sample.csv)
python -m scripts.seed_demo --sample --members 10

# Custom member count and capped reading records
python -m scripts.seed_demo --members 50 --records-limit 500

# Full 1,000 users from data/users.csv
python -m scripts.seed_demo --all-users

# Re-seed reading records cleanly
python -m scripts.seed_demo --reset
```

## Local Demo Credentials

Default passwords for local development (configurable via CLI flags or `DEMO_MEMBER_PASSWORD` / `DEMO_ADMIN_PASSWORD` environment variables):

| Account Type | Email | Role | Default Local Password |
|---|---|---|---|
| Demo Member (User 1) | `member@example.com` | `member` | `DemoMember123` |
| Synthetic Member *i* | `user3@example.com` ... | `member` | `DemoMember123` |
| Demo Admin | `admin@example.com` | `admin` | `DemoAdmin123` |

> **Idempotency:** Running `python -m scripts.seed_demo` repeatedly safely skips already-registered emails and existing `(user_id, book_id)` reading records without raising duplicate errors.
