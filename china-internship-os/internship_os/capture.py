"""Capture a job description (pasted text or one user-supplied URL) into a Job.

Rules enforced here:

* the only network fetch is a GET of a URL the user pasted; anything that needs login, blocks
  the request or has no usable job content fails with :class:`CaptureNeedsPaste`;
* every extracted field is forced to ``confirmed: false`` after parsing, whatever the model said;
* duplicates are never merged silently: :class:`DuplicateCaptureNeedsDecision` is raised and the
  CLI asks the user what to do.

This module never asks terminal questions itself.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Callable, Iterable, get_args, get_origin

import httpx
import trafilatura
from sqlalchemy import select
from sqlalchemy.orm import Session

from internship_os import llm
from internship_os.config import AppConfig
from internship_os.models import Company, Job, JobEvent
from internship_os.schemas import (
    EventKind,
    Extracted,
    ExtractedJob,
    JobStatus,
    SourceChannel,
    force_unconfirmed,
    normalise_city,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
FETCH_TIMEOUT_SECONDS = 10.0
MAX_REDIRECTS = 5
MIN_USEFUL_CHARS = 300
PASTE_INSTRUCTION = "Paste the job description text instead: ios capture --paste --source <channel>"
INITIAL_NEXT_ACTION = "confirm extraction"
POST_CONFIRM_NEXT_ACTION = "assess fit"

LOGIN_WALL_MARKERS = (
    "请登录",
    "请先登录",
    "登录后查看",
    "登录/注册",
    "登录或注册",
    "扫码登录",
    "sign in to view",
    "log in to view",
    "login to view",
    "please log in",
    "please sign in",
    "sign in to continue",
)
JD_MARKERS = (
    "实习",
    "岗位",
    "职责",
    "任职",
    "要求",
    "招聘",
    "职位",
    "intern",
    "responsibilit",
    "requirement",
    "qualification",
    "job description",
)


class CaptureError(Exception):
    """Capture could not proceed."""


class CaptureNeedsPaste(CaptureError):
    """URL capture failed; the user should paste the text instead."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"{reason}. {PASTE_INSTRUCTION}")


class DuplicateCaptureNeedsDecision(CaptureError):
    """A possible duplicate exists. The caller must ask the user; nothing was saved."""

    def __init__(
        self,
        candidate_ids: list[int],
        *,
        extracted: ExtractedJob,
        text: str,
        url: str | None,
        source_channel: str,
    ):
        self.candidate_ids = candidate_ids
        self.extracted = extracted
        self.text = text
        self.url = url
        self.source_channel = source_channel
        ids = ", ".join(str(i) for i in candidate_ids)
        super().__init__(f"possible duplicate of existing job(s): {ids}")


# --------------------------------------------------------------------------------------
# URL capture: a single GET, bounded redirects, paste fallback on anything unusual.
# --------------------------------------------------------------------------------------


def looks_like_login_wall(text: str) -> bool:
    lowered = text.casefold()
    return any(marker.casefold() in lowered for marker in LOGIN_WALL_MARKERS)


def looks_like_job_description(text: str) -> bool:
    lowered = text.casefold()
    return sum(1 for marker in JD_MARKERS if marker in lowered) >= 2


def fetch_url_text(url: str) -> str:
    """GET ``url`` (following at most MAX_REDIRECTS redirects) and return visible text.

    Raises :class:`CaptureNeedsPaste` for every failure mode. Never POSTs anything.
    """
    if not url.lower().startswith(("http://", "https://")):
        raise CaptureNeedsPaste("the URL must start with http:// or https://")
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    current = url
    response: httpx.Response | None = None
    try:
        for _ in range(MAX_REDIRECTS + 1):
            if not current.lower().startswith(("http://", "https://")):
                raise CaptureNeedsPaste("a redirect left http/https")
            response = httpx.get(
                current, headers=headers, timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=False
            )
            if response.is_redirect and "location" in response.headers:
                current = str(response.url.join(response.headers["location"]))
                continue
            break
        else:
            raise CaptureNeedsPaste("too many redirects")
    except httpx.HTTPError as exc:
        raise CaptureNeedsPaste(f"could not fetch the URL ({type(exc).__name__})") from exc
    assert response is not None
    if response.is_redirect:
        raise CaptureNeedsPaste("too many redirects")
    if response.status_code in (401, 403):
        raise CaptureNeedsPaste(f"the page refused the request (HTTP {response.status_code})")
    if response.status_code >= 400:
        raise CaptureNeedsPaste(f"the page returned HTTP {response.status_code}")
    text = trafilatura.extract(response.text, include_comments=False, include_tables=True) or ""
    text = text.strip()
    if not text:
        raise CaptureNeedsPaste("no readable text could be extracted from the page")
    if looks_like_login_wall(text):
        raise CaptureNeedsPaste("the page appears to require login")
    if len(text) < MIN_USEFUL_CHARS:
        raise CaptureNeedsPaste(
            f"only {len(text)} characters of useful content were extracted (need {MIN_USEFUL_CHARS})"
        )
    if not looks_like_job_description(text):
        raise CaptureNeedsPaste("the page content does not look like a job description")
    return text


