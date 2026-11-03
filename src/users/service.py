"""Account functions used by the REST routes and by seed scripts.

create_user() is the one way to add a user: registration and Member 4's demo seed
script both call it, so every password is validated and hashed the same way.
"""

import os
import re

import bcrypt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.users.models import ADMIN, MEMBER, User

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72  # bcrypt rejects longer passwords
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailTakenError(ValueError):
    """The email is already registered."""


def normalize_email(email: str) -> str:
    """Return the email trimmed and lower-cased, so Asha@X.com and asha@x.com match."""
    return email.strip().lower()


def check_email(email: str) -> str:
    """Return the normalized email, or raise ValueError if it is not valid (NFR-U3)."""
    email = normalize_email(email)
    if len(email) > 255 or not EMAIL_PATTERN.match(email):
        raise ValueError("Enter a valid email address")
    return email


def check_password(password: str) -> str:
    """Return the password, or raise ValueError if it is weak (NFR-U3).

    A password needs at least 8 characters, including at least one letter and one digit.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must have at least {MIN_PASSWORD_LENGTH} characters")
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise ValueError("Password must contain at least one letter and one digit")
    return password


def hash_password(password: str) -> str:
    """Return a salted bcrypt hash of the password (NFR-U1)."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Return True if the password matches the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_user(db: Session, name: str, email: str, password: str, role: str = MEMBER) -> User:
    """Validate the input, hash the password and save a new user (FR-U1).

    Raises ValueError for invalid input and EmailTakenError for a duplicate email.
    """
    name = name.strip()
    if not name:
        raise ValueError("Name is required")
    email = check_email(email)
    check_password(password)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise EmailTakenError("Email already registered")

    user = User(name=name, email=email, password_hash=hash_password(password), role=role)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Another request registered the same email between the check and the insert.
        db.rollback()
        raise EmailTakenError("Email already registered") from None
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Return the user if the email and password match, otherwise None (FR-U2)."""
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def ensure_admin_account(db: Session) -> User | None:
    """Make sure the first admin from ADMIN_EMAIL and ADMIN_PASSWORD exists (FR-U3).

    Creates the account if the email is new, or gives an existing account the admin
    role (its password is not changed). Returns None when either variable is unset.
    """
    email = os.getenv("ADMIN_EMAIL", "").strip()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not email or not password:
        return None
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        return create_user(db, "Admin", email, password, role=ADMIN)
    if user.role != ADMIN:
        user.role = ADMIN
        db.commit()
    return user
