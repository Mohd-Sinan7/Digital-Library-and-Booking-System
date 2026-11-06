import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.db import create_tables
from src.users.auth import CurrentUser, create_access_token
from src.users.models import ADMIN, MEMBER, User
from src.users.routes import get_db, profile_router


def bearer(user_id, name="Asha Rao", email="asha@example.com", role=MEMBER):
    token = create_access_token(CurrentUser(user_id, name, email, role))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_tables(engine)
    with Session(engine) as session:
        session.add_all([
            User(id=1, name="Asha Rao", email="asha@example.com", password_hash="hashed"),
            User(id=2, name="Admin", email="admin@example.com", password_hash="hashed",
                 role=ADMIN),
        ])
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def client(session):
    app = FastAPI()
    app.include_router(profile_router)
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as test_client:
        yield test_client


def test_get_profile_returns_id_name_email_and_role(client):
    response = client.get("/api/users/me", headers=bearer(1))

    assert response.status_code == 200
    assert response.json() == {"id": 1, "name": "Asha Rao", "email": "asha@example.com",
                               "role": MEMBER}


def test_admin_profile_shows_the_admin_role(client):
    headers = bearer(2, "Admin", "admin@example.com", ADMIN)

    assert client.get("/api/users/me", headers=headers).json()["role"] == ADMIN


def test_put_changes_the_name_only(client, session):
    response = client.put("/api/users/me", json={"name": "  Asha R.  "}, headers=bearer(1))

    assert response.status_code == 200
    assert response.json() == {"id": 1, "name": "Asha R.", "email": "asha@example.com",
                               "role": MEMBER}
    assert session.get(User, 1).name == "Asha R."


def test_new_name_shows_in_the_profile(client):
    client.put("/api/users/me", json={"name": "Asha R."}, headers=bearer(1))

    assert client.get("/api/users/me", headers=bearer(1)).json()["name"] == "Asha R."


@pytest.mark.parametrize("body", [
    {"name": "Asha R.", "email": "new@example.com"},
    {"name": "Asha R.", "role": ADMIN},
    {"name": ""},
    {"name": "   "},
    {"name": "x" * 101},
    {},
])
def test_invalid_profile_changes_are_422_and_change_nothing(client, session, body):
    response = client.put("/api/users/me", json=body, headers=bearer(1))

    assert response.status_code == 422
    user = session.get(User, 1)
    assert (user.name, user.email, user.role) == ("Asha Rao", "asha@example.com", MEMBER)


def test_profile_of_a_removed_account_is_404(client):
    assert client.get("/api/users/me", headers=bearer(99)).status_code == 404
    assert client.put("/api/users/me", json={"name": "X"}, headers=bearer(99)).status_code == 404


@pytest.mark.parametrize("method", ["get", "put"])
def test_profile_needs_a_token(client, method):
    assert client.request(method, "/api/users/me").status_code == 401
