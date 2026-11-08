"""Database setup shared by every module: the engine, sessions and the table base class.

Each module defines its tables as subclasses of Base. DATABASE_URL comes from the
environment (see .env.example) and defaults to a local SQLite file.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def sqlalchemy_url(url: str) -> str:
    """Use the psycopg driver for PostgreSQL URLs.

    Hosts such as Render give the URL as postgresql://... or postgres://..., which
    SQLAlchemy would open with a different driver (psycopg2) that is not installed.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = sqlalchemy_url(os.getenv("DATABASE_URL", "sqlite:///./library.db"))

# SQLite connections are used across FastAPI's worker threads.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# pool_pre_ping replaces connections the database server has closed while idle.
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    """Base class for every table."""


def create_tables(bind=engine):
    """Create every table whose model has been imported and does not exist yet."""
    Base.metadata.create_all(bind)
