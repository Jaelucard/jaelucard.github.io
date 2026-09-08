"""Orchestration of deterministic steps around a job: confirmation finalisation, recompute,
status transitions and the READY_TO_APPLY programme gate.

Nothing here calls an LLM except :func:`finalize_confirmation`, which attempts the optional
quality checklist and reports (never raises) its failure. :func:`recompute_job` never calls an
LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from internship_os.capture import (
    POST_CONFIRM_NEXT_ACTION,
    Override,
    refresh_display_fields,
)
from internship_os.config import AppConfig
from internship_os.models import Company, Job, JobEvent, utcnow
from internship_os.schemas import EventKind, ExtractedJob, JobStatus


@dataclass
class ConfirmationResult:
    job: Job
    company: Company
    checklist_error: str | None = None
    notes: list[str] = field(default_factory=list)


def finalize_confirmation(
    session: Session,
    job: Job,
    confirmed: ExtractedJob,
    company: Company,
    overrides: list[Override],
    config: AppConfig,
    today: date | None = None,
) -> ConfirmationResult:
    """Persist a fully confirmed extraction and run the post-confirmation steps."""
    if not confirmed.all_confirmed:
        raise ValueError("finalize_confirmation requires every field to be confirmed")
    when = today or date.today()
    job.extracted = confirmed.model_dump(mode="json")
    job.confirmed_at = utcnow()
    refresh_display_fields(job, confirmed)
    job.company = company
    if company.city_zh is None and job.city_zh:
        company.city_zh = job.city_zh
    job.status = JobStatus.DISCOVERED.value
    job.next_action = POST_CONFIRM_NEXT_ACTION
    job.next_action_date = when
    session.add(
        JobEvent(
            job_id=job.id,
            kind=EventKind.confirmed.value,
            detail={
                "company_id": company.id,
                "overrides": [o.__dict__ for o in overrides],
            },
        )
    )
    session.commit()
    return ConfirmationResult(job=job, company=company)
