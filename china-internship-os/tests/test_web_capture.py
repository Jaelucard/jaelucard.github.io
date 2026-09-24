"""Capture a posting in the browser, then review and confirm it (the web `ios confirm`)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from internship_os.models import Company, Job
from internship_os.schemas import ExtractedJob
from internship_os.services import review as rv
from tests.conftest import load_jd


def _jobs(session) -> list[Job]:
    session.expire_all()
    return list(session.scalars(select(Job).order_by(Job.id)))


def _review_form(job: Job, *, ticks: bool = True) -> dict[str, str]:
    extracted = ExtractedJob.model_validate(job.extracted)
    form = {f"field__{f.name}": f.value for f in rv.review_fields(extracted)}
    if ticks:
        form.update({f"confirm__{name}": "on" for name in rv.ALWAYS_CONFIRM})
    return form


# --------------------------------------------------------------------------------------
# Capture
# --------------------------------------------------------------------------------------


def test_capture_form_lists_source_channels(client):
    body = client.get("/capture").text
    assert 'name="text"' in body and '<option value="shixiseng"' in body


def test_capture_creates_an_unconfirmed_job_and_opens_review(client, session):
    response = client.post("/capture", data={"text": load_jd("hangzhou_ai_app"), "source": "shixiseng", "url": ""})
    assert response.status_code == 303
    (job,) = _jobs(session)
    assert response.headers["location"] == f"/jobs/{job.id}/review"
    assert job.confirmed_at is None and job.source_channel == "shixiseng"
    assert [e.kind for e in job.events] == ["captured"]


def test_capture_records_the_url_without_fetching_it(client, session, monkeypatch):
    import internship_os.capture as capture_module

    monkeypatch.setattr(capture_module.httpx, "get", lambda *a, **k: pytest.fail("the web capture fetched a URL"))
    client.post("/capture", data={"text": load_jd("hangzhou_ai_app"), "source": "boss", "url": "https://example.com/job/1"})
    (job,) = _jobs(session)
    assert job.source_url == "https://example.com/job/1"


def test_capture_requires_text_and_a_known_source(client, session):
    assert client.post("/capture", data={"text": "   ", "source": "shixiseng"}).status_code == 400
    assert client.post("/capture", data={"text": "岗位职责", "source": "carrier_pigeon"}).status_code == 400
    assert _jobs(session) == []


def test_extraction_failure_keeps_the_text_and_shows_the_error(client, session, fake_llm):
    fake_llm["extract_job"] = "not json"
    response = client.post("/capture", data={"text": "某公司 实习生 岗位职责 任职要求", "source": "boss"})
    assert response.status_code == 400
    assert "某公司 实习生 岗位职责 任职要求" in response.text and "Extraction failed" in response.text
    assert _jobs(session) == []


def test_duplicate_capture_offers_attach_or_create(capture_fixture, client, session):
    first = capture_fixture("hangzhou_ai_app")
    response = client.post("/capture", data={"text": load_jd("hangzhou_ai_app"), "source": "boss"})
    assert response.status_code == 409
    assert f'href="/jobs/{first.id}"' in response.text
    assert 'name="action" value="attach"' in response.text and 'name="action" value="new"' in response.text
    assert len(_jobs(session)) == 1


def test_duplicate_attach_adds_a_note_and_no_job(capture_fixture, client, session):
    first = capture_fixture("hangzhou_ai_app")
    response = client.post(
        "/capture",
        data={"text": load_jd("hangzhou_ai_app"), "source": "boss", "action": "attach", "attach_to": str(first.id)},
    )
    assert response.status_code == 303 and response.headers["location"] == f"/jobs/{first.id}?msg=attached"
    (job,) = _jobs(session)
    assert job.events[-1].kind == "note" and job.events[-1].detail["note"] == "duplicate capture attached"


def test_duplicate_create_anyway_reuses_the_extraction(capture_fixture, client, session, fake_llm):
    first = capture_fixture("hangzhou_ai_app")
    fake_llm["extract_job"] = lambda prompt: pytest.fail("the extraction should be reused, not re-run")
    response = client.post(
        "/capture",
        data={
            "text": load_jd("hangzhou_ai_app"),
            "source": "boss",
            "action": "new",
            "extracted_json": ExtractedJob.model_validate(first.extracted).model_dump_json(),
        },
    )
    assert response.status_code == 303
    assert len(_jobs(session)) == 2


# --------------------------------------------------------------------------------------
# Review and confirm
# --------------------------------------------------------------------------------------


def test_review_page_lists_every_field_with_sources_and_ticks(capture_fixture, client):
    job = capture_fixture("hangzhou_ai_app")
    body = client.get(f"/jobs/{job.id}/review").text
    for name in ExtractedJob.field_names():
        assert f'name="field__{name}"' in body, name
    for name in rv.ALWAYS_CONFIRM:
        assert f'name="confirm__{name}"' in body, name
    assert "2027年3月起可入职" in body
    assert body.index('name="field__degree_required"') < body.index('name="field__company_name_zh"')


def test_enter_in_a_field_submits_confirm_not_discard(capture_fixture, client):
    job = capture_fixture("hangzhou_ai_app")
    body = client.get(f"/jobs/{job.id}/review").text
    start = body.index(f'action="/jobs/{job.id}/review"')
    review_form = body[start : body.index("</form>", start)]
    assert "discard" not in review_form.lower()
    assert body.index(f'action="/jobs/{job.id}/discard"') > start


def test_confirm_without_ticks_returns_400_and_keeps_edits(capture_fixture, client, session):
    job = capture_fixture("hangzhou_ai_app")
    form = {**_review_form(job, ticks=False), "field__district": "滨江区"}
    response = client.post(f"/jobs/{job.id}/review", data=form)
    assert response.status_code == 400
    assert 'value="滨江区"' in response.text and "tick the box" in response.text
    assert _jobs(session)[0].confirmed_at is None


def test_confirm_saves_the_job_and_opens_it(capture_fixture, client, session, fake_llm):
    fake_llm["quality_checklist"] = '{"signals": []}'
    job = capture_fixture("hangzhou_ai_app")
    response = client.post(f"/jobs/{job.id}/review", data=_review_form(job))
    assert response.status_code == 303 and response.headers["location"] == f"/jobs/{job.id}?msg=confirmed"
    (stored,) = _jobs(session)
    assert stored.confirmed_at is not None and stored.company is not None
    assert stored.next_action == "assess fit"
    assert "Confirmed." in client.get(response.headers["location"]).text


def test_confirm_reports_a_failed_quality_checklist(capture_fixture, client):
    job = capture_fixture("hangzhou_ai_app")  # no quality_checklist response registered, so it fails
    response = client.post(f"/jobs/{job.id}/review", data=_review_form(job))
    assert response.headers["location"] == f"/jobs/{job.id}?msg=checklist_failed"


def test_near_company_match_needs_a_choice_on_the_page(capture_fixture, client, session, fake_llm):
    fake_llm["quality_checklist"] = '{"signals": []}'
    near = Company(name_zh="杭州星河智能集团")
    session.add(near)
    session.commit()
    job = capture_fixture("hangzhou_ai_app")
    body = client.get(f"/jobs/{job.id}/review").text
    assert f'name="company_choice" value="{near.id}"' in body
    response = client.post(f"/jobs/{job.id}/review", data=_review_form(job))
    assert response.status_code == 400 and "similar companies exist" in response.text
    response = client.post(f"/jobs/{job.id}/review", data={**_review_form(job), "company_choice": str(near.id)})
    assert response.status_code == 303
    assert _jobs(session)[0].company_id == near.id


def test_discard_closes_the_capture(capture_fixture, client, session):
    job = capture_fixture("hangzhou_ai_app")
    response = client.post(f"/jobs/{job.id}/discard")
    assert response.status_code == 303 and response.headers["location"] == f"/jobs/{job.id}?msg=discarded"
    assert _jobs(session)[0].status == "CLOSED"


def test_review_of_a_confirmed_job_goes_to_the_job_page(make_confirmed_job, client):
    job = make_confirmed_job()
    response = client.get(f"/jobs/{job.id}/review")
    assert response.status_code == 303 and response.headers["location"] == f"/jobs/{job.id}"


def test_edited_company_name_with_similar_company_offers_the_choice(capture_fixture, client, session, fake_llm):
    fake_llm["quality_checklist"] = '{"signals": []}'
    near = Company(name_zh="杭州星河智能集团")
    session.add(near)
    session.commit()
    job = capture_fixture("hangzhou_ai_app")
    data = dict(job.extracted)
    data["company_name_zh"] = {**data["company_name_zh"], "value": None, "source_span": None}
    job.extracted = data
    session.commit()
    form = {**_review_form(job), "field__company_name_zh": "杭州星河智能科技有限公司"}
    response = client.post(f"/jobs/{job.id}/review", data=form)
    assert response.status_code == 400
    assert f'name="company_choice" value="{near.id}"' in response.text
    assert 'name="company_choice" value="new"' in response.text
    response = client.post(f"/jobs/{job.id}/review", data={**form, "company_choice": "new"})
    assert response.status_code == 303


def test_create_anyway_stores_every_field_unconfirmed(capture_fixture, client, session):
    first = capture_fixture("hangzhou_ai_app")
    tampered = {name: {**field, "confirmed": True} for name, field in first.extracted.items()}
    import json

    client.post(
        "/capture",
        data={"text": load_jd("hangzhou_ai_app"), "source": "boss", "action": "new", "extracted_json": json.dumps(tampered)},
    )
    second = _jobs(session)[-1]
    assert second.id != first.id
    assert not any(field["confirmed"] for field in second.extracted.values())


def test_opening_the_review_page_confirms_nothing(capture_fixture, client, session):
    job = capture_fixture("hangzhou_ai_app")
    client.get(f"/jobs/{job.id}/review")
    stored = _jobs(session)[0]
    assert stored.confirmed_at is None
    assert not any(field["confirmed"] for field in stored.extracted.values())


def test_attach_needs_a_real_job_id(capture_fixture, client, session):
    capture_fixture("hangzhou_ai_app")
    for bad in ("abc", "9" * 25, "424242"):
        response = client.post(
            "/capture", data={"text": load_jd("hangzhou_ai_app"), "source": "boss", "action": "attach", "attach_to": bad}
        )
        assert response.status_code == 400, bad
        assert "invalid literal" not in response.text
    assert len(_jobs(session)) == 1


def test_review_post_for_a_job_without_extraction_is_404(make_confirmed_job, client, session):
    job = make_confirmed_job()
    job.confirmed_at = None
    job.extracted = None
    session.commit()
    assert client.post(f"/jobs/{job.id}/review", data={}).status_code == 404


def test_discarding_twice_does_not_add_a_second_close(capture_fixture, client, session):
    job = capture_fixture("hangzhou_ai_app")
    client.post(f"/jobs/{job.id}/discard")
    response = client.post(f"/jobs/{job.id}/discard")
    assert response.headers["location"] == f"/jobs/{job.id}"
    assert [e.kind for e in _jobs(session)[0].events].count("closed") == 1


# --------------------------------------------------------------------------------------
# Jev on capture and review
# --------------------------------------------------------------------------------------


def _fake_jev(monkeypatch, decisions=None, raises=None):
    from internship_os import jev
    from internship_os.decision_provider import FakeDecisionProvider

    provider = FakeDecisionProvider(decisions or {}, model="jev-test", raises=raises)
    monkeypatch.setattr(jev, "get_provider", lambda config: provider)
    return provider


def test_capture_asks_jev_once_and_review_shows_its_notes(client, session, monkeypatch):
    from internship_os.decision_provider import Decision

    provider = _fake_jev(monkeypatch, {
        "degree": Decision("choice", "master", 0.9, {}),
        "pays_fee": Decision("noul", 0.95, None, {}),
    })
    response = client.post("/capture", data={"text": load_jd("hangzhou_ai_app"), "source": "boss"})
    assert len(provider.calls) == 1
    (job,) = _jobs(session)
    assert [e.kind for e in job.events] == ["captured", "jev_suggestions"]
    body = client.get(response.headers["location"]).text
    assert "Jev suggests master" in body and "pay a fee" in body and "jev-test" in body


def test_review_says_when_jev_is_off(capture_fixture, client):
    job = capture_fixture("hangzhou_ai_app")
    assert "Jev: off" in client.get(f"/jobs/{job.id}/review").text


def test_a_jev_failure_does_not_stop_the_capture(client, session, monkeypatch):
    _fake_jev(monkeypatch, raises=TimeoutError("slow"))
    response = client.post("/capture", data={"text": load_jd("hangzhou_ai_app"), "source": "boss"})
    assert response.status_code == 303
    assert "could not check this posting (TimeoutError)" in client.get(response.headers["location"]).text


def test_review_shows_regex_cross_check_notes(capture_fixture, client, session):
    job = capture_fixture("hangzhou_ai_app")  # the posting says 4-6 months
    data = dict(job.extracted)
    data["duration_min_months"] = {**data["duration_min_months"], "value": 3}
    job.extracted = data
    session.commit()
    assert "The posting text reads as 4-6 months" in client.get(f"/jobs/{job.id}/review").text
