import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import db
from src.main import app, create_app
from src.users.models import ADMIN, User


@pytest.fixture
def test_db(monkeypatch):
    """Point app startup at an in-memory database instead of library.db."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    monkeypatch.setattr(db, "create_tables", lambda: db.Base.metadata.create_all(engine))
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(engine))
    yield engine
    engine.dispose()


def test_health():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_names_the_running_version(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    assert TestClient(app).get("/health").headers["X-App-Version"] == "dev"

    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    assert TestClient(app).get("/health").headers["X-App-Version"] == "abc123"

    monkeypatch.setenv("APP_VERSION", "v1")
    assert TestClient(app).get("/health").headers["X-App-Version"] == "v1"


@pytest.mark.parametrize("path", [
    "/api/auth/register",
    "/api/auth/login",
    "/api/users/me",
    "/api/reading/status",
    "/api/reading/progress",
    "/api/reading/history",
    "/api/reading/stats",
    "/api/books",
    "/api/bookings",
    "/api/recommendations/me",
])
def test_every_module_router_is_mounted(path):
    assert path in app.openapi()["paths"]


def test_startup_creates_tables_and_the_first_admin(test_db, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "libraryadmin1")

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200

    with sessionmaker(test_db)() as session:
        admin = session.scalar(select(User).where(User.email == "admin@example.com"))
    assert admin.role == ADMIN


def test_weak_admin_password_does_not_stop_startup(test_db, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "change-me")

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200

    with sessionmaker(test_db)() as session:
        assert session.scalar(select(User)) is None


@pytest.mark.parametrize("path, text", [
    ("/", "Digital Library"),
    ("/login.html", "Log in"),
    ("/js/app.js", "bookCard"),
    ("/css/app.css", ".nav"),
])
def test_web_pages_are_served(path, text):
    response = TestClient(app).get(path)

    assert response.status_code == 200
    assert text in response.text


def test_api_routes_win_over_web_pages():
    assert TestClient(app).get("/health").json() == {"status": "ok"}
    assert TestClient(app).get("/no-such-page.html").status_code == 404
