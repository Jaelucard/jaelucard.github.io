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


# --------------------------------------------------------------------------------------
# Fake LLM. No test may contact Anthropic, Ollama or the network.
# --------------------------------------------------------------------------------------

import json  # noqa: E402
import re  # noqa: E402

from internship_os import llm  # noqa: E402
from internship_os.config import AppConfig as _AppConfig  # noqa: E402
from internship_os.schemas import ExtractedJob  # noqa: E402

FIXTURE_NAMES = ("hangzhou_ai_app", "shanghai_llm_algorithm", "suzhou_backend")
_JD_BLOCK = re.compile(r"<jd>\n(.*?)\n</jd>", re.DOTALL)


def load_jd(name: str) -> str:
    return (FIXTURES_DIR / "jds" / f"{name}.txt").read_text(encoding="utf-8")


def load_extracted_json(name: str) -> str:
    return (FIXTURES_DIR / "extracted" / f"{name}.json").read_text(encoding="utf-8")


def load_extracted(name: str, *, confirmed: bool = False) -> ExtractedJob:
    data = json.loads(load_extracted_json(name))
    if confirmed:
        for field in data.values():
            field["confirmed"] = True
    return ExtractedJob.model_validate(data)


def fixture_for_prompt(prompt: str) -> str:
    """Pick the canned extraction whose JD text is inside the rendered prompt's <jd> block."""
    match = _JD_BLOCK.search(prompt)
    jd_text = match.group(1) if match else prompt
    for name in FIXTURE_NAMES:
        if load_jd(name).strip() == jd_text.strip():
            return load_extracted_json(name)
    for key, name in (("苏州", "suzhou_backend"), ("上海", "shanghai_llm_algorithm")):
        if key in jd_text:
            return load_extracted_json(name)
    return load_extracted_json("hangzhou_ai_app")


# The unpatched CLI wrapper, captured before the autouse guard replaces it, for tests that stub subprocess.run.
ORIGINAL_CLAUDE_CODE_CALL = llm._claude_code_call


@pytest.fixture(autouse=True)
def _no_real_llm_providers(monkeypatch: pytest.MonkeyPatch):
    """Every test: a real provider call is a failure, whether or not fake_llm is requested."""

    def _blocked(*_a, **_k):
        raise AssertionError("test attempted to call a real LLM provider")

    monkeypatch.setattr(llm, "_claude_code_call", _blocked)
    monkeypatch.setattr(llm, "_ollama_call", _blocked)
    # Also the primitives underneath, so no test can spawn the real claude binary or POST to
    # Ollama by calling the unpatched wrappers; tests that want a fake CLI re-patch these.
    monkeypatch.setattr(llm.subprocess, "run", _blocked)
    monkeypatch.setattr(llm.httpx, "post", _blocked)
    monkeypatch.setattr(llm, "_sleep", lambda s: pytest.fail(f"unexpected sleep({s})"))


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch):
    """Canned provider keyed by prompt name. Other prompts raise unless a test overrides."""
    responses: dict[str, object] = {}

    def provider(prompt_name: str, prompt: str) -> str:
        handler = responses.get(prompt_name)
        if handler is None:
            if prompt_name == "extract_job":
                return fixture_for_prompt(prompt)
            raise AssertionError(f"no fake response registered for prompt {prompt_name}")
        return handler(prompt) if callable(handler) else str(handler)

    llm.set_fake_provider(provider)
    yield responses
    llm.set_fake_provider(None)


@pytest.fixture
def capture_fixture(session, config: _AppConfig, fake_llm, today):
    """Capture one of the three JD fixtures through the real capture path with the fake LLM."""
    from internship_os.capture import capture

    def _capture(name: str, source: str = "shixiseng", url: str | None = None, **kwargs):
        return capture(load_jd(name), url, source, session=session, config=config, today=today, **kwargs)

    return _capture


# --------------------------------------------------------------------------------------
# Confirmed-job factory for the deterministic modules (Checkpoint 3 onward)
# --------------------------------------------------------------------------------------

from internship_os.capture import refresh_display_fields  # noqa: E402
from internship_os.models import Company, Job, utcnow  # noqa: E402
from internship_os.pipeline import run_checks  # noqa: E402


@pytest.fixture
def make_confirmed_job(session, config, today):
    """Build a Job whose extraction is fully confirmed, optionally overriding extracted values.

    ``run=True`` runs eligibility, programme and tiering with the pinned date.
    """

    def _make(
        name: str = "hangzhou_ai_app",
        *,
        company: bool = True,
        yes_status: str = "unknown",
        host_type: str = "unknown",
        run: bool = True,
        source: str = "shixiseng",
        **field_values,
    ) -> Job:
        data = json.loads(load_extracted_json(name))
        for fld in data.values():
            fld["confirmed"] = True
        for key, value in field_values.items():
            data[key]["value"] = value
            data[key]["source_span"] = None
        extracted = ExtractedJob.model_validate(data)
        job = Job(
            source_channel=source,
            raw_text=load_jd(name),
            extracted=extracted.model_dump(mode="json"),
            confirmed_at=utcnow(),
            next_action="assess fit",
            next_action_date=today,
        )
        refresh_display_fields(job, extracted)
        if company:
            job.company = Company(
                name_zh=extracted.company_name_zh.value,
                name_en=extracted.company_name_en.value,
                city_zh=job.city_zh,
                yes_status=yes_status,
                host_type=host_type,
            )
        session.add(job)
        session.commit()
        if run:
            run_checks(job, config, today)
            session.commit()
        return job

    return _make
