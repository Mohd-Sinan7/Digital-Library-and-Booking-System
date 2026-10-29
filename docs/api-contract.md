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

### Stub tokens (until real login is merged on 31 Oct)

| Header | You are |
|---|---|
| `Authorization: Bearer test-member-token` | User 1, Test Member, role `member` |
| `Authorization: Bearer test-admin-token` | User 2, Test Admin, role `admin` |

Any other token, or no token, gets 401. After 31 Oct, get a real token from
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
filter: `?status=finished`. Member 1 uses this for recommendations.

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

### Question for Member 1

The endpoints above only return the logged-in user's own data. A popularity score
needs read counts across all users. Because everything runs in one app, the plan is
to also expose Python functions in `src/users/` that the recommender can call
directly, for example `get_history(user_id)` and `get_read_counts()`. Confirm the
names and return shapes in this section.

---

## Book Catalog (Member 2)

To be filled in by Member 2 on 29 Oct. Already agreed in the member plans:

- The book JSON includes `page_count` (Member 3 uses it for progress) and
  `available_copies` (only Member 4's booking code changes it).
- `GET /api/books?q=&genre=&available=&page=` for search, filter and list
- `GET /api/books/{id}`; `POST`, `PUT` and `DELETE /api/books/{id}` for admins
- `GET /api/books/{id}/availability` returns `available_copies`

## Booking and Borrowing (Member 4)

To be filled in by Member 4 on 29 Oct. Endpoints: `POST /api/bookings`,
`POST /api/bookings/{id}/borrow`, `POST /api/bookings/{id}/return`,
`DELETE /api/bookings/{id}`, `GET /api/bookings/me`.

## Recommendation Engine (Member 1)

To be filled in by Member 1 on 29 Oct. Already agreed: each recommendation carries
`book_id`, `title`, `author`, `cover_url`, `score` and `reason`. Endpoints:
`GET /api/recommendations/me?limit=10` and `POST /api/recommendations/refresh` (admin).