# --------------------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------------------


def extract_job(text: str, config: AppConfig) -> ExtractedJob:
    """Run the extraction prompt and force every field to ``confirmed: false``."""
    result = llm.complete("extract_job", {"text": text}, ExtractedJob, config=config)
    assert isinstance(result, ExtractedJob)
    data = force_unconfirmed(result.model_dump(mode="json"))
    return ExtractedJob.model_validate(data)


# --------------------------------------------------------------------------------------
# Deduplication: normalised company + title + city key, plus source URL.
# --------------------------------------------------------------------------------------

_WS = re.compile(r"\s+")
COMPANY_SUFFIXES = ("有限公司", "公司", "科技")
NO_TITLE_KEY = "<no-title>"


def normalise_text(value: str | None) -> str:
    if not value:
        return ""
    return _WS.sub(" ", value.strip()).casefold()


def normalise_company(name: str | None) -> str:
    key = normalise_text(name)
    changed = True
    while changed and key:
        changed = False
        for suffix in COMPANY_SUFFIXES:
            if key.endswith(suffix) and len(key) > len(suffix):
                key = key[: -len(suffix)].strip()
                changed = True
    return key


def normalise_title(title: str | None) -> str:
    return normalise_text(title)


def dedup_keys(
    company_names: Iterable[str | None], titles: Iterable[str | None], city: str | None
) -> set[str]:
    companies = {normalise_company(n) for n in company_names if n}
    companies.discard("")
    names = {normalise_title(t) for t in titles if t}
    names.discard("")
    if not names:
        # No title at all: fall back to a company + city key so the user is still asked.
        names = {NO_TITLE_KEY}
    city_key = normalise_city(city)
    return {f"{c}|{t}|{city_key}" for c in companies for t in names}


def keys_for_extracted(extracted: ExtractedJob) -> set[str]:
    return dedup_keys(
        [extracted.company_name_zh.value, extracted.company_name_en.value],
        [extracted.title_zh.value, extracted.title_en.value],
        extracted.city_zh.value,
    )


def keys_for_job(job: Job) -> set[str]:
    companies: list[str | None] = [job.company.name_zh, job.company.name_en] if job.company else []
    titles: list[str | None] = [job.title_zh, job.title_en]
    city = job.city_zh
    if job.extracted:
        try:
            extracted = ExtractedJob.model_validate(job.extracted)
        except Exception:  # pragma: no cover - defensive against hand-edited rows
            extracted = None
        if extracted is not None:
            companies += [extracted.company_name_zh.value, extracted.company_name_en.value]
            titles += [extracted.title_zh.value, extracted.title_en.value]
            city = city or extracted.city_zh.value
    return dedup_keys(companies, titles, city)


def find_duplicate_ids(session: Session, source_url: str | None, keys: set[str]) -> list[int]:
    """Existing job ids that share ``source_url`` (any status) or a key (non-terminal only)."""
    found: list[int] = []
    for job in session.scalars(select(Job).order_by(Job.id)):
        if source_url and job.source_url and job.source_url == source_url:
            found.append(job.id)
            continue
        if keys and job.status in _NON_TERMINAL and keys & keys_for_job(job):
            found.append(job.id)
    return found


_NON_TERMINAL = frozenset(
    s.value
    for s in JobStatus
    if s not in (JobStatus.INELIGIBLE, JobStatus.REJECTED, JobStatus.WITHDRAWN, JobStatus.CLOSED)
)


