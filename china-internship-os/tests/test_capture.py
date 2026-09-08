import json
from datetime import date

import httpx
import pytest
from sqlalchemy import func, select
from typer.testing import CliRunner

from internship_os import capture as capture_mod
from internship_os.capture import (
    CaptureNeedsPaste,
    DuplicateCaptureNeedsDecision,
    apply_confirmation,
    attach_to_existing,
    capture,
    create_company_from_extraction,
    find_company_matches,
    normalise_company,
    parse_override,
)
from internship_os.cli import app
from internship_os.models import Company, Job, JobEvent
from internship_os.pipeline import finalize_confirmation
from internship_os.schemas import ExtractedJob, force_unconfirmed
from tests.conftest import load_extracted, load_extracted_json, load_jd


def test_extracted_fields_default_unconfirmed(capture_fixture, session):
    job = capture_fixture("hangzhou_ai_app")
    assert job.id is not None
    assert job.confirmed_at is None
    assert job.status == "DISCOVERED"
    assert job.next_action == "confirm extraction"
    assert job.next_action_date == date(2026, 9, 9)
    extracted = ExtractedJob.model_validate(job.extracted)
    assert extracted.unconfirmed_fields() == ExtractedJob.field_names()
    assert all(not fld["confirmed"] for fld in job.extracted.values())
    assert job.raw_text == load_jd("hangzhou_ai_app").strip()
    assert [e.kind for e in job.events] == ["captured"]
    # Deterministic outcomes are untouched before confirmation.
    assert job.eligibility == "NOT_RUN" and job.tier == "NOT_RUN" and job.company_id is None


def test_capture_forces_unconfirmed_even_if_llm_claims_confirmed(session, config, fake_llm, today):
    data = json.loads(load_extracted_json("hangzhou_ai_app"))
    for fld in data.values():
        fld["confirmed"] = True
    fake_llm["extract_job"] = json.dumps(data, ensure_ascii=False)
    job = capture(load_jd("hangzhou_ai_app"), None, "shixiseng", session=session, config=config, today=today)
    assert all(not fld["confirmed"] for fld in job.extracted.values())
    assert force_unconfirmed({"x": {"value": 1, "confirmed": True, "source_span": None}}) == {
        "x": {"value": 1, "confirmed": False, "source_span": None}
    }


def test_dedup_same_company_title_city_prompts_not_merges(capture_fixture, session, config, today):
    first = capture_fixture("hangzhou_ai_app")
    with pytest.raises(DuplicateCaptureNeedsDecision) as excinfo:
        capture_fixture("hangzhou_ai_app", source="boss")
    assert excinfo.value.candidate_ids == [first.id]
    assert session.scalar(select(func.count()).select_from(Job)) == 1

    # Attaching adds a note event and still creates no job.
    attach_to_existing(session, first.id, text="dup text", url=None, source_channel="boss")
    session.refresh(first)
    assert [e.kind for e in first.events] == ["captured", "note"]
    assert first.events[-1].detail["source_channel"] == "boss"
    assert session.scalar(select(func.count()).select_from(Job)) == 1

    # Creating a separate job requires an explicit decision (force_new) and reuses the extraction.
    second = capture(
        excinfo.value.text, None, "boss", session=session, config=config, today=today,
        extracted=excinfo.value.extracted, force_new=True,
    )
    assert second.id != first.id
    assert session.scalar(select(func.count()).select_from(Job)) == 2

    # Same source URL is also a duplicate, even for a different title.
    url = "https://example.com/jobs/1"
    capture_fixture("suzhou_backend", url=url)
    with pytest.raises(DuplicateCaptureNeedsDecision):
        capture_fixture("shanghai_llm_algorithm", url=url)


def test_dedup_cli_requires_explicit_choice(capture_fixture, engine, project_root):
    first = capture_fixture("hangzhou_ai_app")
    runner = CliRunner()
    jd = project_root / "jd.txt"
    jd.write_text(load_jd("hangzhou_ai_app"), encoding="utf-8")
    # Cancel: nothing is created.
    result = runner.invoke(app, ["capture", "--text-file", str(jd), "--source", "boss"], input="3\n")
    assert result.exit_code == 0, result.output
    assert "Possible duplicate" in result.output and "Cancelled" in result.output
    with engine.connect() as conn:
        assert conn.exec_driver_sql("select count(*) from jobs").scalar() == 1
    # Attach: still one job, one more note event.
    result = runner.invoke(app, ["capture", "--text-file", str(jd), "--source", "boss"], input="1\n")
    assert result.exit_code == 0, result.output
    assert f"Attached capture as a note to job {first.id}" in result.output
    with engine.connect() as conn:
        assert conn.exec_driver_sql("select count(*) from jobs").scalar() == 1
        assert conn.exec_driver_sql("select count(*) from job_events where kind='note'").scalar() == 1
    # Create new: two jobs.
    result = runner.invoke(app, ["capture", "--text-file", str(jd), "--source", "boss"], input="2\n")
    assert result.exit_code == 0, result.output
    with engine.connect() as conn:
        assert conn.exec_driver_sql("select count(*) from jobs").scalar() == 2


def test_capture_cli_requires_exactly_one_input(project_root, engine):
    runner = CliRunner()
    result = runner.invoke(app, ["capture", "--source", "boss"])
    assert result.exit_code == 2
    result = runner.invoke(app, ["capture", "--paste", "--url", "https://x", "--source", "boss"])
    assert result.exit_code == 2


