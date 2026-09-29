from datetime import date

import pytest

from internship_os.pipeline import (
    approve_sutd,
    recompute_all,
    recompute_job,
    set_agreed_dates,
    transition,
)
from internship_os.programme import add_months, constraint_warnings, duration_and_dates, run_programme, worst


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
    job = make_confirmed_job("hangzhou_ai_app", yes_status="willing", start_date="2027-01-20")
    dims, _ = dims_of(job, config, today)
    assert dims["DURATION_AND_DATES"]["status"] == "AT_RISK"
    assert "2027-01-20" in dims["DURATION_AND_DATES"]["note"]


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
    session.expire_all()
    job = session.get(type(job), job.id)
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


def test_early_start_is_at_risk_even_without_duration(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", yes_status="willing", duration_min_months=None,
                             duration_max_months=None, start_date="2027-01-20")
    dims, _ = dims_of(job, config, today)
    assert dims["DURATION_AND_DATES"]["status"] == "AT_RISK"
    job2 = make_confirmed_job("hangzhou_ai_app", yes_status="willing", duration_min_months=None,
                              duration_max_months=None, start_date=None)
    dims2, _ = dims_of(job2, config, today)
    assert dims2["DURATION_AND_DATES"]["status"] == "UNKNOWN"


def test_asap_posting_adds_an_ask_hr_step_at_confirmation(make_confirmed_job, session, config, today):
    from internship_os.pipeline import finalize_confirmation, recompute_all
    from internship_os.schemas import ExtractedJob

    job = make_confirmed_job("suzhou_backend", run=False, start_timing="asap")
    finalize_confirmation(session, job, ExtractedJob.model_validate(job.extracted), job.company, [], config, today=today)
    expected = f"assess fit; ask HR whether a {config.user_facts.internship.intended_start.isoformat()} start works"
    assert job.next_action == expected and job.next_action_date == today
    job.next_action = "user's own next step"
    session.commit()
    recompute_all(session, config, today)
    assert job.next_action == "user's own next step"  # written once at confirmation, never on recompute


def test_named_month_posting_keeps_the_plain_next_action(make_confirmed_job, session, config, today):
    from internship_os.pipeline import finalize_confirmation
    from internship_os.schemas import ExtractedJob

    job = make_confirmed_job("hangzhou_ai_app", run=False)
    finalize_confirmation(session, job, ExtractedJob.model_validate(job.extracted), job.company, [], config, today=today)
    assert job.next_action == "assess fit"


def test_an_asap_posting_that_is_ineligible_gets_no_next_action(make_confirmed_job, session, config, today):
    from internship_os.pipeline import finalize_confirmation
    from internship_os.schemas import ExtractedJob

    job = make_confirmed_job("shanghai_llm_algorithm", run=False, start_timing="asap")  # master required
    finalize_confirmation(session, job, ExtractedJob.model_validate(job.extracted), job.company, [], config, today=today)
    assert job.status == "INELIGIBLE" and job.next_action is None


# --------------------------------------------------------------------------------------
# user_facts.internship.latest_end: the internship must end by this date
# --------------------------------------------------------------------------------------


def _facts(config, *, intended_start=date(2027, 2, 15), latest_end=date(2027, 8, 31)):
    """The test config with the personal dates set explicitly (the example file has no latest_end)."""
    facts = config.user_facts.model_copy(deep=True)
    facts.internship.intended_start = intended_start
    facts.internship.latest_end = latest_end
    return facts


def test_add_months_clamps_to_the_last_day_of_the_target_month():
    assert add_months(date(2027, 1, 31), 1) == date(2027, 2, 28)  # non-leap year
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)  # leap year
    assert add_months(date(2027, 2, 15), 6) == date(2027, 8, 15)
    assert add_months(date(2027, 12, 15), 3) == date(2028, 3, 15)  # year rollover
    assert add_months(date(2027, 3, 1), 6) == date(2027, 9, 1)


