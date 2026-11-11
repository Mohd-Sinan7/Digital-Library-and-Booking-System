"""Unit and integration tests for the demo seed script (DLBS-52)."""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.seed_demo import _clamp_reading_fields, main, seed_demo
from src.catalog.models import Book
from src.db import create_tables
from src.recommender import service as recommender_service
from src.users import reading
from src.users.models import ADMIN, MEMBER, ReadingRecordRow, User
from src.users.service import authenticate


@pytest.fixture
def db_session():
    """Isolated in-memory SQLite session matching the shared schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_tables(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_seed_demo_creates_members_admin_and_reading_records(db_session):
    """DLBS-52: Seed demo accounts (via create_user) and linked reading records."""
    summary = seed_demo(
        db=db_session,
        member_limit=4,
        seed_books_mode="sample",
        member_password="MemberPass1",
        admin_password="AdminPass1",
    )

    assert summary["books"] is not None
    assert summary["books"]["loaded"] == 20
    assert summary["members_created"] == 4
    assert summary["admins_created"] == 1
    assert summary["records_loaded"] >= 10

    # Verify admin account and role
    admin_user = authenticate(db_session, "admin@example.com", "AdminPass1")
    assert admin_user is not None
    assert admin_user.role == ADMIN

    # Verify demo member (User 1) authentication and role
    member_user = authenticate(db_session, "member@example.com", "MemberPass1")
    assert member_user is not None
    assert member_user.role == MEMBER

    # Verify all seeded members authenticate properly via Member 3's authenticate()
    members = list(db_session.scalars(select(User).where(User.role == MEMBER)))
    assert len(members) == 4
    for m in members:
        assert authenticate(db_session, m.email, "MemberPass1") is not None

    # Verify reading records match seeded book_ids and Member 3's get_history()
    history = reading.get_history(member_user.id, db=db_session)
    assert len(history) == 10
    seeded_book_ids = set(db_session.scalars(select(Book.id)))
    for rec in history:
        assert rec.book_id in seeded_book_ids
        assert 0.0 <= rec.percent <= 100.0


def test_seed_demo_calls_member3_create_user_function(db_session):
    """DLBS-52: All demo accounts must be created through Member 3's create_user()."""
    from src.users.service import create_user as real_create_user

    with patch("scripts.seed_demo.create_user", wraps=real_create_user) as spy_create:
        seed_demo(db=db_session, member_limit=3, seed_books_mode="sample")
        # 1 admin + 3 members = 4 calls
        assert spy_create.call_count == 4
        roles = [call.kwargs["role"] for call in spy_create.call_args_list]
        assert roles.count(ADMIN) == 1
        assert roles.count(MEMBER) == 3


def test_seed_demo_idempotency(db_session):
    """DLBS-52: Re-running seed_demo skips existing users and reading records."""
    first = seed_demo(db=db_session, member_limit=3, seed_books_mode="sample")
    assert first["members_created"] == 3
    assert first["admins_created"] == 1
    assert first["records_loaded"] >= 10

    second = seed_demo(db=db_session, member_limit=3, seed_books_mode="sample")
    assert second["members_created"] == 0
    assert second["members_skipped"] == 3
    assert second["admins_created"] == 0
    assert second["admins_skipped"] == 1
    assert second["records_loaded"] == 0


def test_seed_demo_works_with_member1_recommender(db_session):
    """DLBS-52: Member 1 can compute personalised recommendations from seeded data."""
    seed_demo(db=db_session, member_limit=5, seed_books_mode="sample")
    member = db_session.scalar(select(User).where(User.email == "member@example.com"))
    assert member is not None

    recs = recommender_service.get_recommendations(user_id=member.id, limit=5, db=db_session)
    assert len(recs) > 0
    for item in recs:
        assert "book_id" in item
        assert item["reason"]


def test_seed_demo_reset_reloads_reading_records(db_session):
    """DLBS-52: reset=True clears and reloads reading records cleanly."""
    first = seed_demo(db=db_session, member_limit=2, seed_books_mode="sample")
    count_before = len(list(db_session.scalars(select(ReadingRecordRow.id))))
    assert count_before == first["records_loaded"]

    refreshed = seed_demo(db=db_session, member_limit=2, seed_books_mode="none", reset=True)
    assert refreshed["records_loaded"] == count_before


def test_clamp_reading_fields_respects_page_bounds():
    """Verify page clamping keeps sample books valid against ReadingRecordRow constraints."""
    assert _clamp_reading_fields("finished", 774, 100.0, 432) == (432, 100.0)
    assert _clamp_reading_fields("want_to_read", 12, 5.0, 432) == (0, 0.0)
    page, pct = _clamp_reading_fields("reading", 500, 99.0, 200)
    assert page == 200
    assert pct == 100.0


def test_seed_demo_missing_files_raise_file_not_found(tmp_path, db_session):
    """Missing CSV inputs raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="Users CSV"):
        seed_demo(
            db=db_session,
            users_path=tmp_path / "missing_users.csv",
            seed_books_mode="none",
        )


def test_seed_demo_cli_entrypoint(monkeypatch, capsys):
    """CLI entrypoint runs cleanly against an isolated database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_tables(engine)
    monkeypatch.setattr("scripts.seed_demo.create_tables", lambda bind=None: create_tables(engine))
    monkeypatch.setattr("scripts.seed_demo.SessionLocal", sessionmaker(engine))

    code = main(["--sample", "--members", "2", "--records-limit", "5"])
    assert code == 0

    captured = capsys.readouterr()
    assert "Demo seed complete" in captured.out
    assert "member@example.com" in captured.out
    assert "admin@example.com" in captured.out
    engine.dispose()
