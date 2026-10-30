"""Database setup shared by every module: the engine, sessions and the table base class.

Each module defines its tables as subclasses of Base. DATABASE_URL comes from the
environment (see .env.example) and defaults to a local SQLite file.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./library.db")

# SQLite connections are used across FastAPI's worker threads.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    """Base class for every table."""


def create_tables(bind=engine):
    """Create every table whose model has been imported and does not exist yet."""
    Base.metadata.create_all(bind)
