"""Page routes. Routes read the request, call a service or core function, and render or redirect.

Every POST answers with a 303 redirect to a GET page, except a rejected form (400) or a possible
duplicate awaiting a decision (409), which are shown again with the submitted values.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse, Response

from internship_os.capture import (
    CaptureError,
    DuplicateCaptureNeedsDecision,
    attach_to_existing,
    capture as capture_posting,
)
from internship_os import jev
from internship_os.config import AppConfig
from internship_os.llm import LLMError
from internship_os.models import Job
from internship_os.pipeline import TransitionError, add_note
from internship_os.programme import constraint_warnings, global_dimensions
from internship_os.schemas import ContactChannel, ExtractedJob, JobStatus, ProgrammeStatus, SourceChannel, Tier, Track
from internship_os.services import jobs as job_service
from internship_os.services import review as review_service
from internship_os.services.today import summary
from internship_os.timeline import build_timeline, render as render_timeline
from internship_os.web import deps
from internship_os.web.render import page

router = APIRouter()

SOURCES = [s.value for s in SourceChannel]
CAPTURE_CLI = "ios capture --paste --source <channel>"
MESSAGES = {
    "confirmed": ("ok", "Confirmed. Eligibility, programme and tier are updated."),
    "checklist_failed": ("warn", "Confirmed. The quality checklist could not be generated; set quality by hand if needed."),
    "discarded": ("note", "Capture discarded; the job is CLOSED."),
    "attached": ("ok", "The duplicate capture was attached to this job as a note."),
    "status": ("ok", "Status changed."),
    "next": ("ok", "Next action updated."),
    "note": ("ok", "Note added."),
    "contact": ("ok", "Contact added to the company."),
}


def see_other(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def job_message(job: Job, msg: str) -> tuple[str, str] | None:
    """The one-line result shown after a redirect back to the job page."""
    if msg == "refused":
        reason = next(
            (e.detail.get("refused_reason") for e in reversed(job.events)
             if e.kind == "status_change" and isinstance(e.detail, dict) and e.detail.get("refused_reason")),
            None,
        )
        return "bad", f"READY_TO_APPLY was refused; the job is {job.status}. {reason or ''}".strip()
    if msg == "at_risk":
        at_risk = [n for n, d in (job.programme or {}).items() if d["status"] == ProgrammeStatus.AT_RISK]
        return "warn", f"Status changed, with a programme AT_RISK warning on {', '.join(at_risk)}."
    return MESSAGES.get(msg)


MAX_ID = 2**63 - 1  # SQLite INTEGER


def get_job(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id) if 0 < job_id <= MAX_ID else None
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} does not exist")
    return job


def city_options(config: AppConfig, jobs: list[Job]) -> list[str]:
    configured = [c.zh for group in (config.cities.primary, config.cities.secondary, config.cities.expanded) for c in group]
    extra = sorted({j.city_zh for j in jobs if j.city_zh} - set(configured))
    return configured + extra


# --------------------------------------------------------------------------------------
# Read pages
# --------------------------------------------------------------------------------------


@router.get("/")
def today_page(
    request: Request,
    session: Session = Depends(deps.get_db),
    config: AppConfig = Depends(deps.get_config),
    today: date = Depends(deps.today),
) -> Response:
    return page(request, "today.html", cli="ios digest", s=summary(session, config, today), today=today)


@router.get("/jobs")
def jobs_page(
    request: Request,
    tier: str = "",
    status: str = "",
    track: str = "",
    city: str = "",
    session: Session = Depends(deps.get_db),
    config: AppConfig = Depends(deps.get_config),
) -> Response:
    filters = {"tier": tier, "status": status, "track": track, "city": city}
    jobs = job_service.list_jobs(session, config, **filters)
    options = {
        "tier": [t.value for t in Tier],
        "status": [s.value for s in JobStatus],
        "track": [t.value for t in Track],
        "city": city_options(config, job_service.list_jobs(session, config)),
    }
    return page(request, "jobs.html", cli="ios job list", jobs=jobs, filters=filters, options=options)


def job_view(request: Request, job: Job, *, message: tuple[str, str] | None = None,
             form: dict[str, str] | None = None, status_code: int = 200) -> Response:
    """``form`` re-shows a rejected action's typed values; keys are '<form>.<field>'."""
    extraction = ExtractedJob.model_validate(job.extracted) if job.extracted else None
    return page(
        request, "job.html", cli=f"ios job show {job.id}", status_code=status_code,
        job=job,
        message=message,
        form=form or {},
        extraction=extraction,
        field_names=ExtractedJob.field_names(),
        contacts=list(job.company.contacts) if job.company else [],
        statuses=[s.value for s in JobStatus],
        channels=[c.value for c in ContactChannel],
    )


