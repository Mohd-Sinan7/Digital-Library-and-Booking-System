"""scripts/start.py (DLBS-42) and the PostgreSQL URL handling in src/db.py."""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.start import check_choice, seed
from src import db
from src.catalog.models import Book


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    db.Base.metadata.create_all(engine)
    yield sessionmaker(engine)
    engine.dispose()


def count_books(session_factory) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(Book))


@pytest.mark.parametrize("value, expected", [
    (None, None), ("", None), ("full", "full"), ("sample", "sample"),
])
def test_seed_choice(value, expected):
    assert check_choice(value) == expected


def test_unknown_seed_choice_is_rejected():
    with pytest.raises(ValueError, match="full or sample"):
        check_choice("all")


def test_seed_adds_the_sample_books(session_factory):
    message = seed("sample", session_factory)

    assert message == "Seeded books from books_sample.csv: 20 added, 0 already there."
    assert count_books(session_factory) == 20


def test_seeding_again_adds_nothing(session_factory):
    seed("sample", session_factory)

    assert seed("sample", session_factory).endswith("0 added, 20 already there.")
    assert count_books(session_factory) == 20


@pytest.mark.parametrize("given, expected", [
    ("postgresql://u:p@host:5432/lib", "postgresql+psycopg://u:p@host:5432/lib"),
    ("postgres://u:p@host/lib", "postgresql+psycopg://u:p@host/lib"),
    ("postgresql+psycopg://u:p@db:5432/lib", "postgresql+psycopg://u:p@db:5432/lib"),
    ("sqlite:///./library.db", "sqlite:///./library.db"),
])
def test_database_url_uses_the_installed_postgres_driver(given, expected):
    assert db.sqlalchemy_url(given) == expected
