"""Request dependencies. Tests override :func:`today` to pin the date."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from sqlalchemy.orm import Session

from internship_os.config import AppConfig, load_config
from internship_os.db import get_session


def get_config() -> AppConfig:
    """Load and validate config/ on every request, so edits to the YAML apply without a restart."""
    return load_config()


def get_db() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def today() -> date:
    return date.today()
