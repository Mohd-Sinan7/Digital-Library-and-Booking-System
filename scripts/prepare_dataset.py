"""Script to download Goodbooks-10k and prepare books.csv, users.csv, and reading_records.csv.

Fulfills Sprint 1 dataset preparation task (DLBS-8).
Provenance:
- Real from Goodbooks-10k: book_id, title, authors, isbn base, year, cover_url.
- Derived from Goodbooks tags: genre, description.
- Generated with fixed seed (42): page_count (120-900), total_copies (1-5).
- Synthetic: users (1,000 users), reading records (~15,000 records).
"""

import csv
import io
import os
import random
import re
import urllib.request
from datetime import UTC, datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SEED = 42

GOODBOOKS_BASE = "https://raw.githubusercontent.com/zygmuntz/goodbooks-10k/master"
SHELF_TAGS = {
    "-",
    "to-read",
    "currently-reading",
    "favorites",
    "favourites",
    "owned",
    "books-i-own",
    "default",
    "all-time-favorites",
    "my-books",
    "i-own",
    "audiobook",
    "audiobooks",
    "ebook",
    "ebooks",
    "kindle",
    "library",
    "wish-list",
    "re-read",
    "shelfari-favorites",
    "read",
    "my-library",
    "read-in-2015",
    "read-in-2016",
    "read-in-2017",
    "book-club",
    "owned-books",
    "series",
    "novels",
    "novel",
}