# --------------------------------------------------------------------------------------
# Core capture
# --------------------------------------------------------------------------------------


def capture(
    text: str | None,
    url: str | None,
    source_channel: str,
    *,
    session: Session,
    config: AppConfig,
    today: date | None = None,
    extracted: ExtractedJob | None = None,
    force_new: bool = False,
) -> Job:
    """Create a DISCOVERED job from pasted text or a fetched URL.

    ``extracted`` lets a caller reuse a result already returned inside a
    :class:`DuplicateCaptureNeedsDecision`; ``force_new`` skips duplicate detection after the
    user explicitly chose to create a separate job.
    """
    channel = SourceChannel(source_channel).value
    if text is None and url is None:
        raise CaptureError("supply job text or a URL")
    if text is None:
        assert url is not None
        text = fetch_url_text(url)
    text = text.strip()
    if not text:
        raise CaptureError("the job text is empty")

    if extracted is None:
        extracted = extract_job(text, config)
    else:
        extracted = ExtractedJob.model_validate(force_unconfirmed(extracted.model_dump(mode="json")))

    if not force_new:
        duplicates = find_duplicate_ids(session, url, keys_for_extracted(extracted))
        if duplicates:
            raise DuplicateCaptureNeedsDecision(
                duplicates, extracted=extracted, text=text, url=url, source_channel=channel
            )

    when = today or date.today()
    job = Job(
        source_channel=channel,
        source_url=url,
        raw_text=text,
        extracted=extracted.model_dump(mode="json"),
        # Candidate display titles only; deterministic modules ignore them until confirmation.
        title_en=extracted.title_en.value,
        title_zh=extracted.title_zh.value,
        status=JobStatus.DISCOVERED.value,
        next_action=INITIAL_NEXT_ACTION,
        next_action_date=when,
    )
    session.add(job)
    session.flush()
    session.add(
        JobEvent(
            job_id=job.id,
            kind=EventKind.captured.value,
            detail={"source_channel": channel, "source_url": url, "chars": len(text)},
        )
    )
    session.commit()
    return job


def attach_to_existing(
    session: Session, job_id: int, *, text: str, url: str | None, source_channel: str
) -> JobEvent:
    """Record a duplicate capture as a note on an existing job. Creates no Job row."""
    job = session.get(Job, job_id)
    if job is None:
        raise CaptureError(f"job {job_id} does not exist")
    event = JobEvent(
        job_id=job.id,
        kind=EventKind.note.value,
        detail={
            "note": "duplicate capture attached",
            "source_channel": source_channel,
            "source_url": url,
            "raw_text": text,
        },
    )
    session.add(event)
    session.commit()
    return event


# --------------------------------------------------------------------------------------
# Confirmation data handling (the interactive loop lives in the CLI)
# --------------------------------------------------------------------------------------

ACCEPT = ""
ACCEPT_ALL = "a"
SET_NULL = "-"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Override:
    field: str
    old: Any
    new: Any


def _parse_scalar(inner: Any, raw: str) -> Any:
    if inner is str:
        return raw
    if inner is bool:
        lowered = raw.lower()
        if lowered in ("true", "false"):
            return lowered == "true"
        raise ValueError("enter true or false")
    if inner is int:
        try:
            return int(raw)
        except ValueError:
            raise ValueError("enter an integer") from None
    if inner is date:
        if not _DATE.match(raw):
            raise ValueError("enter a date as YYYY-MM-DD")
        return date.fromisoformat(raw)
    if isinstance(inner, type) and issubclass(inner, StrEnum):
        try:
            return inner(raw)
        except ValueError:
            allowed = ", ".join(m.value for m in inner)
            raise ValueError(f"enter one of: {allowed}") from None
    raise ValueError(f"unsupported field type {inner}")


