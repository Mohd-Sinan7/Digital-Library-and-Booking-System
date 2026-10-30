"""HTTP routes are defined after shared auth, DB session and catalog interfaces are confirmed.

Agreed paths from docs/api-contract.md:
- POST /api/bookings
- POST /api/bookings/{id}/borrow
- POST /api/bookings/{id}/return
- DELETE /api/bookings/{id}
- GET /api/bookings/me

Do not mount this placeholder router in src/main.py yet.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/bookings", tags=["bookings"])