def download_tags() -> dict[int, str]:
    """Download tags.csv and return {tag_id: tag_name}."""
    url = f"{GOODBOOKS_BASE}/tags.csv"
    print(f"Downloading tags from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    tags: dict[int, str] = {}
    with urllib.request.urlopen(req, timeout=30) as resp:
        reader = csv.reader(io.TextIOWrapper(resp, encoding="utf-8", errors="replace"))
        next(reader)  # skip header
        for row in reader:
            if len(row) >= 2:
                tags[int(row[0])] = row[1].strip()
    print(f"Loaded {len(tags)} tags.")
    return tags


def download_book_top_tags(tags: dict[int, str]) -> dict[int, list[str]]:
    """Stream book_tags.csv and extract top substantive tags for each goodreads_book_id."""
    url = f"{GOODBOOKS_BASE}/book_tags.csv"
    print(f"Streaming book tags from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    book_tags_raw: dict[int, list[tuple[str, int]]] = {}

    with urllib.request.urlopen(req, timeout=60) as resp:
        reader = csv.reader(io.TextIOWrapper(resp, encoding="utf-8", errors="replace"))
        next(reader)  # skip header
        for row in reader:
            if len(row) >= 3:
                gid = int(row[0])
                tid = int(row[1])
                count = int(row[2])
                tag_name = tags.get(tid, "").lower()

                # Filter out meta/shelf tags
                if not tag_name or tag_name in SHELF_TAGS or tag_name.startswith("--"):
                    continue

                curr = book_tags_raw.setdefault(gid, [])
                if len(curr) < 6:
                    curr.append((tag_name, count))
                else:
                    min_idx = min(range(len(curr)), key=lambda i: curr[i][1])
                    if count > curr[min_idx][1]:
                        curr[min_idx] = (tag_name, count)

    # Sort tags descending by count
    book_tags_cleaned: dict[int, list[str]] = {}
    for gid, tag_list in book_tags_raw.items():
        tag_list.sort(key=lambda x: x[1], reverse=True)
        book_tags_cleaned[gid] = [t[0] for t in tag_list]

    print(f"Extracted substantive tags for {len(book_tags_cleaned)} books.")
    return book_tags_cleaned


def clean_genre(tag: str) -> str:
    """Format tag into a clean, capitalized genre name."""
    cleaned = tag.replace("-", " ").strip()
    words = [w.capitalize() for w in cleaned.split()]
    return " ".join(words) if words else "Fiction"


def prepare_books(book_tags: dict[int, list[str]]) -> list[dict]:
    """Download books.csv and build 10,000 standardized book records."""
    url = f"{GOODBOOKS_BASE}/books.csv"
    print(f"Downloading books from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    rng = random.Random(SEED)
    books: list[dict] = []
    seen_isbns: set[str] = set()

    with urllib.request.urlopen(req, timeout=30) as resp:
        reader = csv.DictReader(io.TextIOWrapper(resp, encoding="utf-8", errors="replace"))
        for row in reader:
            book_id = int(row["book_id"])
            goodreads_id = int(row["goodreads_book_id"])
            raw_title = row.get("title", "").strip() or "Untitled"
            raw_authors = row.get("authors", "").strip() or "Unknown"

            # Parse year
            year_val = row.get("original_publication_year", "").strip()
            try:
                year = int(float(year_val)) if year_val else 2000
            except ValueError:
                year = 2000

            # Tags & Genre
            tags_for_book = book_tags.get(goodreads_id, [])
            if tags_for_book:
                primary_tag = tags_for_book[0]
                genre = clean_genre(primary_tag)
                # Cap genre length to fit DB String(50)
                if len(genre) > 40:
                    genre = genre[:40]
            else:
                genre = "Fiction"

            # Build rich description for TF-IDF vectorization
            if tags_for_book:
                tag_sample = [clean_genre(t) for t in tags_for_book[:4]]
                description = (
                    f"{raw_title} by {raw_authors}. A distinguished {genre.lower()} work "
                    f"touching on themes of {', '.join(tag_sample)}."
                )
            else:
                description = (
                    f"{raw_title} by {raw_authors}. A distinguished work in {genre.lower()} "
                    f"published in {year}."
                )

            # Pad ISBN to 10 digits or generate unique placeholder
            raw_isbn = row.get("isbn", "").strip()
            digits_isbn = re.sub(r"[^0-9X]", "", raw_isbn)
            if len(digits_isbn) == 10 and digits_isbn not in seen_isbns:
                isbn = digits_isbn
            elif 0 < len(digits_isbn) < 10 and digits_isbn.zfill(10) not in seen_isbns:
                isbn = digits_isbn.zfill(10)
            else:
                # Generate unique 10-digit placeholder
                isbn = f"97{book_id:08d}"

            seen_isbns.add(isbn)

            # Generated fields with fixed seed
            page_count = rng.randint(120, 900)
            total_copies = rng.randint(1, 5)

            cover_placeholder = f"https://covers.example.org/{book_id}.jpg"
            cover_url = row.get("image_url", "").strip() or cover_placeholder

            books.append(
                {
                    "book_id": book_id,
                    "title": raw_title,
                    "author": raw_authors,
                    "isbn": isbn,
                    "genre": genre,
                    "description": description,
                    "year": year,
                    "page_count": page_count,
                    "cover_url": cover_url,
                    "total_copies": total_copies,
                }
            )

    print(f"Prepared {len(books)} books.")
    return books


def prepare_users(num_users: int = 1000) -> list[dict]:
    """Generate 1,000 synthetic users matching src/users/models.py."""
    users = []
    # User 1: Fixed test member
    users.append(
        {
            "id": 1,
            "name": "Test Member",
            "email": "member@example.com",
            "password_hash": "$2b$12$e8rXp90yFakeHashForTestingOnlyNotSecret0123456789abcde",
            "role": "member",
            "created_at": "2026-10-30T10:00:00Z",
        }
    )
    # User 2: Fixed test admin
    users.append(
        {
            "id": 2,
            "name": "Test Admin",
            "email": "admin@example.com",
            "password_hash": "$2b$12$e8rXp90yFakeHashForTestingOnlyNotSecret0123456789admin",
            "role": "admin",
            "created_at": "2026-10-30T10:00:00Z",
        }
    )

    first_names = [
        "Aarav", "Aditi", "Alex", "Amara", "Carlos", "Chen", "Dev", "Elena",
        "Fatima", "Grace", "Hassan", "Ishaan", "Jack", "Kavya", "Liam", "Maya",
        "Noah", "Olivia", "Priya", "Rahul", "Sara", "Tariq", "Uma", "Vikram",
        "Zara", "Ananya", "Ben", "Chloe", "David", "Emma", "Farhan", "Gita",
    ]
    last_names = [
        "Patel", "Smith", "Sharma", "Garcia", "Johnson", "Khan", "Wang", "Rao",
        "Kim", "Muller", "Singh", "Brown", "Nair", "Taylor", "Ali", "Das",
        "Kumar", "Gupta", "Tanaka", "Ito", "Reddy", "Menon", "Joshi", "Bose",
    ]

    base_time = datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC)
    for i in range(3, num_users + 1):
        fn = first_names[(i * 7) % len(first_names)]
        ln = last_names[(i * 13) % len(last_names)]
        created = (base_time + timedelta(hours=i * 2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        users.append(
            {
                "id": i,
                "name": f"{fn} {ln}",
                "email": f"user{i}@example.com",
                "password_hash": f"$2b$12$FakeHashUser{i:04d}0123456789abcdef0123456789",
                "role": "member",
                "created_at": created,
            }
        )

    print(f"Generated {len(users)} users.")
    return users


def prepare_reading_records(books: list[dict], users: list[dict]) -> list[dict]:
    """Generate realistic reading records linked to books and users."""
    records = []
    book_lookup = {b["book_id"]: b for b in books}

    # User 1 specific records across key books to test personalization
    user_1_books = [1, 2, 3, 4, 5, 8, 10, 13, 14, 20]
    for idx, bid in enumerate(user_1_books):
        book = book_lookup[bid]
        pages = book["page_count"]
        if idx < 5:
            status = "finished"
            current_page = pages
            percent = 100.0
            started = "2026-10-15T10:00:00Z"
            updated = "2026-10-25T16:00:00Z"
        elif idx < 8:
            status = "reading"
            current_page = int(pages * 0.45)
            percent = 45.0
            started = "2026-10-26T12:00:00Z"
            updated = "2026-10-30T18:30:00Z"
        else:
            status = "want_to_read"
            current_page = 0
            percent = 0.0
            started = ""
            updated = "2026-10-28T09:00:00Z"

        records.append(
            {
                "user_id": 1,
                "book_id": bid,
                "status": status,
                "current_page": current_page,
                "percent": percent,
                "started_at": started,
                "updated_at": updated,
            }
        )

    # Records for users 2..1000
    for user in users:
        uid = user["id"]
        if uid == 1:
            continue
        rng = random.Random(SEED + uid)
        num_records = rng.randint(8, 22)
        chosen_book_ids = rng.sample(range(1, len(books) + 1), num_records)

        for bid in chosen_book_ids:
            book = book_lookup[bid]
            pages = book["page_count"]
            roll = rng.random()
            if roll < 0.60:
                status = "finished"
                current_page = pages
                percent = 100.0
                st_dt = datetime(2026, 10, 1, tzinfo=UTC) + timedelta(days=rng.randint(1, 10))
                up_dt = datetime(2026, 10, 15, tzinfo=UTC) + timedelta(days=rng.randint(1, 14))
                started = st_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                updated = up_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            elif roll < 0.85:
                status = "reading"
                current_page = rng.randint(10, max(11, pages - 10))
                percent = round((current_page / pages) * 100, 1)
                st_dt = datetime(2026, 10, 20, tzinfo=UTC) + timedelta(days=rng.randint(1, 5))
                up_dt = datetime(2026, 10, 27, tzinfo=UTC) + timedelta(days=rng.randint(1, 3))
                started = st_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                updated = up_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                status = "want_to_read"
                current_page = 0
                percent = 0.0
                started = ""
                up_dt = datetime(2026, 10, 25, tzinfo=UTC) + timedelta(days=rng.randint(1, 5))
                updated = up_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            records.append(
                {
                    "user_id": uid,
                    "book_id": bid,
                    "status": status,
                    "current_page": current_page,
                    "percent": percent,
                    "started_at": started,
                    "updated_at": updated,
                }
            )

    print(f"Generated {len(records)} reading records.")
    return records


def write_csv(filepath: str, data: list[dict], fieldnames: list[str]) -> None:
    """Write list of dicts to a CSV file."""
    print(f"Writing {len(data)} rows to {filepath}...")
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    print(f"Finished {os.path.basename(filepath)} ({os.path.getsize(filepath):,} bytes).")


def write_readme() -> None:
    """Generate comprehensive documentation in data/README.md."""
    readme_path = os.path.join(DATA_DIR, "README.md")
    lines = [
        "# Dataset Documentation",
        "",
        "This directory contains the foundational dataset for the Digital Library and Booking",
        "System (DLBS), prepared by Member 1 for Sprint 1 (DLBS-8).",
        "",
        "The dataset provides 10,000 real books from Goodbooks-10k, enriched with derived genres",
        "and descriptions for TF-IDF filtering, alongside 1,000 synthetic users and ~15,000",
        "reading records.",
        "",
        "---",
        "",
        "## 1. Files Summary",
        "",
        "- `books.csv`: 10,000 books (`book_id,title,author,isbn,genre,description,year,`",
        "  `page_count,cover_url,total_copies`)",
        "- `users.csv`: 1,000 users (`id,name,email,password_hash,role,created_at`)",
        "- `reading_records.csv`: ~15,000 reading records (`user_id,book_id,status,`",
        "  `current_page,percent,started_at,updated_at`)",
        "- `books_sample.csv`: 20 initial working books (same schema as `books.csv`)",
        "",
        "---",
        "",
        "## 2. Column Provenance for `books.csv`",
        "",
        "- `book_id`: **Real** (Goodbooks `book_id`). Stable integer (1 to 10000).",
        "- `title`: **Real** (Goodbooks `title`).",
        "- `author`: **Real** (Goodbooks `authors`).",
        "- `isbn`: **Real / Generated**. Padded to 10 digits; unique `97xxxxxxxx` where missing.",
        "- `genre`: **Derived** from Goodbooks top tags (excluding shelf tags like to-read).",
        "- `description`: **Derived** from title, authors, and top tags. Feeds TF-IDF (FR-R2).",
        "- `year`: **Real** (Goodbooks `original_publication_year`).",
        "- `page_count`: **Generated** (Seed `42`). Integer (120-900) for progress (FR-U6).",
        "- `cover_url`: **Real** (Goodbooks `image_url`).",
        "- `total_copies`: **Generated** (Seed `42`). Integer (1-5) for inventory.",
        "",
        "---",
        "",
        "## 3. `users.csv` Specifications",
        "",
        "- Matches `src/users/models.py` (id, name, email, password_hash, role, created_at).",
        "- Seed users: User 1 (`member@example.com`, member),",
        "  User 2 (`admin@example.com`, admin).",
        "",
        "---",
        "",
        "## 4. `reading_records.csv` Specifications",
        "",
        "- Matches `docs/api-contract.md` (user_id, book_id, status, current_page,",
        "  percent, timestamps).",
        "- Statuses: `finished` (~60%), `reading` (~25%), `want_to_read` (~15%).",
        "",
        "---",
        "",
        "## 5. Reproducibility",
        "",
        "The dataset is generated deterministically by running:",
        "",
        "```bash",
        "python scripts/prepare_dataset.py",
        "```",
    ]
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Generated {readme_path}.")


def main():
    print("Starting dataset preparation for DLBS-8...")
    os.makedirs(DATA_DIR, exist_ok=True)

    tags = download_tags()
    book_tags = download_book_top_tags(tags)
    books = prepare_books(book_tags)
    users = prepare_users(1000)
    reading_records = prepare_reading_records(books, users)

    book_fields = [
        "book_id", "title", "author", "isbn", "genre",
        "description", "year", "page_count", "cover_url", "total_copies",
    ]
    write_csv(os.path.join(DATA_DIR, "books.csv"), books, book_fields)

    user_fields = ["id", "name", "email", "password_hash", "role", "created_at"]
    write_csv(os.path.join(DATA_DIR, "users.csv"), users, user_fields)

    rec_fields = [
        "user_id", "book_id", "status", "current_page",
        "percent", "started_at", "updated_at",
    ]
    write_csv(os.path.join(DATA_DIR, "reading_records.csv"), reading_records, rec_fields)

    write_readme()
    print("Dataset preparation complete!")


if __name__ == "__main__":
    main()
