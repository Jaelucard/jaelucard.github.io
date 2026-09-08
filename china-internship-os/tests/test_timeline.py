from datetime import date

from internship_os.timeline import (
    CONTRACT_BY,
    EMBASSY_SUBMISSION,
    FLY,
    HOST_ENTRY_PERMIT_APPLICATION,
    LOC_APPLICATION,
    START_WORK,
    build_timeline,
    placeholders_in_use,
    step,
    top_line,
    warnings_for,
)

EXPECTED = {
    FLY: date(2027, 2, 26),
    EMBASSY_SUBMISSION: date(2027, 2, 19),
    HOST_ENTRY_PERMIT_APPLICATION: date(2027, 1, 29),
    LOC_APPLICATION: date(2027, 1, 15),
    CONTRACT_BY: date(2027, 1, 10),
}


def test_timeline_backward_dates_with_placeholders(config, today):
    steps = build_timeline(config.user_facts, config.constraints, None, today)
    assert step(steps, START_WORK).date == date(2027, 3, 1)
    for name, expected in EXPECTED.items():
        assert step(steps, name).date == expected, name
    assert placeholders_in_use(steps) == [
        "Z_VISA_EMBASSY_LEAD_TIME",
        "ENTRY_PERMIT_LEAD_TIME",
        "LOC_LEAD_TIME",
    ]
    assert step(steps, EMBASSY_SUBMISSION).uses_placeholder
    assert step(steps, CONTRACT_BY).uses_placeholder
    assert not step(steps, FLY).uses_placeholder
    assert top_line(steps, today) == (
        "CONTRACT MUST BE SIGNED BY 2027-01-10 (123 days). "
        "Placeholders in use: Z_VISA_EMBASSY_LEAD_TIME, ENTRY_PERMIT_LEAD_TIME, LOC_LEAD_TIME"
    )
    assert warnings_for(steps) == []


def test_timeline_warns_if_embassy_submission_before_exchange_end(config, today):
    facts = config.user_facts.model_copy(deep=True)
    facts.exchange.end_date = date(2027, 2, 18)  # + 2 days = 2027-02-20 > 2027-02-19
    steps = build_timeline(facts, config.constraints, None, today)
    warning = step(steps, EMBASSY_SUBMISSION).warning
    assert warning and "2027-02-19" in warning and "2027-02-18" in warning
    facts.exchange.end_date = date(2027, 2, 17)  # + 2 days = 2027-02-19, not before
    assert step(build_timeline(facts, config.constraints, None, today), EMBASSY_SUBMISSION).warning is None


def test_timeline_warns_if_contract_date_earlier_than_personal_deadline(config, today):
    facts = config.user_facts.model_copy(deep=True)
    facts.internship.offer_deadline_personal = date(2027, 1, 20)
    steps = build_timeline(facts, config.constraints, None, today)
    warning = step(steps, CONTRACT_BY).warning
    assert warning and "2027-01-10" in warning and "2027-01-20" in warning
    facts.internship.offer_deadline_personal = date(2027, 1, 10)
    assert step(build_timeline(facts, config.constraints, None, today), CONTRACT_BY).warning is None


def test_timeline_uses_verified_value_days_over_placeholder(config, today):
    constraints = config.constraints.model_copy(deep=True)
    constraints.require("LOC_LEAD_TIME").value_days = 0  # verified zero must count as verified
    constraints.require("ENTRY_PERMIT_LEAD_TIME").value_days = 28
    steps = build_timeline(config.user_facts, constraints, None, today)
    assert step(steps, HOST_ENTRY_PERMIT_APPLICATION).date == date(2027, 1, 22)
    assert step(steps, LOC_APPLICATION).date == date(2027, 1, 22)
    assert step(steps, LOC_APPLICATION).uses_placeholder is False
    assert step(steps, CONTRACT_BY).date == date(2027, 1, 17)
    assert placeholders_in_use(steps) == ["Z_VISA_EMBASSY_LEAD_TIME"]
    assert "Placeholders in use: Z_VISA_EMBASSY_LEAD_TIME" in top_line(steps, today)


def test_timeline_uses_agreed_start_not_extracted_start(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", start_date="2027-02-01")
    steps = build_timeline(config.user_facts, config.constraints, job, today)
    assert step(steps, START_WORK).date == date(2027, 3, 1)  # confirmed JD date is never the anchor
    job.agreed_start_date = date(2027, 4, 1)
    steps = build_timeline(config.user_facts, config.constraints, job, today)
    assert step(steps, START_WORK).date == date(2027, 4, 1)
    assert step(steps, FLY).date == date(2027, 3, 29)
    assert step(steps, CONTRACT_BY).date == date(2027, 2, 10)
    assert "agreed_start_date" in step(steps, START_WORK).derived_from
