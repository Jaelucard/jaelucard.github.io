"""Job page actions: status (through the programme gate), next action, note, contact."""

from __future__ import annotations

from datetime import timedelta

from internship_os.models import Contact, Job


def _job(session, job_id: int) -> Job:
    session.expire_all()
    return session.get(Job, job_id)


def test_status_change_redirects_303_and_records_the_event(make_confirmed_job, client, session, today):
    job = make_confirmed_job()
    due = today + timedelta(days=1)
    response = client.post(
        f"/jobs/{job.id}/status",
        data={"status": "SHORTLISTED", "next_action": "tailor CV", "due": due.isoformat(), "note": ""},
    )
    assert response.status_code == 303 and response.headers["location"] == f"/jobs/{job.id}?msg=status"
    stored = _job(session, job.id)
    assert stored.status == "SHORTLISTED" and stored.next_action == "tailor CV" and stored.next_action_date == due
    assert stored.events[-1].kind == "status_change"


def test_ready_to_apply_refused_by_the_programme_gate_is_explained(make_confirmed_job, client, session, today):
    job = make_confirmed_job()  # company YES status unknown, so HOST_COMPANY is UNKNOWN
    response = client.post(
        f"/jobs/{job.id}/status",
        data={"status": "READY_TO_APPLY", "next_action": "apply", "due": today.isoformat(), "note": ""},
    )
    assert response.headers["location"] == f"/jobs/{job.id}?msg=refused"
    assert _job(session, job.id).status == "PROGRAMME_CHECK_REQUIRED"
    body = client.get(response.headers["location"]).text
    assert "READY_TO_APPLY was refused" in body and "HOST_COMPANY" in body


def test_status_change_without_next_action_returns_400(make_confirmed_job, client, session):
    job = make_confirmed_job()
    response = client.post(f"/jobs/{job.id}/status", data={"status": "SHORTLISTED", "next_action": "", "due": "", "note": ""})
    assert response.status_code == 400 and "requires a next action and a due date" in response.text
    assert _job(session, job.id).status == "DISCOVERED"


def test_unknown_status_returns_400(make_confirmed_job, client):
    job = make_confirmed_job()
    response = client.post(f"/jobs/{job.id}/status", data={"status": "HIRED", "next_action": "x", "due": "", "note": ""})
    assert response.status_code == 400


def test_closing_a_job_needs_no_next_action(make_confirmed_job, client, session):
    job = make_confirmed_job()
    response = client.post(f"/jobs/{job.id}/status", data={"status": "CLOSED", "next_action": "", "due": "", "note": ""})
    assert response.status_code == 303
    stored = _job(session, job.id)
    assert stored.status == "CLOSED" and stored.next_action is None


def test_next_action_form_updates_the_job(make_confirmed_job, client, session, today):
    job = make_confirmed_job()
    due = today + timedelta(days=4)
    response = client.post(f"/jobs/{job.id}/next", data={"text": "message HR on WeChat", "due": due.isoformat()})
    assert response.status_code == 303 and response.headers["location"] == f"/jobs/{job.id}?msg=next"
    stored = _job(session, job.id)
    assert stored.next_action == "message HR on WeChat" and stored.next_action_date == due


def test_next_action_form_requires_a_date(make_confirmed_job, client, session):
    job = make_confirmed_job()
    response = client.post(f"/jobs/{job.id}/next", data={"text": "message HR", "due": ""})
    assert response.status_code == 400
    assert _job(session, job.id).next_action == "assess fit"


def test_note_form_adds_a_note_event(make_confirmed_job, client, session):
    job = make_confirmed_job()
    response = client.post(f"/jobs/{job.id}/note", data={"text": "HR said March start is fine"})
    assert response.status_code == 303 and response.headers["location"] == f"/jobs/{job.id}?msg=note"
    event = _job(session, job.id).events[-1]
    assert event.kind == "note" and event.detail["note"] == "HR said March start is fine"


def test_empty_note_returns_400(make_confirmed_job, client):
    job = make_confirmed_job()
    assert client.post(f"/jobs/{job.id}/note", data={"text": "  "}).status_code == 400


def test_contact_form_adds_a_contact_on_the_company(make_confirmed_job, client, session):
    job = make_confirmed_job()
    response = client.post(
        f"/jobs/{job.id}/contact", data={"name": "Li Wei", "role": "HR", "channel": "wechat", "notes": "wxid_liwei"}
    )
    assert response.status_code == 303 and response.headers["location"] == f"/jobs/{job.id}?msg=contact"
    session.expire_all()
    (contact,) = session.query(Contact).all()
    assert contact.company_id == job.company_id and contact.notes == "wxid_liwei"


def test_contact_form_without_a_company_returns_400(make_confirmed_job, client):
    job = make_confirmed_job(company=False)
    response = client.post(f"/jobs/{job.id}/contact", data={"name": "Li Wei", "role": "", "channel": "wechat", "notes": ""})
    assert response.status_code == 400 and "no company" in response.text
