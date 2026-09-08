from datetime import date

import pytest

from internship_os.pipeline import (
    approve_sutd,
    recompute_all,
    recompute_job,
    set_agreed_dates,
    transition,
)
from internship_os.programme import constraint_warnings, run_programme, worst


def dims_of(job, config, today):
    return run_programme(job, job.company, config.constraints, config.user_facts, today)


def test_programme_yes_eligibility_confirmed_from_constraints(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app")
    dims, overall = dims_of(job, config, today)
    assert dims["YES_ELIGIBILITY"]["status"] == "CONFIRMED"
    assert "YES_ELIGIBILITY_CITIZEN_STUDENT" in dims["YES_ELIGIBILITY"]["note"]
    assert dims["IMMIGRATION"]["status"] == "LIKELY"
    assert dims["SUTD_APPROVAL"]["status"] == "LIKELY"
    assert "not yet explicitly approved" in dims["SUTD_APPROVAL"]["note"]
    assert dims["HOST_COMPANY"]["status"] == "UNKNOWN"
    assert dims["DURATION_AND_DATES"]["status"] == "LIKELY"
    assert overall == "UNKNOWN"


def test_programme_unknown_host_keeps_job_at_programme_check_required(session, make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", yes_status="unknown")
    result = transition(session, job, "SHORTLISTED", next_action="ask employer about YES", due=date(2026, 9, 15),
                        stage=None, note=None, config=config, today=today)
    assert result.final == "SHORTLISTED" and not result.refused
    result = transition(session, job, "READY_TO_APPLY", next_action="submit on 实习僧", due=date(2026, 9, 16),
                        stage=None, note=None, config=config, today=today)
    assert result.refused
    assert job.status == "PROGRAMME_CHECK_REQUIRED"
    assert job.next_action == "resolve programme check: HOST_COMPANY"
    assert job.next_action_date == today
    event = job.events[-1]
    assert event.kind == "status_change" and event.detail["requested"] == "READY_TO_APPLY"
    assert event.detail["to"] == "PROGRAMME_CHECK_REQUIRED"


def test_programme_unwilling_host_is_incompatible(session, make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", yes_status="unwilling")
    dims, overall = dims_of(job, config, today)
    assert dims["HOST_COMPANY"]["status"] == "INCOMPATIBLE"
    assert overall == "INCOMPATIBLE"
    assert job.tier == "HOLD"
    result = transition(session, job, "READY_TO_APPLY", next_action="x", due=today, stage=None, note=None,
                        config=config, today=today)
    assert result.refused and job.status == "PROGRAMME_CHECK_REQUIRED"
    assert "HOST_COMPANY" in job.next_action


def test_duration_8_months_min_is_at_risk_not_incompatible(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", yes_status="willing", duration_min_months=8, duration_max_months=None)
    dims, overall = dims_of(job, config, today)
    dd = dims["DURATION_AND_DATES"]
    assert dd["status"] == "AT_RISK"
    assert "8" in dd["note"] and "6" in dd["note"] and "negotiable" in dd["note"]
    assert overall == "AT_RISK"


def test_duration_3_month_max_is_at_risk_because_below_sutd_min(make_confirmed_job, config, today):
    job = make_confirmed_job("suzhou_backend", yes_status="willing")
    dims, overall = dims_of(job, config, today)
    dd = dims["DURATION_AND_DATES"]
    assert dd["status"] == "AT_RISK"
    assert "3" in dd["note"] and "4" in dd["note"]
    assert "SUTD minimum" in dd["note"] and "negotiable" in dd["note"]
    assert overall == "AT_RISK"


def test_duration_3_month_minimum_with_no_max_is_not_at_risk(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", yes_status="willing", duration_min_months=3, duration_max_months=None)
    dims, _ = dims_of(job, config, today)
    assert dims["DURATION_AND_DATES"]["status"] == "LIKELY"


def test_duration_range_covering_4_to_6_is_likely(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", yes_status="willing")
    dims, overall = dims_of(job, config, today)
    assert dims["DURATION_AND_DATES"]["status"] == "LIKELY"
    assert dims["HOST_COMPANY"]["status"] == "LIKELY"
    assert overall == "LIKELY"


def test_start_before_intended_start_is_at_risk(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", yes_status="willing", start_date="2027-01-15")
    dims, _ = dims_of(job, config, today)
    assert dims["DURATION_AND_DATES"]["status"] == "AT_RISK"
    assert "2027-01-15" in dims["DURATION_AND_DATES"]["note"]


def test_programme_overall_is_worst_dimension(make_confirmed_job, config, today):
    assert worst(["CONFIRMED", "LIKELY"]) == "LIKELY"
    assert worst(["CONFIRMED", "UNKNOWN", "LIKELY"]) == "UNKNOWN"
    assert worst(["AT_RISK", "UNKNOWN"]) == "AT_RISK"
    assert worst(["INCOMPATIBLE", "AT_RISK"]) == "INCOMPATIBLE"
    job = make_confirmed_job("hangzhou_ai_app", yes_status="unwilling", duration_min_months=8, duration_max_months=None)
    dims, overall = dims_of(job, config, today)
    assert dims["DURATION_AND_DATES"]["status"] == "AT_RISK"
    assert overall == "INCOMPATIBLE"


def test_past_verification_date_downgrades_dimension_and_warns(make_confirmed_job, config):
    job = make_confirmed_job("hangzhou_ai_app", yes_status="confirmed")
    later = date(2027, 2, 1)
    dims, _ = dims_of(job, config, later)
    assert dims["YES_ELIGIBILITY"]["status"] == "LIKELY"  # CONFIRMED -> LIKELY
    assert "YES_ELIGIBILITY_CITIZEN_STUDENT" in dims["YES_ELIGIBILITY"]["note"]
    assert dims["IMMIGRATION"]["status"] == "UNKNOWN"  # LIKELY -> UNKNOWN (Z_VISA_ROUTE_USER stale)
    assert dims["SUTD_APPROVAL"]["status"] == "UNKNOWN"
    warnings = constraint_warnings(config.constraints, later)
    joined = "\n".join(warnings)
    assert "YES_ELIGIBILITY_CITIZEN_STUDENT" in joined and "Z_VISA_ROUTE_USER" in joined
    # Not past on the verification date itself; stored statuses untouched.
    on_the_day = date(2026, 12, 1)
    dims_on, _ = dims_of(job, config, on_the_day)
    assert dims_on["IMMIGRATION"]["status"] == "LIKELY"
    assert config.constraints.require("Z_VISA_ROUTE_USER").status == "USER_CONFIRMED"
    # AT_RISK is never turned into INCOMPATIBLE by staleness.
    job2 = make_confirmed_job("suzhou_backend", yes_status="willing")
    dims2, _ = dims_of(job2, config, later)
    assert dims2["DURATION_AND_DATES"]["status"] == "AT_RISK"
    # REQUIRES_CONFIRMATION and UNVERIFIED constraints always warn.
    warnings_now = "\n".join(constraint_warnings(config.constraints, date(2026, 9, 9)))
    assert "LOC_LEAD_TIME" in warnings_now and "Z_VISA_EMBASSY_LEAD_TIME" in warnings_now


def test_programme_unknown_stays_separate_from_eligibility(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", yes_status="unknown")
    assert job.eligibility in ("ELIGIBLE", "LIKELY_ELIGIBLE")
    assert job.programme_overall == "UNKNOWN"
    assert job.tier == "T3"
    assert job.status == "DISCOVERED"


def test_agreed_dates_take_precedence(session, make_confirmed_job, config, today):
    job = make_confirmed_job("suzhou_backend", yes_status="willing")
    assert job.programme["DURATION_AND_DATES"]["status"] == "AT_RISK"
    set_agreed_dates(session, job, date(2027, 3, 1), 5, config, today)
    assert job.programme["DURATION_AND_DATES"]["status"] == "CONFIRMED"
    assert job.programme_overall == "LIKELY"
    assert job.start_date is None  # JD-extracted start untouched
    assert job.events[-1].kind == "programme_update"
    set_agreed_dates(session, job, date(2027, 3, 1), 3, config, today)
    assert job.programme["DURATION_AND_DATES"]["status"] == "AT_RISK"
    set_agreed_dates(session, job, date(2027, 2, 1), 5, config, today)
    assert job.programme["DURATION_AND_DATES"]["status"] == "AT_RISK"


def test_recompute_preserves_manual_fields(session, make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", yes_status="willing")
    approve_sutd(session, job, config, today)
    assert job.programme["SUTD_APPROVAL"]["status"] == "CONFIRMED"
    set_agreed_dates(session, job, date(2027, 3, 1), 6, config, today)
    job.fit = "strong"
    job.quality = "strong"
    session.commit()
    approved_at = job.sutd_approved_at
    recompute_job(job, config, today)
    changes = recompute_all(session, config, today)
    assert job.sutd_approved_at == approved_at
    assert job.agreed_start_date == date(2027, 3, 1) and job.agreed_duration_months == 6
    assert job.fit == "strong" and job.quality == "strong"
    assert job.company.yes_status == "willing"
    # IMMIGRATION stays LIKELY until the Z visa is issued, so overall is LIKELY.
    assert job.programme_overall == "LIKELY" and job.tier == "T1"
    assert [c[0].id for c in changes] == [job.id]


def test_transition_requires_next_for_non_terminal_and_note_for_ineligible(session, make_confirmed_job, config, today):
    from internship_os.pipeline import TransitionError

    job = make_confirmed_job("hangzhou_ai_app")
    with pytest.raises(TransitionError):
        transition(session, job, "SHORTLISTED", next_action=None, due=None, stage=None, note=None, config=config, today=today)
    with pytest.raises(TransitionError):
        transition(session, job, "INELIGIBLE", next_action=None, due=None, stage=None, note=None, config=config, today=today)
    result = transition(session, job, "WITHDRAWN", next_action=None, due=None, stage=None, note="not for me", config=config, today=today)
    assert result.final == "WITHDRAWN" and job.next_action is None and job.next_action_date is None


def test_ready_to_apply_refused_when_any_dimension_unknown_even_if_overall_at_risk(session, make_confirmed_job, config, today):
    job = make_confirmed_job("suzhou_backend", yes_status="unknown")
    assert job.programme_overall == "AT_RISK"
    result = transition(session, job, "READY_TO_APPLY", next_action="x", due=today, stage=None, note=None,
                        config=config, today=today)
    assert result.refused and job.status == "PROGRAMME_CHECK_REQUIRED"
    assert job.next_action == "resolve programme check: HOST_COMPANY"
    # Once the host is willing, AT_RISK alone proceeds with a warning.
    job.company.yes_status = "willing"
    session.commit()
    result = transition(session, job, "READY_TO_APPLY", next_action="x", due=today, stage=None, note=None,
                        config=config, today=today)
    assert not result.refused and job.status == "READY_TO_APPLY"
    assert any("DURATION_AND_DATES" in w for w in result.warnings)
