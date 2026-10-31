# API Contract

The JSON shapes that modules use to talk to each other. Agreed on 29 Oct 2026.
Each owner fills in and maintains their own section. If you change an endpoint,
update this file in the same pull request and tell the people who call it.

## Shared conventions

| Topic | Rule |
|---|---|
| Base path | Every endpoint starts with `/api`, except `GET /health` |
| Format | JSON request and response bodies, UTF-8 |
| Field names | `snake_case` |
| IDs | Integers |
| Timestamps | ISO 8601 in UTC, for example `"2026-10-30T10:15:00Z"` |
| Authentication | Header `Authorization: Bearer <token>` on every protected endpoint |
| Errors | `{"detail": "Human-readable message"}` |

### Status codes

| Code | When |
|---|---|
| 200 | Success with a body |
| 201 | Something was created |
| 204 | Success with no body |
| 401 | No token, or an invalid or expired token |
| 403 | Logged in, but the role is not allowed (for example a member on an admin endpoint) |
| 404 | The item does not exist |
| 409 | Conflict: duplicate email or ISBN, no copies left, a booking in the wrong state |
| 422 | The request body or query failed validation (FastAPI returns this automatically) |

### Protecting your endpoints (Members 1, 2 and 4)

Use the shared helper in `src/users/auth.py`:

```python
from fastapi import APIRouter, Depends

from src.users.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api/books", tags=["catalog"])


@router.get("/{book_id}")
def get_book(book_id: int, user: CurrentUser = Depends(get_current_user)):
    ...  # any logged-in user; no token gets 401
```

`CurrentUser` has `id`, `name`, `email` and `role` (`"member"` or `"admin"`).

An admin-only helper that returns 403 to members is added with the Roles story by
31 Oct. Until then, check `user.role == "admin"` yourself.

### Stub tokens (until real login is merged on 1 Nov)

| Header | You are |
|---|---|
| `Authorization: Bearer test-member-token` | User 1, Test Member, role `member` |
| `Authorization: Bearer test-admin-token` | User 2, Test Admin, role `admin` |

Any other token, or no token, gets 401. After 1 Nov, get a real token from
`POST /api/auth/login`. Your code does not change.

---

## Users and Reading Tracking (Member 3)

### POST /api/auth/register

Creates a member account (FR-U1). The email must be unique. The password needs at
least 8 characters, including at least one letter and one digit.

Request:

```json
{"name": "Asha Rao", "email": "asha@example.com", "password": "readmore42"}
```

Response `201`:

```json
{"id": 7, "name": "Asha Rao", "email": "asha@example.com", "role": "member", "created_at": "2026-10-30T10:15:00Z"}
```

Errors: `409` email already registered; `422` invalid email, missing field or weak password.

### POST /api/auth/login

Logs in and returns a token (FR-U2).

Request:

```json
{"email": "asha@example.com", "password": "readmore42"}
```

