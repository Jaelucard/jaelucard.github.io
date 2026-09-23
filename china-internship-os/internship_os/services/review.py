"""Browser review of an unconfirmed extraction: the web version of ``ios confirm``.

The form shows every extracted field with its current value. Submitting a field unchanged
confirms it, a new value overrides it, and an empty box sets it to null (``-`` in the CLI).
The fields that can make a job INELIGIBLE also need an explicit tick.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from internship_os.capture import (
    CaptureError,
    Override,
    _jsonable,
    create_company_from_extraction,
    find_company_matches,
    parse_override,
)
from internship_os.config import AppConfig
from internship_os.models import Company, Job
from internship_os.pipeline import ConfirmationResult, TransitionResult, finalize_confirmation, transition
from internship_os.schemas import ExtractedJob, JobStatus

# Inputs of eligibility's hard-fail codes (degree, cohort, nationality/work authorisation,
# role closed, deadline passed). Each needs its own tick on the review page.
ALWAYS_CONFIRM: tuple[str, ...] = (
    "degree_required",
    "graduation_cohort_text",
    "cohort_years",
    "cohort_unrestricted",
    "nationality_or_work_auth_restriction",
    "role_closed",
    "deadline",
)
LONG_TEXT_FIELDS = frozenset({"responsibilities_summary"})
DISCARD_NOTE = "discarded at review"


class ReviewInvalid(ValueError):
    """The submitted review cannot be saved. ``errors`` maps a field (or 'company'/'job') to a message."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


@dataclass
class ReviewField:
    name: str
    kind: str  # select | text | textarea | date | number
    value: str
    options: list[str] | None
    source_span: str | None
    must_confirm: bool
    ticked: bool = False
    error: str | None = None


def display(value: Any) -> str:
    """The text an input shows for ``value``; :func:`parse_form` reads it back unchanged."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        items = [display(v) for v in value]
        return json.dumps(items, ensure_ascii=False) if any("," in i for i in items) else ", ".join(items)
    if isinstance(value, date):
        return value.isoformat()
    return str(getattr(value, "value", value))


def _widget(name: str) -> tuple[str, list[str] | None]:
    inner = ExtractedJob.inner_type(name)
    if inner is bool:
        return "select", ["false", "true"]
    if isinstance(inner, type) and issubclass(inner, StrEnum):
        return "select", [m.value for m in inner]
    if inner is date:
        return "date", None
    if inner is int:
        return "number", None
    return ("textarea" if name in LONG_TEXT_FIELDS else "text"), None


def field_order() -> list[str]:
    return list(ALWAYS_CONFIRM) + [n for n in ExtractedJob.field_names() if n not in ALWAYS_CONFIRM]


def review_fields(
    extracted: ExtractedJob,
    form: Mapping[str, str] | None = None,
    errors: Mapping[str, str] | None = None,
) -> list[ReviewField]:
    """Fields in review order. ``form`` re-shows submitted values after a rejected submit."""
    form = form or {}
    errors = errors or {}
    fields: list[ReviewField] = []
    for name in field_order():
        fld = extracted.get(name)
        kind, options = _widget(name)
        key = f"field__{name}"
        fields.append(
            ReviewField(
                name=name,
                kind=kind,
                value=form[key] if key in form else display(fld.value),
                options=options,
                source_span=fld.source_span,
                must_confirm=name in ALWAYS_CONFIRM,
                ticked=bool(form.get(f"confirm__{name}")),
                error=errors.get(name),
            )
        )
    return fields


def parse_form(
    extracted: ExtractedJob, form: Mapping[str, str]
) -> tuple[ExtractedJob, list[Override], dict[str, str]]:
    """Read a submitted review. Returns (confirmed extraction, overrides, errors by field)."""
    errors: dict[str, str] = {}
    values: dict[str, Any] = {}
    for name in ExtractedJob.field_names():
        raw = form.get(f"field__{name}")
        if raw is None:
            errors[name] = "missing from the submitted form"
            continue
        raw = raw.strip()
        try:
            values[name] = None if raw == "" else parse_override(name, raw)
        except ValueError as exc:
            errors[name] = str(exc)
    for name in ALWAYS_CONFIRM:
        if name not in errors and not form.get(f"confirm__{name}"):
            errors[name] = "tick the box to confirm you checked this field"
    if errors:
        return extracted, [], errors

    draft = extracted.model_copy(deep=True)
    for name, value in values.items():
        draft.get(name).value = value
    # Re-validate so fields cleared to null pick up their sentinel again.
    confirmed = ExtractedJob.model_validate(draft.model_dump(mode="json"))
    overrides: list[Override] = []
    for name in ExtractedJob.field_names():
        old, fld = extracted.get(name), confirmed.get(name)
        if fld.value != old.value:
            overrides.append(Override(name, _jsonable(old.value), _jsonable(fld.value)))
            fld.source_span = None
        else:
            fld.source_span = old.source_span
        fld.confirmed = True
    return confirmed, overrides, errors


def company_matches(session: Session, extracted: ExtractedJob) -> tuple[Company | None, list[Company]]:
    return find_company_matches(session, extracted.company_name_zh.value, extracted.company_name_en.value)


def choose_company(session: Session, confirmed: ExtractedJob, choice: str | None) -> Company:
    """An explicitly chosen company id, else an exact match, else a new company.

    Near matches are never linked automatically: when they exist the user must pick one or 'new'.
    """
    choice = (choice or "").strip()
    if choice and choice != "new":
        company = session.get(Company, int(choice)) if choice.isdigit() else None
        if company is None:
            raise ReviewInvalid({"company": f"company {choice} does not exist"})
        return company
    exact, near = company_matches(session, confirmed)
    if exact is not None:
        return exact
    if near and choice != "new":
        raise ReviewInvalid({"company": "similar companies exist; choose one or create a new company"})
    try:
        return create_company_from_extraction(session, confirmed)
    except CaptureError as exc:
        raise ReviewInvalid({"company": str(exc)}) from None


def confirm_job(
    session: Session, job: Job, form: Mapping[str, str], config: AppConfig, today: date
) -> ConfirmationResult:
    """Validate the submitted review, link the company and run the same steps as ``ios confirm``."""
    if job.confirmed_at is not None:
        raise ReviewInvalid({"job": f"job {job.id} is already confirmed"})
    if not job.extracted:
        raise ReviewInvalid({"job": f"job {job.id} has no extraction to confirm"})
    extracted = ExtractedJob.model_validate(job.extracted)
    confirmed, overrides, errors = parse_form(extracted, form)
    if errors:
        raise ReviewInvalid(errors)
    if not (confirmed.company_name_zh.value or confirmed.company_name_en.value):
        raise ReviewInvalid({"company_name_zh": "enter the company name (Chinese or English)"})
    company = choose_company(session, confirmed, form.get("company_choice"))
    return finalize_confirmation(session, job, confirmed, company, overrides, config, today=today)


def discard_job(session: Session, job: Job, config: AppConfig, today: date) -> TransitionResult:
    """Close an unconfirmed capture. Jobs are never deleted."""
    if job.confirmed_at is not None:
        raise ReviewInvalid({"job": f"job {job.id} is already confirmed; change its status on the job page"})
    return transition(
        session, job, JobStatus.CLOSED.value, next_action=None, due=None, stage=None,
        note=DISCARD_NOTE, config=config, today=today,
    )
