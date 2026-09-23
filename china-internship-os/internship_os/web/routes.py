"""Page routes. Routes read the request, call a service or core function, and render or redirect.

Every POST answers with a 303 redirect to a GET page, except a rejected form, which is shown
again with status 400 and the submitted values so no typing is lost.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.responses import Response

from internship_os.config import AppConfig
from internship_os.models import Job
from internship_os.programme import constraint_warnings, global_dimensions
from internship_os.schemas import ExtractedJob, JobStatus, Tier, Track
from internship_os.services import jobs as job_service
from internship_os.services.today import summary
from internship_os.timeline import build_timeline, render as render_timeline
from internship_os.web import deps
from internship_os.web.render import page

router = APIRouter()


def get_job(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
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


@router.get("/jobs/{job_id}")
def job_page(
    request: Request,
    job_id: int,
    session: Session = Depends(deps.get_db),
) -> Response:
    job = get_job(session, job_id)
    extraction = ExtractedJob.model_validate(job.extracted) if job.extracted else None
    return page(
        request, "job.html", cli=f"ios job show {job.id}",
        job=job,
        extraction=extraction,
        field_names=ExtractedJob.field_names(),
        contacts=list(job.company.contacts) if job.company else [],
    )


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