Response `200`:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {"id": 7, "name": "Asha Rao", "email": "asha@example.com", "role": "member"}
}
```

Errors: `401` invalid email or password. The message does not say which one was wrong.

### POST /api/auth/logout

Logs out (FR-U2). The client deletes its stored token. Requires a token.

Response `204`, no body.

### GET /api/users/me

The current user's profile and role (FR-U3, FR-U4). Requires a token.

Response `200`:

```json
{"id": 7, "name": "Asha Rao", "email": "asha@example.com", "role": "member"}
```

### PUT /api/users/me

Edits the current user's profile (FR-U4). Email and role cannot be changed here.

Request:

```json
{"name": "Asha R."}
```

Response `200`: the updated profile, same shape as `GET /api/users/me`.

### Reading record

`PUT /api/reading/status`, `POST /api/reading/progress` and
`GET /api/reading/history` all return reading records in this shape:

```json
{
  "book_id": 42,
  "title": "The Pragmatic Programmer",
  "author": "Andrew Hunt, David Thomas",
  "genre": "Technology",
  "status": "reading",
  "current_page": 120,
  "percent": 37.5,
  "started_at": "2026-10-30T10:15:00Z",
  "updated_at": "2026-11-02T18:40:00Z"
}
```

- `status` is one of `"want_to_read"`, `"reading"`, `"finished"`.
- `percent` is calculated from `current_page` and the book's `page_count` from the catalog.
- `title`, `author` and `genre` come from the catalog (Member 2).

### PUT /api/reading/status

Sets the reading status for a book (FR-U5). Creates the record if it does not exist.

Request:

```json
{"book_id": 42, "status": "reading"}
```

Response `200`: the reading record.

Errors: `404` book not found; `422` unknown status.

### POST /api/reading/progress

Records progress for a book (FR-U6). Send exactly one of `current_page` or `percent`.

```json
{"book_id": 42, "current_page": 120}
```

```json
{"book_id": 42, "percent": 37.5}
```

Response `200`: the reading record. Recording progress on a `want_to_read` book moves
it to `reading`. Reaching 100% moves it to `finished`.

Errors: `404` book not found; `422` when both or neither field is sent, `percent` is
below 0 or above 100, or `current_page` is below 0 or above the book's `page_count`.

### GET /api/reading/history

The current user's reading history (FR-U7), newest `updated_at` first. Optional
filter: `?status=finished`. The My Reading screen uses this. Member 1's recommender
calls the in-process function `reading.get_history(user_id)` instead (see below).

Response `200`:

```json
{"items": [ /* reading records */ ]}
```

### GET /api/reading/stats

The current user's reading statistics (FR-U8). `pages_read` is the sum of
`current_page` over all of the user's records.

Response `200`:

```json
{"books_finished": 4, "books_reading": 2, "books_want_to_read": 5, "pages_read": 1260}
```

### In-process function: reading.get_history(user_id)

Member 1's recommender calls this Python function directly instead of the REST
endpoint. It lives in `src/users/reading.py` and is live by 1 Nov.

```python
from src.users import reading

records = reading.get_history(user_id)
```

Signature and return shape:

```python
@dataclass(frozen=True)
class ReadingRecord:
    book_id: int
    status: str                 # "want_to_read", "reading" or "finished"
    current_page: int
    percent: float              # 0 to 100
    started_at: datetime | None # UTC; None until the user starts reading
    updated_at: datetime        # UTC


def get_history(user_id: int) -> list[ReadingRecord]:
    """Return all of the user's reading records, newest updated_at first."""
