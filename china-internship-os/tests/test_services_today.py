"""Today page data: the CLI digest's computations, returned as data instead of lines."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from internship_os.digest import build_digest, recommended_today
from internship_os.models import Job
from internship_os.programme import constraint_warnings, global_dimensions
from internship_os.services.today import summary
from internship_os.tiering import TIER_ORDER


def test_top_line_matches_digest(session, config, today):
    s = summary(session, config, today)
    assert s.top_line == build_digest(session, config, today)[0]
    assert s.top_line.startswith("CONTRACT MUST BE SIGNED BY")


def test_unconfirmed_capture_needs_review(capture_fixture, session, config, today):
    job = capture_fixture("hangzhou_ai_app")
    assert [j.id for j in summary(session, config, today).needs_review] == [job.id]


def test_confirmed_job_does_not_need_review(make_confirmed_job, session, config, today):
    make_confirmed_job()
    assert summary(session, config, today).needs_review == []


def test_actions_split_into_due_and_upcoming(make_confirmed_job, session, config, today):
    due = make_confirmed_job()
    later = make_confirmed_job("suzhou_backend")
    later.next_action_date = today + timedelta(days=3)
    session.commit()
    s = summary(session, config, today)
    assert [j.id for j in s.due] == [due.id]
    assert [j.id for j in s.upcoming] == [later.id]


def test_deadlines_within_seven_days(make_confirmed_job, session, config, today):
    soon = make_confirmed_job(deadline=(today + timedelta(days=5)).isoformat())
    make_confirmed_job("suzhou_backend", deadline=(today + timedelta(days=30)).isoformat())
    assert [j.id for j in summary(session, config, today).deadlines_soon] == [soon.id]


def test_counts_by_tier_status_and_programme(make_confirmed_job, session, config, today):
    job = make_confirmed_job()
    s = summary(session, config, today)
    assert [tier for tier, _ in s.by_tier] == list(TIER_ORDER)
    assert dict(s.by_tier)[job.tier] == 1
    assert dict(s.by_status) == {job.status: 1}
    assert dict(s.by_programme) == {job.programme_overall: 1}


def test_recommended_matches_digest(make_confirmed_job, session, config, today):
    make_confirmed_job()
    make_confirmed_job("suzhou_backend")
    jobs = list(session.scalars(select(Job).order_by(Job.id)))
    expected = [j.id for j in recommended_today(jobs, config)]
    assert [j.id for j in summary(session, config, today).recommended] == expected


def test_programme_facts_included(session, config, today):
    s = summary(session, config, today)
    assert s.constraint_warnings == constraint_warnings(config.constraints, today)
    assert s.global_dimensions == global_dimensions(config.constraints, config.user_facts, today)
