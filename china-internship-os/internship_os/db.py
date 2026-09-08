"""Engine and session helpers. SQLite only; no migrations in Phase 1."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from internship_os.config import project_root
from internship_os.models import Base

DB_FILENAME = "db.sqlite"
DB_URL_ENV_VAR = "IOS_DB_URL"

_engines: dict[str, Engine] = {}


def database_url(root: Path | str | None = None) -> str:
    """``IOS_DB_URL`` if set, else ``sqlite:///<project root>/db.sqlite``."""
    env = os.environ.get(DB_URL_ENV_VAR)
    if env:
        return env
    return f"sqlite:///{project_root(root) / DB_FILENAME}"


def get_engine(url: str | None = None) -> Engine:
    """Return a cached engine for ``url`` (default :func:`database_url`)."""
    resolved = url or database_url()
    engine = _engines.get(resolved)
    if engine is None:
        engine = create_engine(resolved, future=True)
        if engine.dialect.name == "sqlite":

            @event.listens_for(engine, "connect")
            def _enable_foreign_keys(dbapi_connection, _record):  # pragma: no cover
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        _engines[resolved] = engine
    return engine


def get_session(engine: Engine | None = None) -> Session:
    """A new ORM session bound to ``engine`` (default :func:`get_engine`)."""
    factory = sessionmaker(bind=engine or get_engine(), expire_on_commit=False)
    return factory()


def init_db(engine: Engine | None = None) -> Engine:
    """Create all tables if they do not exist. Never drops anything."""
    resolved = engine or get_engine()
    Base.metadata.create_all(resolved)
    return resolved
