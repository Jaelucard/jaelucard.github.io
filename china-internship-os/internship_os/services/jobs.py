"""Job list filtering and the user-entered job updates behind the Job page."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from internship_os.config import AppConfig
from internship_os.models import Contact, Job, JobEvent
from internship_os.pipeline import TransitionResult, transition
from internship_os.schemas import ContactChannel, EventKind, is_terminal, normalise_city
from internship_os.tiering import sort_jobs


def list_jobs(
    session: Session,
    config: AppConfig,
    *,
    tier: str | None = None,
    status: str | None = None,
    track: str | None = None,
    city: str | None = None,
) -> list[Job]:
    """Jobs matching every non-blank filter, sorted like ``ios job list``."""
    jobs = list(session.scalars(select(Job)))
    if tier:
        jobs = [j for j in jobs if j.tier == tier]
    if status:
        jobs = [j for j in jobs if j.status == status]
    if track:
        jobs = [j for j in jobs if j.track == track]
    if city:
        wanted = config.cities.find(city)
        jobs = [
            j for j in jobs
            if (wanted is not None and wanted.matches(j.city_zh)) or normalise_city(j.city_zh) == normalise_city(city)
        ]
    return sort_jobs(jobs, config.user_facts)


def set_status(
    session: Session,
    job: Job,
    target: str,
    *,
    next_action: str | None,
    due: date | None,
    note: str | None,
    config: AppConfig,
    today: date,
) -> TransitionResult:
    """Same path as ``ios job status``, including the READY_TO_APPLY programme gate."""
    return transition(
        session, job, target, next_action=next_action, due=due, stage=None, note=note, config=config, today=today
    )


def set_next_action(session: Session, job: Job, text: str, due: date | None) -> None:
    if is_terminal(job.status):
        raise ValueError(f"job {job.id} is {job.status}; reopen it with a status change first")
    if not text or not text.strip():
        raise ValueError("next action text is required")
    if due is None:
        raise ValueError("next action date is required")
    job.next_action = text.strip()
    job.next_action_date = due
    session.commit()


def add_contact(
    session: Session, job: Job, *, name: str, role: str | None, channel: str, notes: str | None
) -> Contact:
    """A contact belongs to the job's company (as in ``ios contact add``); a note on the job links it."""
    if job.company is None:
        raise ValueError(f"job {job.id} has no company yet; confirm the job first")
    if not name or not name.strip():
        raise ValueError("contact name is required")
    contact = Contact(
        company_id=job.company.id,
        name=name.strip(),
        role=(role or "").strip() or None,
        channel=ContactChannel(channel).value,
        notes=(notes or "").strip() or None,
    )
    session.add(contact)
    session.flush()
    session.add(
        JobEvent(job_id=job.id, kind=EventKind.note.value, detail={"note": f"contact added: {contact.name}"}, contact_id=contact.id)
    )
    session.commit()
    return contact
