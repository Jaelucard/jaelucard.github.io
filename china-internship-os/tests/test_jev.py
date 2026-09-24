"""Jev questions, the stored suggestion record, and how answers become review notes."""

from __future__ import annotations

import json

import pytest

from internship_os import jev
from internship_os.decision_provider import Decision, DecisionBatch, FakeDecisionProvider, NullProvider
from internship_os.schemas import ChineseLevel, Degree, ExtractedJob, StartTiming, Track
from tests.conftest import load_extracted, load_jd


def _cfg():
    from internship_os.decision_provider import DecisionsConfig

    return DecisionsConfig(provider="typesafe", noul_flag_p=0.7, choice_min_confidence=0.6)


def test_choice_questions_use_the_repo_vocabularies():
    questions = jev.posting_questions()
    assert set(questions["track"]["criteria"]) == {t.value for t in Track if t != Track.unknown}
    assert set(questions["degree"]["criteria"]) == {d.value for d in Degree}
    assert set(questions["chinese_level"]["criteria"]) == {c.value for c in ChineseLevel}
    assert set(questions["start_timing"]["criteria"]) == {s.value for s in StartTiming}
    assert "cohort" not in questions  # code decides cohorts, not Jev


def test_state_holds_posting_text_and_extracted_values_only(config):
    extracted = load_extracted("hangzhou_ai_app")
    state = jev.build_state(load_jd("hangzhou_ai_app"), extracted)
    assert set(state) == {"posting", "fields"} and state["posting"] == load_jd("hangzhou_ai_app")
    # The questions carry nothing about the user: no name, university, cohort or handles.
    questions = json.dumps(jev.all_questions(extracted), ensure_ascii=False)
    facts = config.user_facts
    for personal in (facts.name, facts.university, facts.graduation_cohort, facts.github, str(facts.cohort_year)):
        assert personal not in questions, personal


def test_yes_no_fields_are_checked_as_conditions_not_as_information():
    extracted = load_extracted("hangzhou_ai_app")  # cohort_unrestricted false: cohorts are listed
    question = jev.check_questions(extracted)["check__cohort_unrestricted"]
    assert "information" not in question["instructions"]
    assert "any graduation year" in jev.build_state("text", extracted)["fields"]["cohort_unrestricted"]["meaning"]


def test_support_checks_ask_about_found_and_missing_values():
    extracted = load_extracted("suzhou_backend")  # cohort_unrestricted true, role_closed false
    checks = jev.check_questions(extracted)
    assert set(checks) == {f"check__{name}" for name in jev.CHECKED_FIELDS}
    assert "unsupported" in checks["check__cohort_unrestricted"]["criteria"]["true"].lower()
    assert "states" in checks["check__role_closed"]["criteria"]["true"].lower()


def test_record_stores_the_answers_as_a_job_event(capture_fixture, session, config):
    job = capture_fixture("hangzhou_ai_app")
    provider = FakeDecisionProvider({"degree": Decision("choice", "bachelor", 0.9, {"bachelor": 0.9})}, model="jev-test")
    outcome = jev.record_suggestions(session, job, config, provider=provider)
    assert outcome.state == "on" and outcome.model == "jev-test"
    event = job.events[-1]
    assert event.kind == "jev_suggestions"
    assert event.detail["model"] == "jev-test" and event.detail["decisions"]["degree"]["value"] == "bachelor"
    assert provider.calls and provider.calls[0][0]["posting"] == job.raw_text


def test_record_is_skipped_when_jev_is_off(capture_fixture, session, config):
    job = capture_fixture("hangzhou_ai_app")
    outcome = jev.record_suggestions(session, job, config, provider=NullProvider("no key"))
    assert outcome.state == "off" and outcome.detail == "no key"
    assert [e.kind for e in job.events] == ["captured"]


