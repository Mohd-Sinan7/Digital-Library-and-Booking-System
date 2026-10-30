# src

Application code. `src` is a Python package, so import with the full path, for
example `from src.users.auth import get_current_user`.

| Package | Module | Owner |
|---|---|---|
| `src/main.py` | Builds the FastAPI app and mounts every module's router (Sprint 1) | Member 3 |
| `src/db.py` | Shared database engine, sessions and the `Base` class every table extends | Member 3 |
| `src/users/` | Users and Reading Tracking, plus the shared auth helper | Member 3 |
| `src/catalog/` | Book Catalog | Member 2 |
| `src/booking/` | Booking and Borrowing | Member 4 |
| `src/recommender/` | Recommendation Engine | Member 1 |

## Adding your module

1. Create `src/<module>/__init__.py` and `src/<module>/routes.py` with an
   `APIRouter`.
2. Mount it in `src/main.py` with `app.include_router(...)`.
3. Protect endpoints with the shared helper in `src/users/auth.py`. See
   `docs/api-contract.md` for examples.