def test_agreed_dates_ending_after_latest_end_are_at_risk(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", yes_status="willing")
    job.agreed_start_date, job.agreed_duration_months = date(2027, 3, 1), 6  # ends 2027-09-01
    dd = duration_and_dates(job, config.constraints, _facts(config))
    assert dd["status"] == "AT_RISK"
    assert "2027-09-01" in dd["note"] and "2027-08-31" in dd["note"] and "latest_end" in dd["note"]
    dims, _ = run_programme(job, job.company, config.constraints, _facts(config), today)
    assert dims["DURATION_AND_DATES"]["status"] == "AT_RISK"
    # The same agreement with latest_end unset behaves as before this check existed.
    assert duration_and_dates(job, config.constraints, _facts(config, latest_end=None))["status"] == "CONFIRMED"


def test_agreed_dates_ending_by_latest_end_are_confirmed(make_confirmed_job, config):
    job = make_confirmed_job("hangzhou_ai_app", yes_status="willing")
    job.agreed_start_date, job.agreed_duration_months = date(2027, 2, 15), 6  # ends 2027-08-15
    assert duration_and_dates(job, config.constraints, _facts(config))["status"] == "CONFIRMED"
    # Ending on latest_end itself is not "after" it.
    job.agreed_start_date = date(2027, 3, 1)
    on_the_day = _facts(config, latest_end=date(2027, 9, 1))
    assert duration_and_dates(job, config.constraints, on_the_day)["status"] == "CONFIRMED"


def test_posting_start_plus_minimum_after_latest_end_is_at_risk(make_confirmed_job, config):
    job = make_confirmed_job(
        "hangzhou_ai_app", yes_status="willing", start_date="2027-04-01", duration_min_months=5, duration_max_months=6
    )
    dd = duration_and_dates(job, config.constraints, _facts(config))  # 2027-04-01 + 5 = 2027-09-01
    assert dd["status"] == "AT_RISK"
    assert "2027-09-01" in dd["note"] and "latest_end" in dd["note"] and "negotiable" in dd["note"]
    # latest_end unset: the existing LIKELY outcome is unchanged.
    assert duration_and_dates(job, config.constraints, _facts(config, latest_end=None))["status"] == "LIKELY"
    # Ending on latest_end itself is not "after" it.
    assert duration_and_dates(job, config.constraints, _facts(config, latest_end=date(2027, 9, 1)))["status"] == "LIKELY"


def test_posting_check_uses_the_minimum_duration_not_the_maximum(make_confirmed_job, config):
    job = make_confirmed_job("hangzhou_ai_app", yes_status="willing", start_date="2027-04-01")  # fixture: 4-6 months
    # 2027-04-01 + 4 = 2027-08-01 fits; the maximum (2027-10-01) would not.
    assert duration_and_dates(job, config.constraints, _facts(config))["status"] == "LIKELY"


def test_posting_start_after_latest_end_is_at_risk_even_without_a_minimum(make_confirmed_job, config):
    job = make_confirmed_job(
        "hangzhou_ai_app", yes_status="willing", start_date="2027-09-15", duration_min_months=None, duration_max_months=6
    )
    dd = duration_and_dates(job, config.constraints, _facts(config))
    assert dd["status"] == "AT_RISK" and "2027-09-15" in dd["note"] and "latest_end" in dd["note"]
    # With no minimum and a start in time, nothing is added: the length is unknown.
    early = make_confirmed_job(
        "hangzhou_ai_app", yes_status="willing", start_date="2027-07-01", duration_min_months=None, duration_max_months=6
    )
    assert duration_and_dates(early, config.constraints, _facts(config))["status"] == "LIKELY"


def test_posting_without_a_start_is_anchored_on_intended_start(make_confirmed_job, config):
    job = make_confirmed_job(
        "hangzhou_ai_app", yes_status="willing", start_date=None, duration_min_months=6, duration_max_months=None
    )
    assert duration_and_dates(job, config.constraints, _facts(config))["status"] == "LIKELY"  # 2027-02-15 + 6 = 2027-08-15
    late = duration_and_dates(job, config.constraints, _facts(config, intended_start=date(2027, 3, 15)))  # ends 2027-09-15
    assert late["status"] == "AT_RISK" and "intended start 2027-03-15" in late["note"]


def test_latest_end_before_intended_start_is_a_config_error(project_root):
    from internship_os.config import ConfigError, load_config

    with open(project_root / "n.log", "w") as fh:
        load_config(project_root, notice_stream=fh)  # creates user_facts.yaml from the example
    uf = project_root / "config" / "user_facts.yaml"
    uf.write_text(uf.read_text(encoding="utf-8").replace("latest_end: null", "latest_end: 2027-01-31"), encoding="utf-8")
    with open(project_root / "n.log", "w") as fh, pytest.raises(ConfigError) as excinfo:
        load_config(project_root, notice_stream=fh)
    (problem,) = excinfo.value.problems
    assert problem.file.endswith("user_facts.yaml") and problem.path == "internship"
    assert "latest_end" in problem.problem and "intended_start" in problem.problem
    assert "key:     internship" in excinfo.value.format()


def test_example_config_leaves_latest_end_unset(config):
    assert config.user_facts.internship.latest_end is None