@router.get("/jobs/{job_id}")
def job_page(
    request: Request,
    job_id: int,
    msg: str = "",
    session: Session = Depends(deps.get_db),
) -> Response:
    job = get_job(session, job_id)
    return job_view(request, job, message=job_message(job, msg))


@router.get("/facts")
def facts_page(
    request: Request,
    config: AppConfig = Depends(deps.get_config),
    today: date = Depends(deps.today),
) -> Response:
    steps = build_timeline(config.user_facts, config.constraints, None, today)
    return page(
        request, "facts.html", cli="ios constraints; ios timeline",
        constraints=list(config.constraints),
        warnings=constraint_warnings(config.constraints, today),
        dimensions=global_dimensions(config.constraints, config.user_facts, today),
        timeline=render_timeline(steps, today),
        today=today,
    )


# --------------------------------------------------------------------------------------
# Capture
# --------------------------------------------------------------------------------------


def capture_again(request: Request, form: dict[str, str], *, status_code: int, error: str | None = None,
                  duplicate: dict | None = None) -> Response:
    return page(request, "capture.html", cli=CAPTURE_CLI, status_code=status_code,
                form=form, sources=SOURCES, error=error, duplicate=duplicate)


@router.get("/capture")
def capture_page(request: Request) -> Response:
    return page(request, "capture.html", cli=CAPTURE_CLI, form={}, sources=SOURCES, error=None, duplicate=None)


@router.post("/capture")
def capture_create(
    request: Request,
    text: str = Form(""),
    source: str = Form(""),
    url: str = Form(""),
    action: str = Form(""),
    attach_to: str = Form(""),
    extracted_json: str = Form(""),
    session: Session = Depends(deps.get_db),
    config: AppConfig = Depends(deps.get_config),
    today: date = Depends(deps.today),
) -> Response:
    """Pasted text only: the URL box is stored for duplicate matching and never fetched here."""
    form = {"text": text, "source": source, "url": url}
    source_url = url.strip() or None
    if not text.strip():
        return capture_again(request, form, status_code=400, error="Paste the job description text.")
    if source not in SOURCES:
        return capture_again(request, form, status_code=400, error="Choose where the posting came from.")
    try:
        if action == "attach":
            if not (attach_to.isascii() and attach_to.isdigit() and len(attach_to) <= 18):
                return capture_again(request, form, status_code=400, error="Choose one of the listed jobs to attach to.")
            target = int(attach_to)
            attach_to_existing(session, target, text=text.strip(), url=source_url, source_channel=source)
            return see_other(f"/jobs/{target}?msg=attached")
        if action == "new":
            job = capture_posting(
                text, source_url, source, session=session, config=config, today=today,
                extracted=ExtractedJob.model_validate_json(extracted_json), force_new=True,
            )
        else:
            job = capture_posting(text, source_url, source, session=session, config=config, today=today)
    except DuplicateCaptureNeedsDecision as dup:
        candidates = [j for j in (session.get(Job, i) for i in dup.candidate_ids) if j is not None]
        return capture_again(request, form, status_code=409, duplicate={
            "candidates": candidates, "extracted_json": dup.extracted.model_dump_json(),
        })
    except LLMError as exc:
        return capture_again(request, form, status_code=400, error=f"Extraction failed: {exc}")
    except (CaptureError, ValueError) as exc:
        return capture_again(request, form, status_code=400, error=str(exc))
    jev.record_suggestions(session, job, config)  # never raises; the review page shows the result
    return see_other(f"/jobs/{job.id}/review")


# --------------------------------------------------------------------------------------
# Review and confirm (the web version of `ios confirm`)
# --------------------------------------------------------------------------------------


def review_view(request: Request, session: Session, job: Job, config: AppConfig, *, form: dict[str, str] | None = None,
                errors: dict[str, str] | None = None, status_code: int = 200) -> Response:
    extracted = ExtractedJob.model_validate(job.extracted)
    exact, near = review_service.company_matches(session, extracted, form)
    view, notes = jev.review_notes(job, extracted, config)
    return page(
        request, "review.html", cli=f"ios confirm {job.id}", status_code=status_code,
        job=job,
        jev_view=view,
        jev_status=jev.status(config),
        notes=notes,
        fields=review_service.review_fields(extracted, form, errors),
        exact=exact,
        near=near,
        company_choice=(form or {}).get("company_choice", ""),
        errors=errors or {},
    )


@router.get("/jobs/{job_id}/review")
def review_page(
    request: Request,
    job_id: int,
    session: Session = Depends(deps.get_db),
    config: AppConfig = Depends(deps.get_config),
) -> Response:
    job = get_job(session, job_id)
    if job.confirmed_at is not None or job.is_terminal:
        return see_other(f"/jobs/{job.id}")
    if not job.extracted:
        raise HTTPException(status_code=404, detail=f"job {job.id} has no extraction to review")
    return review_view(request, session, job, config)


