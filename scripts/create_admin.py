"""Create the first admin account from ADMIN_EMAIL and ADMIN_PASSWORD (FR-U3).

Set both variables (see .env.example), then run from the repository root:

    python -m scripts.create_admin
"""

from src.db import SessionLocal, create_tables
from src.users.service import ensure_admin_account


def main() -> None:
    create_tables()
    with SessionLocal() as db:
        try:
            admin = ensure_admin_account(db)
        except ValueError as error:
            raise SystemExit(f"Admin account not created: {error}") from None
        if admin is None:
            raise SystemExit("Set ADMIN_EMAIL and ADMIN_PASSWORD first (see .env.example).")
        print(f"Admin account ready: {admin.email}")


if __name__ == "__main__":
    main()
