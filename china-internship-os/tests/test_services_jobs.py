"""Job list filtering and the user-entered job updates used by the web UI."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from internship_os.models import Job
from internship_os.pipeline import transition
from internship_os.services import jobs as svc
from internship_os.tiering import sort_jobs


def test_list_jobs_filters_by_track_and_city(make_confirmed_job, session, config):
    hz = make_confirmed_job()
    sz = make_confirmed_job("suzhou_backend")
    assert [j.id for j in svc.list_jobs(session, config, track="SWE")] == [sz.id]
    assert [j.id for j in svc.list_jobs(session, config, city="杭州")] == [hz.id]
    assert [j.id for j in svc.list_jobs(session, config, city="Hangzhou")] == [hz.id]


def test_list_jobs_filters_by_tier_and_status(make_confirmed_job, session, config):
    hz = make_confirmed_job()
    assert [j.id for j in svc.list_jobs(session, config, tier=hz.tier, status=hz.status)] == [hz.id]
    assert svc.list_jobs(session, config, status="OFFER") == []


def test_list_jobs_blank_filters_return_all_sorted_like_cli(make_confirmed_job, session, config):
    make_confirmed_job()
    make_confirmed_job("suzhou_backend")
    everything = sort_jobs(list(session.scalars(select(Job))), config.user_facts)
    listed = svc.list_jobs(session, config, tier="", status="", track="", city="")
    assert [j.id for j in listed] == [j.id for j in everything]


def test_set_status_goes_through_the_programme_gate(make_confirmed_job, session, config, today):
    job = make_confirmed_job()  # host company YES status unknown, so a programme dimension is UNKNOWN
    result = svc.set_status(
        session, job, "READY_TO_APPLY", next_action="apply", due=today, note=None, config=config, today=today
    )
    assert result.refused
    assert job.status == "PROGRAMME_CHECK_REQUIRED"


def test_set_next_action_updates_text_and_date(make_confirmed_job, session, today):
    job = make_confirmed_job()
    svc.set_next_action(session, job, "email HR", today + timedelta(days=2))
    session.expire_all()
    stored = session.get(Job, job.id)
    assert stored.next_action == "email HR" and stored.next_action_date == today + timedelta(days=2)


def test_set_next_action_requires_text_and_date(make_confirmed_job, session, today):
    job = make_confirmed_job()
    with pytest.raises(ValueError):
        svc.set_next_action(session, job, "   ", today)
    with pytest.raises(ValueError):
        svc.set_next_action(session, job, "email HR", None)


def test_set_next_action_refused_on_terminal_job(make_confirmed_job, session, config, today):
    job = make_confirmed_job()
    transition(session, job, "CLOSED", next_action=None, due=None, stage=None, note=None, config=config, today=today)
    with pytest.raises(ValueError):
        svc.set_next_action(session, job, "email HR", today)


def test_add_contact_attaches_to_company_and_logs_note(make_confirmed_job, session):
    job = make_confirmed_job()
    contact = svc.add_contact(session, job, name="Li Wei", role="HR", channel="wechat", notes="wxid_liwei")
    assert contact.company_id == job.company_id and contact.channel == "wechat"
    event = job.events[-1]
    assert event.kind == "note" and event.contact_id == contact.id


def test_add_contact_requires_linked_company(make_confirmed_job, session):
    job = make_confirmed_job(company=False)
    with pytest.raises(ValueError):
        svc.add_contact(session, job, name="Li Wei", role=None, channel="wechat", notes=None)


def test_add_contact_rejects_unknown_channel(make_confirmed_job, session):
    job = make_confirmed_job()
    with pytest.raises(ValueError):
        svc.add_contact(session, job, name="Li Wei", role=None, channel="WeChat DM", notes=None)