@router.post("/jobs/{job_id}/review")
async def review_confirm(
    request: Request,
    job_id: int,
    session: Session = Depends(deps.get_db),
    config: AppConfig = Depends(deps.get_config),
    today: date = Depends(deps.today),
) -> Response:
    form = {key: value for key, value in (await request.form()).items() if isinstance(value, str)}
    job = await run_in_threadpool(get_job, session, job_id)
    if job.confirmed_at is not None or job.is_terminal:
        return see_other(f"/jobs/{job.id}")
    if not job.extracted:
        raise HTTPException(status_code=404, detail=f"job {job.id} has no extraction to review")
    try:
        # The confirmation may call the LLM for the quality checklist, so keep it off the event loop.
        result = await run_in_threadpool(review_service.confirm_job, session, job, form, config, today)
    except review_service.ReviewInvalid as exc:
        return await run_in_threadpool(review_view, request, session, job, config, form=form, errors=exc.errors, status_code=400)
    return see_other(f"/jobs/{job.id}?msg={'checklist_failed' if result.checklist_error else 'confirmed'}")


@router.post("/jobs/{job_id}/discard")
def review_discard(
    job_id: int,
    session: Session = Depends(deps.get_db),
    config: AppConfig = Depends(deps.get_config),
    today: date = Depends(deps.today),
) -> Response:
    job = get_job(session, job_id)
    try:
        review_service.discard_job(session, job, config, today)
    except review_service.ReviewInvalid:
        return see_other(f"/jobs/{job.id}")
    return see_other(f"/jobs/{job.id}?msg=discarded")


# --------------------------------------------------------------------------------------
# Job actions: user-entered facts, written directly
# --------------------------------------------------------------------------------------


def parse_due(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"the date must be YYYY-MM-DD, got {raw!r}") from None


@router.post("/jobs/{job_id}/status")
def job_status_change(
    request: Request,
    job_id: int,
    status: str = Form(""),
    next_action: str = Form(""),
    due: str = Form(""),
    note: str = Form(""),
    session: Session = Depends(deps.get_db),
    config: AppConfig = Depends(deps.get_config),
    today: date = Depends(deps.today),
) -> Response:
    """Same path as ``ios job status``: READY_TO_APPLY is gated on the programme dimensions."""
    job = get_job(session, job_id)
    try:
        result = job_service.set_status(
            session, job, status,
            next_action=next_action.strip() or None, due=parse_due(due), note=note.strip() or None,
            config=config, today=today,
        )
    except (TransitionError, ValueError) as exc:
        text = str(exc).replace("--next and --due", "a next action and a due date").replace("--note", "a note")
        typed = {"status.status": status, "status.next_action": next_action, "status.due": due, "status.note": note}
        return job_view(request, job, message=("bad", text), form=typed, status_code=400)
    if result.refused:
        return see_other(f"/jobs/{job.id}?msg=refused")
    return see_other(f"/jobs/{job.id}?msg={'at_risk' if result.warnings else 'status'}")


@router.post("/jobs/{job_id}/next")
def job_next_action(
    request: Request,
    job_id: int,
    text: str = Form(""),
    due: str = Form(""),
    session: Session = Depends(deps.get_db),
) -> Response:
    job = get_job(session, job_id)
    try:
        job_service.set_next_action(session, job, text, parse_due(due))
    except ValueError as exc:
        typed = {"next.text": text, "next.due": due}
        return job_view(request, job, message=("bad", str(exc)), form=typed, status_code=400)
    return see_other(f"/jobs/{job.id}?msg=next")


@router.post("/jobs/{job_id}/note")
def job_note(
    request: Request,
    job_id: int,
    text: str = Form(""),
    session: Session = Depends(deps.get_db),
) -> Response:
    job = get_job(session, job_id)
    if not text.strip():
        return job_view(request, job, message=("bad", "The note is empty."), status_code=400)
    add_note(session, job, text.strip())
    return see_other(f"/jobs/{job.id}?msg=note")


@router.post("/jobs/{job_id}/contact")
def job_contact(
    request: Request,
    job_id: int,
    name: str = Form(""),
    role: str = Form(""),
    channel: str = Form(""),
    notes: str = Form(""),
    session: Session = Depends(deps.get_db),
) -> Response:
    job = get_job(session, job_id)
    try:
        job_service.add_contact(session, job, name=name, role=role, channel=channel, notes=notes)
    except ValueError as exc:
        typed = {"contact.name": name, "contact.role": role, "contact.channel": channel, "contact.notes": notes}
        return job_view(request, job, message=("bad", str(exc)), form=typed, status_code=400)
    return see_other(f"/jobs/{job.id}?msg=contact")
