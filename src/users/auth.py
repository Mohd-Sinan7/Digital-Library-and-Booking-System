"""Authentication helper shared by every module.

STUB (29 Oct): the token is looked up in a fixed table of test users, so other
modules can protect their endpoints before real login exists. By 1 Nov the body
of get_current_user() switches to JWT validation; its signature and CurrentUser
stay the same, so callers do not change.
"""

from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from src.users.models import ADMIN, MEMBER


@dataclass(frozen=True)
class CurrentUser:
    """The logged-in user, as other modules see it."""

    id: int
    name: str
    email: str
    role: str


# Stub tokens and the fixed test users they map to. Removed when JWT login lands.
STUB_MEMBER_TOKEN = "test-member-token"
STUB_ADMIN_TOKEN = "test-admin-token"
_STUB_USERS = {
    STUB_MEMBER_TOKEN: CurrentUser(1, "Test Member", "member@example.com", MEMBER),
    STUB_ADMIN_TOKEN: CurrentUser(2, "Test Admin", "admin@example.com", ADMIN),
}


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """Return the user for the request's bearer token, or reject it with 401 (NFR-U2)."""
    scheme, _, token = (authorization or "").partition(" ")
    user = _STUB_USERS.get(token) if scheme.lower() == "bearer" else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