def test_url_capture_fails_gracefully_without_network(monkeypatch, session, config, today, fake_llm):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        request = httpx.Request("GET", url)
        return httpx.Response(403, request=request, text="forbidden")

    monkeypatch.setattr(capture_mod.httpx, "get", fake_get)
    with pytest.raises(CaptureNeedsPaste, match="HTTP 403"):
        capture(None, "https://www.zhipin.com/job/1", "boss", session=session, config=config, today=today)
    assert calls and calls[0][1]["follow_redirects"] is False
    assert calls[0][1]["timeout"] == 10.0

    def login_wall(url, **kwargs):
        request = httpx.Request("GET", url)
        body = "<html><body><p>" + "请登录后查看职位详情。" * 40 + "</p></body></html>"
        return httpx.Response(200, request=request, text=body)

    monkeypatch.setattr(capture_mod.httpx, "get", login_wall)
    with pytest.raises(CaptureNeedsPaste, match="paste"):
        capture(None, "https://example.com/j", "boss", session=session, config=config, today=today)

    with pytest.raises(CaptureNeedsPaste, match="http"):
        capture(None, "ftp://example.com/j", "boss", session=session, config=config, today=today)
    assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_parse_override_types():
    assert parse_override("cohort_years", "[2027, 2028]") == [2027, 2028]
    assert parse_override("cohort_years", "2027, 2028") == [2027, 2028]
    assert parse_override("required_skills", "Python, Go") == ["Python", "Go"]
    assert parse_override("deadline", "2026-10-01") == date(2026, 10, 1)
    assert parse_override("role_closed", "true") is True
    assert parse_override("degree_required", "master").value == "master"
    with pytest.raises(ValueError):
        parse_override("deadline", "1 Oct 2026")
    with pytest.raises(ValueError):
        parse_override("degree_required", "diploma")
    with pytest.raises(ValueError):
        parse_override("role_closed", "yes")


def test_apply_confirmation_override_and_accept_all():
    extracted = load_extracted("hangzhou_ai_app")
    answers = {"degree_required": "master", "deadline": "2026-10-01", "district": "-"}

    def decide(name, field, error):
        assert error is None
        if name in answers:
            return answers[name]
        return "a" if name == "salary_text" else ""

    confirmed, overrides = apply_confirmation(extracted, decide)
    assert confirmed.all_confirmed
    assert confirmed.degree_required.value == "master"
    assert confirmed.degree_required.source_span is None
    assert confirmed.deadline.value == date(2026, 10, 1)
    assert confirmed.district.value is None and confirmed.district.confirmed
    by_field = {o.field: o for o in overrides}
    assert by_field["degree_required"].old == "bachelor" and by_field["degree_required"].new == "master"
    assert by_field["district"].old == "西湖区" and by_field["district"].new is None
    # Fields after 'a' were accepted without being asked.
    assert confirmed.research_signals.confirmed


def test_finalize_confirmation_links_company_and_sets_next_action(capture_fixture, session, config, today):
    job = capture_fixture("hangzhou_ai_app")
    confirmed, overrides = apply_confirmation(ExtractedJob.model_validate(job.extracted), lambda *a: "a")
    exact, near = find_company_matches(session, confirmed.company_name_zh.value, None)
    assert exact is None and near == []
    company = create_company_from_extraction(session, confirmed)
    result = finalize_confirmation(session, job, confirmed, company, overrides, config, today=today)
    assert result.job.confirmed_at is not None
    assert job.company_id == company.id and company.name_zh == "杭州星河智能科技有限公司"
    assert job.city_zh == "杭州" and job.track == "AI" and job.start_date == date(2027, 3, 1)
    assert job.duration_months is None  # range 4-6, not an exact duration
    assert job.next_action == "assess fit" and job.next_action_date == today
    assert [e.kind for e in job.events] == ["captured", "confirmed"]
    # Exact normalised match now links; suffix stripping makes 杭州星河智能 match.
    exact, _ = find_company_matches(session, "杭州星河智能科技", None)
    assert exact is not None and exact.id == company.id
    assert normalise_company("杭州星河智能科技有限公司") == "杭州星河智能"


def test_confirm_cli_accept_all(capture_fixture, engine, project_root):
    job = capture_fixture("suzhou_backend")
    runner = CliRunner()
    result = runner.invoke(app, ["confirm", str(job.id)], input="a\n")
    assert result.exit_code == 0, result.output
    assert "Created company" in result.output
    with engine.connect() as conn:
        row = conn.exec_driver_sql("select confirmed_at, city_zh, company_id from jobs").one()
    assert row[0] is not None and row[1] == "苏州" and row[2] is not None
    result = runner.invoke(app, ["confirm", str(job.id)], input="a\n")
    assert "already confirmed" in result.output


def test_confirmation_to_ineligible_emits_status_change(make_confirmed_job, session, config, today):
    from internship_os.capture import dedup_keys
    from internship_os.pipeline import apply_eligibility_effect, finalize_confirmation

    job = make_confirmed_job("shanghai_llm_algorithm", run=False)
    confirmed = ExtractedJob.model_validate(job.extracted)
    finalize_confirmation(session, job, confirmed, job.company, [], config, today=today)
    assert job.status == "INELIGIBLE" and job.tier == "HOLD"
    kinds = [e.kind for e in job.events]
    assert "status_change" in kinds and kinds.index("status_change") < kinds.index("confirmed")
    assert dedup_keys(["Acme 有限公司"], [None, None], "杭州") == {"acme|<no-title>|杭州"}
