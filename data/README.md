# Dataset Documentation

This directory contains the foundational dataset for the Digital Library and Booking System
(DLBS), prepared by Member 1 (Recommendation Engine, Architecture Owner) for Sprint 1 (DLBS-8).

The dataset provides 10,000 real books from Goodbooks-10k, enriched with derived genres and
descriptions for TF-IDF content filtering, alongside 1,000 synthetic users and ~15,000 reading
records.

---

## 1. Files Summary

| File | Rows | Description | Schema / Columns |
|---|---|---|---|
| `books.csv` | 10,000 | Core library catalog of books | `book_id,title,author,isbn,genre,description,year,page_count,cover_url,total_copies` |
| `users.csv` | 1,000 | Library users (members & admins) | `id,name,email,password_hash,role,created_at` |
| `reading_records.csv` | ~15,000 | User reading activity & progress | `user_id,book_id,status,current_page,percent,started_at,updated_at` |
| `books_sample.csv` | 20 | Member 2 initial working sample | (Same schema as `books.csv`) |

---

## 2. Column Provenance for `books.csv`

Every column in `books.csv` strictly aligns with the SQL database model in `src/catalog/models.py`.

| Column | Type | Source / Provenance | Description |
|---|---|---|---|
| `book_id` | Integer | **Real** (Goodbooks-10k `book_id`) | Primary key, stable integer (1 to 10000) referenced across all modules. |
| `title` | String | **Real** (Goodbooks-10k `title`) | Title of the book. |
| `author` | String | **Real** (Goodbooks-10k `authors`) | Author(s) of the book. |
| `isbn` | String(10-13) | **Real / Generated** | Sourced from Goodbooks `isbn` padded to 10 digits; unique 10-digit placeholders (`97xxxxxxxx`) generated where missing or duplicate to guarantee uniqueness. |
| `genre` | String | **Derived** | Extracted from Goodbooks-10k top tag frequencies in `tags.csv` and `book_tags.csv` (excluding generic shelf tags like `to-read`). Cleaned and capitalized. |
| `description` | Text | **Derived** | Synthesized from title, authors, and top descriptive book tags. Feeds the TF-IDF feature extractor for content-based recommendation (FR-R2). |
| `year` | Integer | **Real** (Goodbooks-10k `original_publication_year`) | Integer publication year. Defaults to 2000 where missing. |
| `page_count` | Integer | **Generated** (Fixed seed `42`) | Integer between 120 and 900. Required by Member 3 for page/percentage reading progress (FR-U6). |
| `cover_url` | String | **Real** (Goodbooks-10k `image_url`) | Valid URL to Goodreads book cover artwork. |
| `total_copies` | Integer | **Generated** (Fixed seed `42`) | Integer between 1 and 5. Governs copy inventory for Member 4's booking module. |

---

## 3. `users.csv` Specifications

Matches `src/users/models.py` for user authentication and role management:

- `id`: Unique integer user ID (1 to 1000).
- `name`: User display name (e.g., "Test Member", "Test Admin", "Aarav Patel").
- `email`: Unique email address (`member@example.com`, `admin@example.com`, `user{i}@example.com`).
- `password_hash`: Bcrypt-compatible password hash string.
- `role`: One of `"member"` or `"admin"`.
- `created_at`: UTC timestamp in ISO 8601 format.

**Seed Test Users**:
- User 1: `member@example.com` (role: `member`)
- User 2: `admin@example.com` (role: `admin`)

---

## 4. `reading_records.csv` Specifications

Matches the reading tracking model and `reading.get_history(user_id)` interface in `docs/api-contract.md`:

- `user_id`: Foreign key to `users.csv`.
- `book_id`: Foreign key to `books.csv`.
- `status`: One of `"want_to_read"`, `"reading"`, `"finished"`.
- `current_page`: Integer page number ($0 \le \text{current\_page} \le \text{page\_count}$).
- `percent`: Float progress percentage ($0.0 \le \text{percent} \le 100.0$).
- `started_at`: ISO 8601 UTC timestamp (empty string if `want_to_read`).
- `updated_at`: ISO 8601 UTC timestamp of last progress update.

Distribution across records:
- Finished: ~60% ($percent = 100.0, current\_page = page\_count$).
- Reading: ~25% ($0 < current\_page < page\_count$).
- Want to read: ~15% ($current\_page = 0, percent = 0.0$).

---

## 5. Reproducibility

The dataset is generated deterministically by running:

```bash
python scripts/prepare_dataset.py
```

Random generation uses seed `42` to guarantee identical outputs across all environments.
