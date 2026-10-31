import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db import create_tables
from src.users.models import ADMIN, MEMBER, User


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    create_tables(engine)
    return engine


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


def add_user(session, **overrides):
    fields = {"name": "Asha Rao", "email": "asha@example.com", "password_hash": "hashed"}
    fields.update(overrides)
    user = User(**fields)
    session.add(user)
    session.commit()
    return user


def test_users_table_has_the_designed_columns(engine):
    columns = {column["name"] for column in inspect(engine).get_columns("users")}

    assert columns == {"id", "name", "email", "password_hash", "role", "created_at"}


def test_new_user_is_a_member_with_an_id_and_created_at(session):
    user = add_user(session)

    assert user.id is not None
    assert user.role == MEMBER
    assert user.created_at is not None


def test_admin_role_is_allowed(session):
    assert add_user(session, role=ADMIN).role == ADMIN


def test_unknown_role_is_rejected(session):
    with pytest.raises(IntegrityError):
        add_user(session, role="librarian")


def test_duplicate_email_is_rejected(session):
    add_user(session)

    with pytest.raises(IntegrityError):
        add_user(session, name="Someone Else")


@pytest.mark.parametrize("field", ["name", "email", "password_hash"])
def test_required_fields_cannot_be_missing(session, field):
    with pytest.raises(IntegrityError):
        add_user(session, **{field: None})
