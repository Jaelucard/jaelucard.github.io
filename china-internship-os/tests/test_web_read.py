"""Read-only web pages: Today, Jobs, Job and Facts."""

from __future__ import annotations

from internship_os.pipeline import add_note
from internship_os.services.jobs import add_contact


def test_today_page_shows_contract_line_and_sections(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.text
    assert "CONTRACT MUST BE SIGNED BY" in body
    for heading in (
        "Needs your review",
        "Due today or overdue",
        "Upcoming",
        "Deadlines within 7 days",
        "Recommended today",
        "Pipeline",
        "Programme",
    ):
        assert heading in body, heading
    assert 'href="/capture"' in body


def test_today_links_jobs_needing_review(capture_fixture, client):
    job = capture_fixture("hangzhou_ai_app")
    assert f'href="/jobs/{job.id}/review"' in client.get("/").text


def test_jobs_page_lists_and_filters(make_confirmed_job, client):
    hz = make_confirmed_job()
    sz = make_confirmed_job("suzhou_backend")
    everything = client.get("/jobs").text
    assert f'href="/jobs/{hz.id}"' in everything and f'href="/jobs/{sz.id}"' in everything
    swe = client.get("/jobs", params={"track": "SWE"}).text
    assert f'href="/jobs/{sz.id}"' in swe and f'href="/jobs/{hz.id}"' not in swe


def test_job_page_shows_details_events_and_contacts(make_confirmed_job, session, client):
    job = make_confirmed_job()
    add_contact(session, job, name="Li Wei", role="HR", channel="wechat", notes=None)
    add_note(session, job, "called HR about the start date")
    body = client.get(f"/jobs/{job.id}").text
    assert job.title_zh in body and job.company.name_zh in body
    assert "called HR about the start date" in body and "Li Wei" in body
    assert "DURATION_AND_DATES" in body


def test_unconfirmed_job_page_links_to_review(capture_fixture, client):
    job = capture_fixture("hangzhou_ai_app")
    assert f'href="/jobs/{job.id}/review"' in client.get(f"/jobs/{job.id}").text


def test_facts_page_shows_constraints_with_verification_dates(client, config):
    body = client.get("/facts").text
    for constraint in config.constraints:
        assert constraint.constraint_id in body
    dated = next(c for c in config.constraints if c.next_verification_date)
    assert dated.next_verification_date.isoformat() in body
    assert "CONTRACT MUST BE SIGNED BY" in body


def test_unknown_job_returns_an_html_404(client):
    response = client.get("/jobs/999")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "job 999 does not exist" in response.text


def test_pages_show_their_cli_equivalent(client):
    assert "ios digest" in client.get("/").text
    assert "ios job list" in client.get("/jobs").text
    assert "ios constraints" in client.get("/facts").text


def test_timestamps_are_shown_in_local_time(make_confirmed_job, session, client, monkeypatch):
    import time
    from datetime import UTC, datetime

    job = make_confirmed_job()
    job.confirmed_at = datetime(2026, 9, 23, 17, 7, tzinfo=UTC)
    session.commit()
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    time.tzset()
    try:
        body = client.get(f"/jobs/{job.id}").text
    finally:
        monkeypatch.undo()
        time.tzset()
    assert "<dt>confirmed</dt><dd>2026-09-24</dd>" in body
