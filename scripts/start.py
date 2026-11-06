"""Container start command (DLBS-42): create the tables, seed the books, run the app.

    python -m scripts.start

SEED_BOOKS=full seeds data/books.csv and SEED_BOOKS=sample seeds data/books_sample.csv.
Seeding runs in the background, so the app answers straight away while the catalog
fills. Books that are already there are skipped, so a restart finishes an interrupted
seed and otherwise takes well under a second. The app listens on PORT (default 8000),
which hosts such as Render set.
"""

import os
import threading
import traceback
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

SEED_CHOICES = ("full", "sample")


def check_choice(choice: str | None) -> str | None:
    """Return the SEED_BOOKS value, or raise ValueError if it is not full or sample."""
    if choice and choice not in SEED_CHOICES:
        raise ValueError(f"SEED_BOOKS must be full or sample, not {choice!r}")
    return choice or None


def seed(choice: str, session_factory=None) -> str:
    """Add the books from the CSV for choice that are not in the database yet."""
    # Imported here so that .env is loaded before src.db reads DATABASE_URL.
    from scripts.seed import seed_books
    from src import db

    with (session_factory or db.SessionLocal)() as session:
        result = seed_books(db=session, sample=choice == "sample")
        if session.get_bind().dialect.name == "postgresql":
            # The CSV gives every book its id, which leaves PostgreSQL's id counter
            # behind. Move it past the seeded ids so books added later get new ids.
            session.execute(text(
                "SELECT setval(pg_get_serial_sequence('books', 'id'), "
                "(SELECT MAX(id) FROM books))"
            ))
            session.commit()
    return (f"Seeded books from {Path(result['file']).name}: {result['loaded']} added, "
            f"{result['skipped']} already there.")


def _seed_in_background(choice: str) -> None:
    try:
        print(seed(choice), flush=True)
    except Exception:  # keep the app running; the next start tries again
        print("Seeding books failed:\n" + traceback.format_exc(), flush=True)


def main() -> None:
    load_dotenv()
    choice = check_choice(os.getenv("SEED_BOOKS"))

    import uvicorn

    from src import db
    from src.main import app  # imports every module, so create_tables makes every table

    db.create_tables()  # before the seed and the app start using the tables
    if choice:
        threading.Thread(target=_seed_in_background, args=(choice,), daemon=True).start()
    else:
        print("SEED_BOOKS is not set, so no books are seeded.", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
