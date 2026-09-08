"""Orchestration of the deterministic steps around a job: confirmation finalisation,
recompute, manual field updates and status transitions with the READY_TO_APPLY gate.

Only :func:`finalize_confirmation` touches an LLM, for the optional quality checklist, and it
reports rather than raises when that fails. :func:`recompute_job` never calls an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from internship_os import llm
from internship_os.capture import POST_CONFIRM_NEXT_ACTION, Override, refresh_display_fields
from internship_os.config import AppConfig
from internship_os.eligibility import run_eligibility
from internship_os.models import Company, Job, JobEvent, utcnow
from internship_os.programme import run_programme
from internship_os.schemas import (
    NON_TERMINAL_STATUSES,
    Eligibility,
    EventKind,
    ExtractedJob,
    Fit,
    HostType,
    JobStatus,
    ProgrammeStatus,
    Quality,
    QualityChecklist,
    Tier,
    YesStatus,
    is_terminal,
)
from internship_os.tiering import run_tiering


# --------------------------------------------------------------------------------------
# Deterministic checks
# --------------------------------------------------------------------------------------


def run_checks(job: Job, config: AppConfig, today: date | None = None) -> None:
    """Eligibility, programme and tiering over confirmed data. Sets job columns; no commit."""
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    job.eligibility = status
    job.eligibility_reasons = [r.as_dict() for r in reasons]
    run_programme_and_tier(job, config, today)


def run_programme_and_tier(job: Job, config: AppConfig, today: date | None = None) -> None:
    dimensions, overall = run_programme(job, job.company, config.constraints, config.user_facts, today)
    job.programme = dimensions
    job.programme_overall = overall
    job.tier = run_tiering(job, config)


def recompute_job(job: Job, config: AppConfig, today: date | None = None) -> None:
    """Rerun eligibility, programme and tiering. Never calls an LLM. Manual fields survive."""
    run_checks(job, config, today)


def snapshot(job: Job) -> dict[str, Any]:
    return {
        "eligibility": job.eligibility,
        "programme_overall": job.programme_overall,
        "tier": job.tier,
    }


def recompute_all(
    session: Session, config: AppConfig, today: date | None = None
) -> list[tuple[Job, dict[str, Any], dict[str, Any]]]:
    """Recompute every non-terminal confirmed job. Returns (job, before, after) triples."""
    changes = []
    for job in session.scalars(select(Job).order_by(Job.id)):
        if job.status not in NON_TERMINAL_STATUSES or job.confirmed_at is None:
            continue
        before = snapshot(job)
        recompute_job(job, config, today)
        changes.append((job, before, snapshot(job)))
    session.commit()
    return changes


# --------------------------------------------------------------------------------------
# Confirmation
# --------------------------------------------------------------------------------------


@dataclass
class ConfirmationResult:
    job: Job
    company: Company
    checklist_error: str | None = None
    notes: list[str] = field(default_factory=list)


def apply_eligibility_effect(job: Job, today: date) -> None:
    """Pipeline effect of a freshly confirmed eligibility result."""
    if job.eligibility == Eligibility.INELIGIBLE:
        extracted = ExtractedJob.model_validate(job.extracted)
        role_closed = extracted.role_closed.confirmed and extracted.role_closed.value is True
        job.status = JobStatus.CLOSED.value if role_closed else JobStatus.INELIGIBLE.value
        job.next_action = None
        job.next_action_date = None
        job.tier = Tier.HOLD.value
        return
    job.status = JobStatus.DISCOVERED.value
    job.next_action = POST_CONFIRM_NEXT_ACTION
    job.next_action_date = today


def attempt_quality_checklist(job: Job, config: AppConfig) -> str | None:
    """Ask the LLM to tick quality signals. Returns an error message instead of raising."""
    try:
        extracted = ExtractedJob.model_validate(job.extracted)
        result = llm.complete(
            "quality_checklist",
            {
                "responsibilities": extracted.confirmed_value("responsibilities_summary") or "",
                "required_skills": extracted.confirmed_value("required_skills") or [],
                "title": job.display_title,
            },
            QualityChecklist,
            config=config,
        )
        assert isinstance(result, QualityChecklist)
        job.quality_checklist = [s.model_dump() for s in result.signals]
        return None
    except Exception as exc:  # noqa: BLE001 - checklist failure must not undo confirmation
        job.quality_checklist = []
        return f"{type(exc).__name__}: {exc}"


def finalize_confirmation(
    session: Session,
    job: Job,
    confirmed: ExtractedJob,
    company: Company,
    overrides: list[Override],
    config: AppConfig,
    today: date | None = None,
) -> ConfirmationResult:
    """Persist a fully confirmed extraction and run the post-confirmation steps in order."""
    if not confirmed.all_confirmed:
        raise ValueError("finalize_confirmation requires every field to be confirmed")
    when = today or date.today()
    job.extracted = confirmed.model_dump(mode="json")
    job.confirmed_at = utcnow()
    refresh_display_fields(job, confirmed)
    job.company = company
    if company.city_zh is None and job.city_zh:
        company.city_zh = job.city_zh
    session.flush()

    run_checks(job, config, when)
    apply_eligibility_effect(job, when)
    checklist_error = attempt_quality_checklist(job, config)
    job.quality = Quality.unknown.value if job.quality is None else job.quality

    session.add(
        JobEvent(
            job_id=job.id,
            kind=EventKind.confirmed.value,
            detail={
                "company_id": company.id,
                "overrides": [o.__dict__ for o in overrides],
                "eligibility": job.eligibility,
                "programme_overall": job.programme_overall,
                "tier": job.tier,
                "status": job.status,
            },
        )
    )
    session.commit()
    notes = [f"{name}: {d['status']}" for name, d in job.programme.items()]
    return ConfirmationResult(job=job, company=company, checklist_error=checklist_error, notes=notes)


# --------------------------------------------------------------------------------------
# Status transitions
# --------------------------------------------------------------------------------------


@dataclass
class TransitionResult:
    job: Job
    previous: str
    requested: str
    final: str
    warnings: list[str] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        return self.final != self.requested


class TransitionError(ValueError):
    """The requested transition is invalid as specified."""


def transition(
    session: Session,
    job: Job,
    target: str,
    *,
    next_action: str | None,
    due: date | None,
    stage: str | None,
    note: str | None,
    config: AppConfig,
    today: date | None = None,
) -> TransitionResult:
    when = today or date.today()
    try:
        requested = JobStatus(target).value
    except ValueError:
        raise TransitionError(
            f"unknown status {target!r}; allowed: {', '.join(s.value for s in JobStatus)}"
        ) from None
    if not is_terminal(requested) and (not next_action or due is None):
        raise TransitionError(f"moving to {requested} requires --next and --due")
    if requested == JobStatus.INELIGIBLE and not note:
        raise TransitionError("moving to INELIGIBLE manually requires --note")

    previous = job.status
    final = requested
    warnings: list[str] = []
    gate_reason: str | None = None

    if requested == JobStatus.READY_TO_APPLY:
        run_programme_and_tier(job, config, when)
        # Gate per dimension: an UNKNOWN or INCOMPATIBLE dimension refuses the transition even
        # when another dimension is AT_RISK (which ranks worse in programme_overall).
        blocking = [
            name
            for name, d in job.programme.items()
            if d["status"] in (ProgrammeStatus.UNKNOWN, ProgrammeStatus.INCOMPATIBLE)
        ]
        at_risk = [name for name, d in job.programme.items() if d["status"] == ProgrammeStatus.AT_RISK]
        if blocking:
            final = JobStatus.PROGRAMME_CHECK_REQUIRED.value
            gate_reason = f"programme_overall is {job.programme_overall}: " + ", ".join(
                f"{name} {job.programme[name]['status']}" for name in blocking
            )
            next_action = f"resolve programme check: {', '.join(blocking)}"
            due = when
        elif at_risk:
            warnings.append(f"programme AT_RISK on {', '.join(at_risk)}; proceeding with a warning")

    job.status = final
    if is_terminal(final):
        job.next_action = None
        job.next_action_date = None
    else:
        job.next_action = next_action
        job.next_action_date = due
    session.add(
        JobEvent(
            job_id=job.id,
            kind=EventKind.status_change.value,
            detail={
                "from": previous,
                "to": final,
                "requested": requested,
                "refused_reason": gate_reason,
                "stage": stage,
                "note": note,
            },
        )
    )
    if is_terminal(final):
        session.add(JobEvent(job_id=job.id, kind=EventKind.closed.value, detail={"status": final}))
    session.commit()
    return TransitionResult(job=job, previous=previous, requested=requested, final=final, warnings=warnings)


# --------------------------------------------------------------------------------------
# Manual updates that must survive recompute
# --------------------------------------------------------------------------------------


def _programme_update(session: Session, job: Job, detail: dict[str, Any], config: AppConfig, today: date) -> None:
    run_programme_and_tier(job, config, today)
    detail = {**detail, "programme_overall": job.programme_overall, "tier": job.tier}
    session.add(JobEvent(job_id=job.id, kind=EventKind.programme_update.value, detail=detail))
    session.commit()


def approve_sutd(session: Session, job: Job, config: AppConfig, today: date | None = None) -> None:
    when = today or date.today()
    job.sutd_approved_at = utcnow()
    _programme_update(session, job, {"sutd_approved_at": job.sutd_approved_at.isoformat()}, config, when)


def set_agreed_dates(
    session: Session, job: Job, start: date, months: int, config: AppConfig, today: date | None = None
) -> None:
    """Employer-agreed values. Never touches the JD-extracted start_date."""
    when = today or date.today()
    job.agreed_start_date = start
    job.agreed_duration_months = months
    _programme_update(
        session,
        job,
        {"agreed_start_date": start.isoformat(), "agreed_duration_months": months},
        config,
        when,
    )


def set_fit(session: Session, job: Job, value: str, config: AppConfig) -> tuple[str, str]:
    fit = Fit(value)
    if fit == Fit.unset:
        raise ValueError("fit must be strong, ok or weak")
    old_tier = job.tier
    job.fit = fit.value
    job.tier = run_tiering(job, config)
    session.commit()
    return old_tier, job.tier


def set_quality(session: Session, job: Job, value: str, config: AppConfig) -> tuple[str, str]:
    quality = Quality(value)
    old_tier = job.tier
    job.quality = quality.value
    job.tier = run_tiering(job, config)
    session.commit()
    return old_tier, job.tier


def add_note(session: Session, job: Job, text: str) -> JobEvent:
    event = JobEvent(job_id=job.id, kind=EventKind.note.value, detail={"note": text})
    session.add(event)
    session.commit()
    return event


def update_company(
    session: Session,
    company: Company,
    *,
    host_type: str | None = None,
    yes_status: str | None = None,
    note: str | None = None,
) -> list[tuple[str, Any, Any]]:
    """Update manual company fields. Returns (field, old, new) triples."""
    changes: list[tuple[str, Any, Any]] = []
    if host_type is not None:
        value = HostType(host_type).value
        changes.append(("host_type", company.host_type, value))
        company.host_type = value
    if yes_status is not None:
        value = YesStatus(yes_status).value
        changes.append(("yes_status", company.yes_status, value))
        company.yes_status = value
    if note is not None:
        old = company.notes
        company.notes = f"{old}\n{note}" if old else note
        changes.append(("notes", old, company.notes))
    session.commit()
    return changes
