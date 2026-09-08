"""Shared fixtures. Every test runs against a temporary project root and SQLite file.

Nothing here touches the real ``db.sqlite`` or ``config/user_facts.yaml``, and no test may call
an LLM provider or the network.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from internship_os.config import (
    CITIES_FILE,
    PROGRAMME_CONSTRAINTS_FILE,
    SKILL_EVIDENCE_FILE,
    USER_FACTS_EXAMPLE_FILE,
    AppConfig,
    load_config,
)
from internship_os.db import get_engine, init_db

PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_SRC = PROJECT_DIR / "config"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Date-sensitive tests pin "today" here rather than reading the clock.
TODAY = date(2026, 9, 9)


@pytest.fixture
def today() -> date:
    return TODAY


@pytest.fixture
def project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary project root with the committed config files (not the personal user_facts)."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    for name in (
        USER_FACTS_EXAMPLE_FILE,
        PROGRAMME_CONSTRAINTS_FILE,
        SKILL_EVIDENCE_FILE,
        CITIES_FILE,
    ):
        shutil.copyfile(CONFIG_SRC / name, cfg / name)
    prompts_src = CONFIG_SRC / "llm_prompts"
    if prompts_src.is_dir():
        shutil.copytree(prompts_src, cfg / "llm_prompts")
    monkeypatch.setenv("IOS_ROOT", str(tmp_path))
    monkeypatch.setenv("IOS_DB_URL", f"sqlite:///{tmp_path / 'test.sqlite'}")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def config(project_root: Path) -> AppConfig:
    return load_config(project_root, notice_stream=open(project_root / "notice.log", "w"))


@pytest.fixture
def engine(project_root: Path):
    eng = get_engine(f"sqlite:///{project_root / 'test.sqlite'}")
    init_db(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine) -> Session:
    with Session(engine, expire_on_commit=False) as s:
        yield s
