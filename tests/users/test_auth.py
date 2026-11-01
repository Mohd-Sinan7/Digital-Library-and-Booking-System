from datetime import timedelta

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.db import create_tables
from src.users import service
from src.users.auth import (
    JWT_ALGORITHM,
    JWT_SECRET,
    CurrentUser,
    create_access_token,
    get_current_user,
)
from src.users.models import MEMBER, User
from src.users.routes import get_db, router

ASHA = {"name": "Asha Rao", "email": "asha@example.com", "password": "readmore42"}


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_tables(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(session):
    app = FastAPI()
    app.include_router(router)

    @app.get("/whoami")
    def whoami(user: CurrentUser = Depends(get_current_user)):
        return {"id": user.id, "email": user.email, "role": user.role}

    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as test_client:
        yield test_client


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_creates_a_member(client):
    response = client.post("/api/auth/register", json=ASHA)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Asha Rao"
    assert body["email"] == "asha@example.com"
    assert body["role"] == MEMBER
    assert body["created_at"].endswith("Z")
    assert "password" not in body and "password_hash" not in body


def test_password_is_stored_hashed(client, session):
    client.post("/api/auth/register", json=ASHA)

    stored = session.query(User).one().password_hash
    assert stored != ASHA["password"]
    assert service.verify_password(ASHA["password"], stored)


def test_duplicate_email_is_rejected(client):
    client.post("/api/auth/register", json=ASHA)

    response = client.post("/api/auth/register", json={**ASHA, "email": "ASHA@example.com"})

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


@pytest.mark.parametrize("password", ["short1", "onlyletters", "12345678", "a1" * 40])
def test_weak_password_is_rejected(client, password):
    response = client.post("/api/auth/register", json={**ASHA, "password": password})

    assert response.status_code == 422


@pytest.mark.parametrize("email", ["not-an-email", "asha@", "@example.com", "a b@example.com"])
def test_invalid_email_is_rejected(client, email):
    response = client.post("/api/auth/register", json={**ASHA, "email": email})

    assert response.status_code == 422


def test_missing_name_is_rejected(client):
    response = client.post("/api/auth/register", json={**ASHA, "name": ""})

    assert response.status_code == 422


def test_login_returns_a_token_that_protected_endpoints_accept(client):
    user_id = client.post("/api/auth/register", json=ASHA).json()["id"]

    response = client.post(
        "/api/auth/login", json={"email": "Asha@Example.com", "password": "readmore42"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["user"] == {"id": user_id, "name": "Asha Rao",
                            "email": "asha@example.com", "role": MEMBER}
    me = client.get("/whoami", headers=bearer(body["access_token"]))
    assert me.json() == {"id": user_id, "email": "asha@example.com", "role": MEMBER}


@pytest.mark.parametrize("email, password", [
    ("asha@example.com", "wrongpass1"),
    ("nobody@example.com", "readmore42"),
])
def test_wrong_password_or_unknown_email_gets_the_same_401(client, email, password):
    client.post("/api/auth/register", json=ASHA)

    response = client.post("/api/auth/login", json={"email": email, "password": password})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_logout_needs_a_token(client):
    token = create_access_token(CurrentUser(1, "Asha Rao", "asha@example.com", MEMBER))

    assert client.post("/api/auth/logout", headers=bearer(token)).status_code == 204
    assert client.post("/api/auth/logout").status_code == 401


def test_missing_token_is_rejected(client):
    response = client.get("/whoami")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_expired_token_is_rejected(client):
    user = CurrentUser(1, "Asha Rao", "asha@example.com", MEMBER)
    token = create_access_token(user, expires_in=timedelta(seconds=-1))

    assert client.get("/whoami", headers=bearer(token)).status_code == 401


@pytest.mark.parametrize("header", [
    "Bearer not-a-jwt",
    "Bearer test-member-token",
    "Basic YXNoYTpyZWFkbW9yZTQy",
    "Bearer " + jwt.encode({"sub": "1", "exp": 4102444800}, "x" * 32, algorithm="HS256"),
    "Bearer " + jwt.encode({"sub": "1"}, JWT_SECRET, algorithm=JWT_ALGORITHM),
])
def test_invalid_tokens_are_rejected(client, header):
    """Covers malformed, old stub, wrong scheme, wrong signature and no expiry."""
    assert client.get("/whoami", headers={"Authorization": header}).status_code == 401


def test_create_user_is_shared_by_registration_and_seed_scripts(session):
    user = service.create_user(session, " Asha Rao ", " Asha@Example.com ", "readmore42")

    assert (user.name, user.email, user.role) == ("Asha Rao", "asha@example.com", MEMBER)
    with pytest.raises(service.EmailTakenError):
        service.create_user(session, "Asha Again", "asha@example.com", "readmore42")
    with pytest.raises(ValueError):
        service.create_user(session, "  ", "new@example.com", "readmore42")


def test_verify_password_rejects_garbage_hash():
    assert not service.verify_password("readmore42", "not-a-bcrypt-hash")
