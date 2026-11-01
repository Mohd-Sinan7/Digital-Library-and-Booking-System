"""REST endpoints for registration, login and logout (FR-U1, FR-U2)."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from src.db import SessionLocal
from src.users import service
from src.users.auth import JWT_EXPIRE_MINUTES, CurrentUser, create_access_token, get_current_user
from src.users.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_db():
    """Dependency yielding a database session."""
    with SessionLocal() as db:
        yield db


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, email: str) -> str:
        return service.check_email(email)

    @field_validator("password")
    @classmethod
    def strong_password(cls, password: str) -> str:
        return service.check_password(password)


class LoginRequest(BaseModel):
    email: str
    password: str


def user_json(user: User) -> dict:
    """User JSON shape from docs/api-contract.md."""
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Create a member account (FR-U1). 409 if the email is already registered."""
    try:
        user = service.create_user(db, body.name, body.email, body.password)
    except service.EmailTakenError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from None
    # Stored as UTC; SQLite drops the timezone, so format it explicitly.
    created_at = user.created_at.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"
    return {**user_json(user), "created_at": created_at}


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Check the email and password and return a bearer token (FR-U2)."""
    user = service.authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    token = create_access_token(CurrentUser(user.id, user.name, user.email, user.role))
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRE_MINUTES * 60,
        "user": user_json(user),
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: CurrentUser = Depends(get_current_user)):
    """Log out (FR-U2). Tokens are stateless, so the client deletes its stored token."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)
