import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.db import create_tables
from src.users import service
from src.users.auth import CurrentUser, create_access_token, require_admin
from src.users.models import ADMIN, MEMBER, User

MEMBER_TOKEN = create_access_token(CurrentUser(1, "Test Member", "member@example.com", MEMBER))
ADMIN_TOKEN = create_access_token(CurrentUser(2, "Test Admin", "admin@example.com", ADMIN))


@pytest.fixture
def client():
    app = FastAPI()

    @app.post("/admin-only")
    def admin_only(admin: CurrentUser = Depends(require_admin)):
        return {"id": admin.id, "role": admin.role}

    admin_router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])

    @admin_router.get("/stats")
    def stats():
        return {"ok": True}

    app.include_router(admin_router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    create_tables(engine)
    with Session(engine) as session:
        yield session


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("path, method", [("/admin-only", "post"), ("/admin/stats", "get")])
def test_member_is_rejected_from_admin_endpoints(client, path, method):
    response = client.request(method, path, headers=bearer(MEMBER_TOKEN))

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin privileges required"


@pytest.mark.parametrize("path, method", [("/admin-only", "post"), ("/admin/stats", "get")])
def test_admin_is_allowed(client, path, method):
    assert client.request(method, path, headers=bearer(ADMIN_TOKEN)).status_code == 200


def test_admin_endpoint_without_token_is_401(client):
    assert client.post("/admin-only").status_code == 401


def test_admin_account_is_created_from_the_environment(session, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", " Admin@Example.com ")
    monkeypatch.setenv("ADMIN_PASSWORD", "libraryadmin1")

    admin = service.ensure_admin_account(session)

    assert (admin.email, admin.role) == ("admin@example.com", ADMIN)
    assert service.authenticate(session, "admin@example.com", "libraryadmin1") == admin


def test_admin_account_is_created_only_once(session, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "libraryadmin1")

    first = service.ensure_admin_account(session)
    second = service.ensure_admin_account(session)

    assert first.id == second.id
    assert session.scalar(select(func.count()).select_from(User)) == 1


def test_existing_member_with_admin_email_becomes_admin(session, monkeypatch):
    member = service.create_user(session, "Asha Rao", "asha@example.com", "readmore42")
    monkeypatch.setenv("ADMIN_EMAIL", "asha@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "different9")

    admin = service.ensure_admin_account(session)

    assert admin.id == member.id
    assert admin.role == ADMIN
    assert service.verify_password("readmore42", admin.password_hash)


@pytest.mark.parametrize("unset", ["ADMIN_EMAIL", "ADMIN_PASSWORD"])
def test_no_admin_without_both_variables(session, monkeypatch, unset):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "libraryadmin1")
    monkeypatch.delenv(unset)

    assert service.ensure_admin_account(session) is None
    assert session.scalar(select(func.count()).select_from(User)) == 0


def test_weak_admin_password_is_rejected(session, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "change-me")

    with pytest.raises(ValueError):
        service.ensure_admin_account(session)
