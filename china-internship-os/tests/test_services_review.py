"""The browser review form: field widgets, form parsing and confirmation."""

from __future__ import annotations

import pytest

from internship_os.models import Company
from internship_os.schemas import Degree, ExtractedJob
from internship_os.services import review as rv
from tests.conftest import FIXTURE_NAMES, load_extracted


def _form(extracted: ExtractedJob, **changes: str) -> dict[str, str]:
    """The form a browser submits when the user changes nothing but ``changes`` and ticks every box."""
    form = {f"field__{f.name}": f.value for f in rv.review_fields(extracted)}
    form.update({f"confirm__{name}": "on" for name in rv.ALWAYS_CONFIRM})
    form.update(changes)
    return form


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_unchanged_form_round_trips_every_field(name):
    extracted = load_extracted(name)
    confirmed, overrides, errors = rv.parse_form(extracted, _form(extracted))
    assert errors == {} and overrides == []
    assert confirmed.all_confirmed
    for field in ExtractedJob.field_names():
        assert confirmed.get(field).value == extracted.get(field).value, field
        assert confirmed.get(field).source_span == extracted.get(field).source_span, field


def test_must_confirm_fields_come_first_and_are_marked():
    fields = rv.review_fields(load_extracted("hangzhou_ai_app"))
    head = len(rv.ALWAYS_CONFIRM)
    assert [f.name for f in fields[:head]] == list(rv.ALWAYS_CONFIRM)
    assert sorted(f.name for f in fields) == sorted(ExtractedJob.field_names())
    assert all(f.must_confirm for f in fields[:head])
    assert not any(f.must_confirm for f in fields[head:])


def test_field_widgets_match_field_types():
    by = {f.name: f for f in rv.review_fields(load_extracted("hangzhou_ai_app"))}
    assert by["role_closed"].options == ["false", "true"] and by["role_closed"].value == "false"
    assert by["degree_required"].options == [d.value for d in Degree]
    assert by["degree_required"].value == "bachelor"
    assert by["cohort_years"].value == "2027, 2028"
    assert by["start_date"].kind == "date" and by["start_date"].value == "2027-03-01"
    assert by["deadline"].value == ""
    assert by["days_per_week_min"].kind == "number"
    assert by["cohort_years"].source_span


def test_empty_box_sets_null_and_records_override():
    extracted = load_extracted("hangzhou_ai_app")
    confirmed, overrides, errors = rv.parse_form(extracted, _form(extracted, field__district=""))
    assert errors == {}
    assert confirmed.district.value is None and confirmed.district.source_span is None
    assert [(o.field, o.old, o.new) for o in overrides] == [("district", "西湖区", None)]


def test_changed_value_is_typed_and_recorded():
    extracted = load_extracted("hangzhou_ai_app")
    confirmed, overrides, errors = rv.parse_form(
        extracted, _form(extracted, field__degree_required="master", field__cohort_years="2028")
    )
    assert errors == {}
    assert confirmed.degree_required.value == Degree.master
    assert confirmed.cohort_years.value == [2028]
    assert {o.field for o in overrides} == {"degree_required", "cohort_years"}


def test_bad_values_report_an_error_per_field():
    extracted = load_extracted("hangzhou_ai_app")
    _, _, errors = rv.parse_form(
        extracted, _form(extracted, field__deadline="next week", field__days_per_week_min="four")
    )
    assert set(errors) == {"deadline", "days_per_week_min"}


def test_missing_tick_is_an_error():
    extracted = load_extracted("hangzhou_ai_app")
    form = _form(extracted)
    del form["confirm__role_closed"]
    _, _, errors = rv.parse_form(extracted, form)
    assert set(errors) == {"role_closed"}


def test_review_fields_show_submitted_values_after_an_error():
    extracted = load_extracted("hangzhou_ai_app")
    form = {"field__district": "滨江区", "confirm__degree_required": "on"}
    by = {f.name: f for f in rv.review_fields(extracted, form=form, errors={"deadline": "bad date"})}
    assert by["district"].value == "滨江区"
    assert by["degree_required"].ticked and not by["role_closed"].ticked
    assert by["deadline"].error == "bad date"


def test_confirm_job_creates_company_and_runs_checks(capture_fixture, session, config, today, fake_llm):
    fake_llm["quality_checklist"] = '{"signals": []}'
    job = capture_fixture("hangzhou_ai_app")
    rv.confirm_job(session, job, _form(ExtractedJob.model_validate(job.extracted)), config, today)
    assert job.confirmed_at is not None
    assert job.company.name_zh == "杭州星河智能科技有限公司"
    assert job.eligibility == "LIKELY_ELIGIBLE" and job.next_action == "assess fit"
    assert [e.kind for e in job.events] == ["captured", "confirmed"]


def test_confirm_job_links_an_exact_company_match(capture_fixture, session, config, today, fake_llm):
    fake_llm["quality_checklist"] = '{"signals": []}'
    existing = Company(name_zh="杭州星河智能科技")
    session.add(existing)
    session.commit()
    job = capture_fixture("hangzhou_ai_app")
    rv.confirm_job(session, job, _form(ExtractedJob.model_validate(job.extracted)), config, today)
    assert job.company_id == existing.id


def test_confirm_job_needs_a_choice_when_only_near_matches(capture_fixture, session, config, today, fake_llm):
    fake_llm["quality_checklist"] = '{"signals": []}'
    near = Company(name_zh="杭州星河智能集团")
    session.add(near)
    session.commit()
    job = capture_fixture("hangzhou_ai_app")
    form = _form(ExtractedJob.model_validate(job.extracted))
    with pytest.raises(rv.ReviewInvalid) as exc:
        rv.confirm_job(session, job, form, config, today)
    assert "company" in exc.value.errors and job.confirmed_at is None
    rv.confirm_job(session, job, {**form, "company_choice": str(near.id)}, config, today)
    assert job.company_id == near.id


def test_confirm_job_can_create_a_new_company_despite_near_matches(capture_fixture, session, config, today, fake_llm):
    fake_llm["quality_checklist"] = '{"signals": []}'
    near = Company(name_zh="杭州星河智能集团")
    session.add(near)
    session.commit()
    job = capture_fixture("hangzhou_ai_app")
    form = {**_form(ExtractedJob.model_validate(job.extracted)), "company_choice": "new"}
    rv.confirm_job(session, job, form, config, today)
    assert job.company_id != near.id and job.company.name_zh == "杭州星河智能科技有限公司"


def test_confirm_job_refuses_an_already_confirmed_job(make_confirmed_job, session, config, today):
    job = make_confirmed_job()
    with pytest.raises(rv.ReviewInvalid):
        rv.confirm_job(session, job, _form(ExtractedJob.model_validate(job.extracted)), config, today)


def test_discard_closes_the_job_with_a_note(capture_fixture, session, config, today):
    job = capture_fixture("hangzhou_ai_app")
    rv.discard_job(session, job, config, today)
    assert job.status == "CLOSED" and job.next_action is None
    change = [e for e in job.events if e.kind == "status_change"][-1]
    assert change.detail["note"] == rv.DISCARD_NOTE