def test_record_survives_a_provider_error(capture_fixture, session, config):
    job = capture_fixture("hangzhou_ai_app")
    outcome = jev.record_suggestions(session, job, config, provider=FakeDecisionProvider({}, raises=TimeoutError("slow")))
    assert outcome.state == "failed" and outcome.detail == "TimeoutError"
    assert job.events[-1].kind == "jev_suggestions" and job.events[-1].detail["error"] == "TimeoutError"


def test_record_survives_a_broken_provider_setup(capture_fixture, session, config, monkeypatch):
    job = capture_fixture("hangzhou_ai_app")

    def broken(_config):
        raise ValueError("bad key format")

    monkeypatch.setattr(jev, "get_provider", broken)
    outcome = jev.record_suggestions(session, job, config)
    assert outcome.state == "failed" and outcome.detail == "ValueError"


def _batch(**decisions) -> dict:
    return jev.record_detail(DecisionBatch("jev-test", decisions), error=None)


def test_a_disagreeing_choice_becomes_a_field_note():
    extracted = load_extracted("hangzhou_ai_app")  # degree_required bachelor
    view = jev.interpret(_batch(degree=Decision("choice", "master", 0.9, {})), extracted, _cfg())
    assert any("master" in note for note in view.notes["degree_required"])


def test_an_agreeing_confident_choice_adds_no_note():
    extracted = load_extracted("hangzhou_ai_app")
    view = jev.interpret(_batch(degree=Decision("choice", "bachelor", 0.95, {})), extracted, _cfg())
    assert "degree_required" not in view.notes


def test_an_unsure_choice_is_flagged():
    extracted = load_extracted("hangzhou_ai_app")
    view = jev.interpret(_batch(degree=Decision("choice", "bachelor", 0.4, {})), extracted, _cfg())
    assert any("unsure" in note for note in view.notes["degree_required"])


def test_posting_warnings_are_shown_apart_from_field_notes():
    extracted = load_extracted("hangzhou_ai_app")
    view = jev.interpret(_batch(pays_fee=Decision("noul", 0.92, None, {}), mostly_sales=Decision("noul", 0.2, None, {})),
                         extracted, _cfg())
    assert len(view.warnings) == 1 and "fee" in view.warnings[0]


def test_an_unsupported_value_is_flagged_on_its_field():
    extracted = load_extracted("hangzhou_ai_app")
    view = jev.interpret(_batch(check__graduation_cohort_text=Decision("noul", 0.85, None, {})), extracted, _cfg())
    assert view.notes["graduation_cohort_text"]


def test_a_restriction_jev_sees_but_the_extraction_missed_is_flagged():
    extracted = load_extracted("hangzhou_ai_app")  # no restriction extracted
    view = jev.interpret(_batch(restricted=Decision("noul", 0.9, None, {})), extracted, _cfg())
    assert view.notes["nationality_or_work_auth_restriction"]


def test_answers_below_the_threshold_add_nothing():
    extracted = load_extracted("hangzhou_ai_app")
    view = jev.interpret(
        _batch(check__role_closed=Decision("noul", 0.3, None, {}), pays_fee=Decision("noul", 0.5, None, {})),
        extracted, _cfg(),
    )
    assert view.notes == {} and view.warnings == []


def test_latest_record_reads_the_newest_event(capture_fixture, session, config):
    job = capture_fixture("hangzhou_ai_app")
    jev.record_suggestions(session, job, config, provider=FakeDecisionProvider({}, model="first"))
    jev.record_suggestions(session, job, config, provider=FakeDecisionProvider({}, model="second"))
    assert jev.latest_record(job)["model"] == "second"


@pytest.mark.parametrize("module", ["eligibility", "programme", "tiering", "digest", "pipeline", "timeline"])
def test_gates_never_read_jev_output(module):
    import importlib
    import inspect

    source = inspect.getsource(importlib.import_module(f"internship_os.{module}"))
    for marker in ("jev", "decision_provider", "suggestion"):
        assert marker not in source.lower(), f"{module} mentions {marker}"
