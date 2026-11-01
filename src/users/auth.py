"""Authentication helper shared by every module.

POST /api/auth/login issues a signed JWT that carries the user's id, name, email and
role. get_current_user() checks the token on every protected endpoint and returns
that CurrentUser, so other modules need no database lookup (NFR-U2).
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Header, HTTPException, status

# Set JWT_SECRET in .env (at least 32 characters). The default is for local use only.
JWT_SECRET = os.getenv("JWT_SECRET", "local-development-secret-not-for-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))


@dataclass(frozen=True)
class CurrentUser:
    """The logged-in user, as other modules see it."""

    id: int
    name: str
    email: str
    role: str


def create_access_token(user: CurrentUser, expires_in: timedelta | None = None) -> str:
    """Return a signed token for the user that expires after JWT_EXPIRE_MINUTES."""
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user.id),
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "iat": now,
        "exp": now + (expires_in or timedelta(minutes=JWT_EXPIRE_MINUTES)),
    }
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """Return the user for the request's bearer token, or reject it with 401 (NFR-U2).

    A missing, malformed, tampered or expired token all get the same 401.
    """
    scheme, _, token = (authorization or "").partition(" ")
    try:
        if scheme.lower() != "bearer":
            raise jwt.InvalidTokenError("not a bearer token")
        claims = jwt.decode(
            token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"require": ["exp", "sub"]}
        )
        return CurrentUser(int(claims["sub"]), claims["name"], claims["email"], claims["role"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
