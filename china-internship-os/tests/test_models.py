from datetime import date

import pytest
from sqlalchemy import func, select

from internship_os.models import ActiveJobNeedsNextAction, Company, CompanyNeedsName, Job, JobEvent


def _active_job(**overrides):
    kwargs = dict(
        source_channel="shixiseng",
        title_zh="AI应用开发实习生",
        next_action="confirm extraction",
        next_action_date=date(2026, 9, 9),
    )
    kwargs.update(overrides)
    return Job(**kwargs)


def test_next_action_required_for_active_jobs(session):
    # Insert without a next action is refused, and the error names status and missing field.
    job = Job(source_channel="shixiseng", title_zh="后端开发实习生")
    session.add(job)
    with pytest.raises(ActiveJobNeedsNextAction) as excinfo:
        session.flush()
    assert excinfo.value.status == "DISCOVERED"
    assert excinfo.value.missing == "next_action"
    assert "DISCOVERED" in str(excinfo.value) and "next_action" in str(excinfo.value)
    session.rollback()

    # Missing date alone is also refused.
    job = Job(source_channel="shixiseng", title_zh="后端开发实习生", next_action="assess fit")
    session.add(job)
    with pytest.raises(ActiveJobNeedsNextAction) as excinfo:
        session.flush()
    assert excinfo.value.missing == "next_action_date"
    session.rollback()

    # Update path: clearing the next action on a stored active job is refused, naming the id.
    job = _active_job()
    session.add(job)
    session.commit()
    job_id = job.id
    job.next_action = None
    with pytest.raises(ActiveJobNeedsNextAction) as excinfo:
        session.commit()
    session.rollback()
    assert excinfo.value.job_id == job_id
    assert f"job id {job_id}" in str(excinfo.value)

    # Moving to another non-terminal state still requires both fields.
    job = session.get(Job, job_id)
    job.status = "SHORTLISTED"
    job.next_action_date = None
    with pytest.raises(ActiveJobNeedsNextAction):
        session.commit()
    session.rollback()


def test_terminal_job_does_not_require_next_action(session):
    for status in ("INELIGIBLE", "REJECTED", "WITHDRAWN", "CLOSED"):
        job = Job(source_channel="boss", title_en="Backend Intern", status=status)
        session.add(job)
        session.commit()
        assert job.id is not None
        assert job.next_action is None and job.next_action_date is None

    # A terminal transition clears the previous next action.
    job = _active_job()
    session.add(job)
    session.commit()
    job.status = "REJECTED"
    session.commit()
    session.expire_all()
    stored = session.get(Job, job.id)
    assert stored.status == "REJECTED"
    assert stored.next_action is None
    assert stored.next_action_date is None


def test_closed_job_is_retained(session):
    job = _active_job(raw_text="原始JD")
    session.add(job)
    session.commit()
    session.add(JobEvent(job_id=job.id, kind="captured", detail={"source": "shixiseng"}))
    session.commit()
    job_id = job.id

    job.status = "CLOSED"
    session.commit()
    session.expire_all()

    stored = session.get(Job, job_id)
    assert stored is not None
    assert stored.status == "CLOSED"
    assert stored.raw_text == "原始JD"
    assert session.scalar(select(func.count()).select_from(Job)) == 1
    assert [e.kind for e in stored.events] == ["captured"]


def test_job_defaults_are_not_run(session):
    job = _active_job()
    session.add(job)
    session.commit()
    session.expire_all()
    stored = session.get(Job, job.id)
    assert stored.status == "DISCOVERED"
    assert stored.eligibility == "NOT_RUN"
    assert stored.programme_overall == "NOT_RUN"
    assert stored.tier == "NOT_RUN"
    assert stored.fit == "unset"
    assert stored.quality == "unknown"
    assert stored.referral == "none"
    assert stored.track == "unknown"
    assert stored.confirmed_at is None
    assert set(stored.programme) == {
        "SUTD_APPROVAL",
        "YES_ELIGIBILITY",
        "HOST_COMPANY",
        "DURATION_AND_DATES",
        "IMMIGRATION",
    }
    assert all(d["status"] == "NOT_RUN" for d in stored.programme.values())
    assert stored.captured_at.tzinfo is not None


def test_vocabulary_columns_reject_unknown_values(session):
    with pytest.raises(ValueError, match="status"):
        Job(source_channel="boss", status="OPEN")
    with pytest.raises(ValueError, match="source_channel"):
        Job(source_channel="craigslist")
    with pytest.raises(ValueError, match="yes_status"):
        Company(name_en="Acme", yes_status="maybe")


def test_company_requires_a_name(session):
    session.add(Company(host_type="startup"))
    with pytest.raises(CompanyNeedsName):
        session.flush()
    session.rollback()

    company = Company(name_zh="某某科技")
    session.add(company)
    session.commit()
    assert company.host_type == "unknown"
    assert company.yes_status == "unknown"