def parse_override(name: str, raw: str) -> Any:
    """Parse a typed user override for extracted field ``name``.

    Lists accept JSON list syntax (``["a", "b"]``) or comma-separated values (``a, b``).
    Dates must be YYYY-MM-DD; booleans ``true``/``false``; enums must be an allowed value.
    """
    inner = ExtractedJob.inner_type(name)
    raw = raw.strip()
    if get_origin(inner) is list:
        (elem,) = get_args(inner)
        if raw.startswith("["):
            try:
                items = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON list: {exc}") from None
            if not isinstance(items, list):
                raise ValueError("enter a JSON list")
            items = [str(i) for i in items]
        else:
            items = [part.strip() for part in raw.split(",") if part.strip()]
        value: Any = [_parse_scalar(elem, str(item)) for item in items]
    else:
        value = _parse_scalar(inner, raw)
    return Extracted[inner](value=value, confirmed=True).value  # type: ignore[valid-type]


Decide = Callable[[str, Extracted[Any], str | None], str]


def apply_confirmation(
    extracted: ExtractedJob, decide: Decide
) -> tuple[ExtractedJob, list[Override]]:
    """Walk every field, asking ``decide`` for the user's input, and return the confirmed job.

    ``decide(field_name, field, error)`` returns the raw input: empty string confirms, ``-``
    sets null, ``a`` accepts the current and all remaining fields, anything else overrides.
    """
    overrides: list[Override] = []
    accept_all = False
    for name in ExtractedJob.field_names():
        field = extracted.get(name)
        if accept_all:
            field.confirmed = True
            continue
        error: str | None = None
        while True:
            raw = decide(name, field, error)
            if raw == ACCEPT:
                field.confirmed = True
                break
            if raw.strip() == ACCEPT_ALL:
                field.confirmed = True
                accept_all = True
                break
            try:
                new_value = None if raw.strip() == SET_NULL else parse_override(name, raw)
            except ValueError as exc:
                error = str(exc)
                continue
            old_value = field.value
            if new_value != old_value:
                overrides.append(Override(name, _jsonable(old_value), _jsonable(new_value)))
                field.source_span = None
            field.value = new_value
            field.confirmed = True
            break
    # Re-validate so sentinel fields cleared to null pick up their sentinel again.
    confirmed = ExtractedJob.model_validate(extracted.model_dump(mode="json"))
    return confirmed, overrides


def _jsonable(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def refresh_display_fields(job: Job, extracted: ExtractedJob) -> None:
    """Copy confirmed extraction into the top-level display and decision columns."""
    job.title_en = extracted.confirmed_value("title_en")
    job.title_zh = extracted.confirmed_value("title_zh")
    job.city_zh = extracted.confirmed_value("city_zh")
    job.deadline = extracted.confirmed_value("deadline")
    job.start_date = extracted.confirmed_value("start_date")
    dmin = extracted.confirmed_value("duration_min_months")
    dmax = extracted.confirmed_value("duration_max_months")
    job.duration_months = dmin if dmin is not None and dmin == dmax else None
    job.track = extracted.confirmed_value("track_guess").value


# --------------------------------------------------------------------------------------
# Company matching
# --------------------------------------------------------------------------------------

NEAR_MATCH_THRESHOLD = 0.8  # difflib ratio on normalised names; documented, fixed


def find_company_matches(
    session: Session, name_zh: str | None, name_en: str | None
) -> tuple[Company | None, list[Company]]:
    """Exact normalised match on either name, else plausible near matches (never auto-linked)."""
    wanted = {normalise_company(n) for n in (name_zh, name_en) if n}
    wanted.discard("")
    near: list[tuple[float, Company]] = []
    for company in session.scalars(select(Company).order_by(Company.id)):
        have = {normalise_company(n) for n in (company.name_zh, company.name_en) if n}
        have.discard("")
        if wanted & have:
            return company, []
        best = max(
            (difflib.SequenceMatcher(None, w, h).ratio() for w in wanted for h in have),
            default=0.0,
        )
        if best >= NEAR_MATCH_THRESHOLD:
            near.append((best, company))
    near.sort(key=lambda pair: -pair[0])
    return None, [c for _, c in near]


def create_company_from_extraction(session: Session, extracted: ExtractedJob) -> Company:
    company = Company(
        name_zh=extracted.confirmed_value("company_name_zh"),
        name_en=extracted.confirmed_value("company_name_en"),
        city_zh=extracted.confirmed_value("city_zh"),
    )
    if company.name_zh is None and company.name_en is None:
        raise CaptureError(
            "the confirmed extraction has no company name; set company_name_zh or "
            "company_name_en during confirmation"
        )
    session.add(company)
    session.flush()
    return company
