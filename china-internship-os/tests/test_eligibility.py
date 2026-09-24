
from internship_os.eligibility import run_eligibility, skill_matches


def codes(reasons):
    return [r.code for r in reasons]


def test_eligibility_not_run_on_unconfirmed_fields(capture_fixture, config, today):
    job = capture_fixture("hangzhou_ai_app")
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "NOT_RUN"
    assert codes(reasons) == ["UNCONFIRMED_FIELDS"]
    assert "degree_required" in reasons[0].detail


def test_master_required_is_ineligible(make_confirmed_job, config, today):
    job = make_confirmed_job("shanghai_llm_algorithm")
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "INELIGIBLE"
    assert "DEGREE_INELIGIBLE" in codes(reasons)
    degree = next(r for r in reasons if r.code == "DEGREE_INELIGIBLE")
    assert degree.field == "degree_required" and "master" in degree.detail
    assert "RESEARCH_ROLE_SIGNALS" in codes(reasons)


def test_cohort_2028_in_list_is_eligible(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app")
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status in ("ELIGIBLE", "LIKELY_ELIGIBLE")
    assert "GRADUATION_COHORT_INELIGIBLE" not in codes(reasons)


def test_cohort_2027_only_is_ineligible(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", cohort_years=[2027], graduation_cohort_text="2027届")
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "INELIGIBLE"
    reason = next(r for r in reasons if r.code == "GRADUATION_COHORT_INELIGIBLE")
    assert reason.field == "cohort_years"
    assert "2028" in reason.detail and "2027" in reason.detail


def test_cohort_unrestricted_passes(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", cohort_years=[2027], cohort_unrestricted=True)
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status != "INELIGIBLE"
    assert "GRADUATION_COHORT_INELIGIBLE" not in codes(reasons)
    # Cohort text present but unparseable, and not unrestricted, is an uncertainty.
    job2 = make_confirmed_job("hangzhou_ai_app", cohort_years=[], graduation_cohort_text="应届生")
    status2, reasons2 = run_eligibility(job2, config.user_facts, today, evidence=config.evidence)
    assert status2 == "UNCERTAIN" and "COHORT_TEXT_UNPARSEABLE" in codes(reasons2)


def test_preferred_skill_gap_is_soft_flag_not_fail(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", required_skills=["Python"], preferred_skills=["Kubernetes", "Rust"])
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "LIKELY_ELIGIBLE"
    gap = next(r for r in reasons if r.code == "PREFERRED_SKILL_GAPS")
    assert "Kubernetes" in gap.detail and "Rust" in gap.detail
    assert "REQUIRED_SKILL_GAPS" not in codes(reasons)


def test_required_skill_gap_is_soft_flag_not_fail(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", required_skills=["Rust", "Python"], preferred_skills=[])
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "LIKELY_ELIGIBLE"
    gap = next(r for r in reasons if r.code == "REQUIRED_SKILL_GAPS")
    assert gap.detail == "no evidence for: Rust"


def test_no_flags_is_eligible(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", required_skills=["Python"], preferred_skills=[])
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "ELIGIBLE" and reasons == []


def test_native_chinese_requirement_is_soft_flag(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", required_skills=["Python"], preferred_skills=[], chinese_required_level="native")
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "LIKELY_ELIGIBLE"
    assert codes(reasons) == ["CHINESE_LEVEL_ABOVE_STATED"]
    job2 = make_confirmed_job("hangzhou_ai_app", required_skills=["Python"], preferred_skills=[], chinese_required_level="fluent")
    status2, reasons2 = run_eligibility(job2, config.user_facts, today, evidence=config.evidence)
    assert status2 == "UNCERTAIN" and codes(reasons2) == ["CHINESE_LEVEL_REVIEW"]


def test_nationality_silence_is_not_a_restriction(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app")
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status != "INELIGIBLE"
    assert not any(r.field == "nationality_or_work_auth_restriction" for r in reasons)


def test_explicit_prc_only_restriction_fails(make_confirmed_job, config, today):
    for text in ("仅限中国籍", "PRC nationals only", "Chinese citizens only"):
        job = make_confirmed_job("hangzhou_ai_app", nationality_or_work_auth_restriction=text)
        status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
        assert status == "INELIGIBLE", text
        reason = next(r for r in reasons if r.code == "EXPLICIT_NATIONALITY_RESTRICTION")
        assert text in reason.detail
    for text in ("不提供签证支持", "no visa sponsorship", "must already be authorised to work in China"):
        job = make_confirmed_job("hangzhou_ai_app", nationality_or_work_auth_restriction=text)
        status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
        assert status == "INELIGIBLE", text
        assert "EXPLICIT_WORK_AUTHORIZATION_RESTRICTION" in codes(reasons)
    # Restriction text that matches no deterministic pattern is a review flag, not a fail.
    job = make_confirmed_job("hangzhou_ai_app", nationality_or_work_auth_restriction="需有中国工作经验")
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "UNCERTAIN" and "RESTRICTION_TEXT_PRESENT_REVIEW" in codes(reasons)


def test_deadline_passed_fails(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", deadline="2026-09-08")
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "INELIGIBLE"
    reason = next(r for r in reasons if r.code == "DEADLINE_PASSED")
    assert "2026-09-08" in reason.detail and "2026-09-09" in reason.detail
    job2 = make_confirmed_job("hangzhou_ai_app", deadline="2026-09-09")
    status2, reasons2 = run_eligibility(job2, config.user_facts, today, evidence=config.evidence)
    assert "DEADLINE_PASSED" not in codes(reasons2)


def test_role_closed_and_experience_and_days_flags(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", role_closed=True, days_per_week_min=6, required_skills=["Python", "3年经验"])
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "INELIGIBLE"
    assert {"ROLE_CLOSED", "DAYS_PER_WEEK_HIGH", "EXPERIENCE_YEARS_ASKED"} <= set(codes(reasons))


def test_skill_matching_is_deterministic(config):
    assert "EV_MOLARDATA_CV" in skill_matches("Python", config.evidence)
    assert "EV_MOLARDATA_CV" in skill_matches("RAG检索链路与Prompt工程", config.evidence)
    assert "EV_SUTD_COURSEWORK" in skill_matches("network-security", config.evidence)
    assert skill_matches("Rust", config.evidence) == []
    assert skill_matches("C", config.evidence) == ["EV_SUTD_COURSEWORK"]


def test_unparseable_user_cohort_is_uncertain_not_ineligible(make_confirmed_job, config, today):
    facts = config.user_facts.model_copy(deep=True, update={"graduation_cohort": "final year"})
    job = make_confirmed_job("hangzhou_ai_app")
    status, reasons = run_eligibility(job, facts, today, evidence=config.evidence)
    assert status == "UNCERTAIN"
    assert "USER_COHORT_UNPARSEABLE" in codes(reasons) and "GRADUATION_COHORT_INELIGIBLE" not in codes(reasons)


def test_open_ended_cohort_includes_later_years(make_confirmed_job, config, today):
    for text in ("2027届及以后", "2027届以后毕业", "Class of 2027 or later"):
        job = make_confirmed_job("hangzhou_ai_app", cohort_years=[2027], graduation_cohort_text=text)
        status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
        assert "GRADUATION_COHORT_INELIGIBLE" not in codes(reasons), text
        assert status != "INELIGIBLE", text


def test_open_ended_cohort_starting_after_the_user_still_fails(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", cohort_years=[2029], graduation_cohort_text="2029届及以后")
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "INELIGIBLE" and "GRADUATION_COHORT_INELIGIBLE" in codes(reasons)


def test_preferred_cohort_is_a_soft_flag(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", cohort_years=[2027], graduation_cohort_text="2027届优先")
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert "GRADUATION_COHORT_INELIGIBLE" not in codes(reasons)
    assert "GRADUATION_COHORT_PREFERRED" in codes(reasons)
    assert status == "LIKELY_ELIGIBLE"