```

- Returns an empty list for a user with no records, or a `user_id` that does not exist.
- Book details (title, author, genre) are not included. Get them from `catalog.get_books()`.
- No token is needed: the caller is code in the same app, not an HTTP request.

---

## Book Catalog (Member 2)

To be filled in by Member 2 on 29 Oct. Already agreed in the member plans:

- The book JSON includes `page_count` (Member 3 uses it for progress) and
  `available_copies` (only Member 4's booking code changes it).
- `GET /api/books?q=&genre=&available=&page=` for search, filter and list
- `GET /api/books/{id}`; `POST`, `PUT` and `DELETE /api/books/{id}` for admins
- `GET /api/books/{id}/availability` returns `available_copies`

## Booking and Borrowing (Member 4)

Filled in by Member 4 (Rushi Eswar) on 30 Oct 2026.

All booking endpoints require authentication via `Authorization: Bearer <token>` using `CurrentUser`.

### Booking object shape

```json
{
  "id": 101,
  "user_id": 7,
  "book_id": 42,
  "status": "reserved",
  "created_at": "2026-10-30",
  "due_date": null,
  "returned_at": null,
  "is_active": true,
  "is_overdue": false
}
```

- `status` is one of `"reserved"`, `"borrowed"`, `"returned"`, `"cancelled"`, `"expired"`.
- `is_active` is true for `"reserved"` and `"borrowed"`.
- `is_overdue` is true when `status == "borrowed"`, `due_date` is set, and today is past `due_date`.

### POST /api/bookings

Reserves a copy of a book for the authenticated member (BR-01, BR-02, BR-03, BR-04). Requires at least 1 available copy and member must have fewer than 5 active bookings. Decrements `available_copies` by 1.

Request:

```json
{"book_id": 42}
```

Response `201`:

```json
{
  "id": 101,
  "user_id": 7,
  "book_id": 42,
  "status": "reserved",
  "created_at": "2026-10-30",
  "due_date": null,
  "returned_at": null,
  "is_active": true,
  "is_overdue": false
}
```

Errors: `401` unauthorized; `404` book not found; `409` no copies available or member reached limit of 5 active bookings.

### POST /api/bookings/{id}/borrow

Transitions a reservation to borrowed status (BR-05, BR-06). Sets the loan due date to 14 calendar days from the borrowing date.

Response `200`:

```json
{
  "id": 101,
  "user_id": 7,
  "book_id": 42,
  "status": "borrowed",
  "created_at": "2026-10-30",
  "due_date": "2026-11-13",
  "returned_at": null,
  "is_active": true,
  "is_overdue": false
}
```

Errors: `401` unauthorized; `404` booking not found; `409` booking is not in `reserved` status.

### POST /api/bookings/{id}/return

Processes the return of a borrowed book (BR-07, BR-08). Sets status to `returned` and records `returned_at`. Restores 1 available copy to the catalog. Repeated returns are rejected or idempotent to prevent duplicate stock increments.

Response `200`:

```json
{
  "id": 101,
  "user_id": 7,
  "book_id": 42,
  "status": "returned",
  "created_at": "2026-10-30",
  "due_date": "2026-11-13",
  "returned_at": "2026-10-30",
  "is_active": false,
  "is_overdue": false
}
```

Errors: `401` unauthorized; `404` booking not found; `409` booking is not in `borrowed` status.

### DELETE /api/bookings/{id}

Cancels an active reservation (BR-09, BR-11). Transitions status to `cancelled` and restores 1 available copy.

Response `200`:

```json
{
  "id": 101,
  "user_id": 7,
  "book_id": 42,
  "status": "cancelled",
  "created_at": "2026-10-30",
  "due_date": null,
  "returned_at": null,
  "is_active": false,
  "is_overdue": false
}
```

Errors: `401` unauthorized; `404` booking not found; `409` booking is not in `reserved` status (e.g. already borrowed or cancelled).

### GET /api/bookings/me

Returns all bookings for the authenticated member, newest first.

Response `200`:

```json
{
  "items": [
    {
      "id": 101,
      "user_id": 7,
      "book_id": 42,
      "status": "reserved",
      "created_at": "2026-10-30",
      "due_date": null,
      "returned_at": null,
      "is_active": true,
      "is_overdue": false
    }
  ]
}
```

Errors: `401` unauthorized.


## Recommendation Engine (Member 1)

Agreed on 29 Oct 2026. Each recommendation carries `book_id`, `title`, `author`,
`cover_url`, `score`, and `reason`, so Member 2's home page can render cards directly
without additional API roundtrips.

### Common Interface (NFR-R2)

All recommendation algorithms implement the common `Recommender` interface in
`src/recommender/base.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Recommendation:
    book_id: int
    score: float
    reason: str


class Recommender(ABC):
    @abstractmethod
    def recommend(self, user_id: int, n: int = 10) -> list[Recommendation]:
        """Generate top-n recommendations for a given user."""
        ...
```

To swap or test algorithms without touching calling code or routes:

```python
from src.recommender import set_recommender, MyNewRecommender

set_recommender(MyNewRecommender())
```

### In-process function: recommender.get_recommendations(user_id, limit=10)

Member 2's home page service or internal callers can call this in-process Python function
directly:

```python
from src.recommender import get_recommendations

recommendations = get_recommendations(user_id=1, limit=10)
```

Returns a list of enriched dictionaries matching the items in `GET /api/recommendations/me`.

### GET /api/recommendations/me

Returns personalized recommendations for the logged-in user, or cold-start fallback (FR-R1, FR-R3).
Requires authentication (`Authorization: Bearer <token>`).

Query parameters:
- `limit` (integer, optional, default: 10, min: 1, max: 50): Number of recommendations to return.

Response `200`:

```json
{
  "items": [
    {
      "book_id": 42,
      "title": "The Pragmatic Programmer",
      "author": "Andrew Hunt, David Thomas",
      "cover_url": "https://images.example.com/covers/42.jpg",
      "genre": "Technology",
      "score": 0.95,
      "reason": "Popular among library readers"
    }
  ],
  "count": 1
}
```

Errors: `401` not authenticated; `422` invalid limit query parameter.

### POST /api/recommendations/refresh

Triggers a retrain or cache refresh of the recommendation model (FR-R6). Admin only.
Requires admin token (`role: admin`).

Response `200`:

```json
{
  "status": "ok",
  "message": "Recommendation models refreshed successfully"
}
```

Errors: `401` not authenticated; `403` forbidden (if requested by a non-admin member).
