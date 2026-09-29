import pytest

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


def test_summer_programme_is_a_soft_flag(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", internship_type="暑期实习")
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    flag = next(r for r in reasons if r.code == "SUMMER_PROGRAMME_TIMING")
    assert flag.field == "internship_type" and status in ("LIKELY_ELIGIBLE", "UNCERTAIN")


def test_daily_internship_has_no_summer_flag(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app")  # 日常实习
    _, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert "SUMMER_PROGRAMME_TIMING" not in codes(reasons)


@pytest.mark.parametrize(
    ("text", "years"),
    [
        ("2026届、2027届（2028届及以后毕业生请勿投递）", [2026, 2027]),
        ("仅限2026届，2027届及以后不考虑", [2026]),
        ("2026届毕业生，入职以后表现优秀可转正", [2026]),
        ("2026届毕业生，毕业之后可留用", [2026]),
        ("2026 graduates only; available from June onwards", [2026]),
        ("2026届本科，计算机相关专业优先", [2026]),
        ("2026届，985/211院校优先", [2026]),
        ("2029届及以后", [2029]),
        ("2026届及以前", [2026]),
    ],
)
def test_cohort_wording_that_excludes_the_user_still_hard_fails(make_confirmed_job, config, today, text, years):
    job = make_confirmed_job("hangzhou_ai_app", cohort_years=years, graduation_cohort_text=text)
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "INELIGIBLE" and "GRADUATION_COHORT_INELIGIBLE" in codes(reasons), text


def test_open_ended_year_is_the_one_attached_to_the_wording(make_confirmed_job, config, today):
    # 2025 is listed, but "及以后" is attached to 2029, which is after the user's 2028 cohort.
    job = make_confirmed_job("hangzhou_ai_app", cohort_years=[2025, 2029], graduation_cohort_text="2025届、2029届及以后")
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert "GRADUATION_COHORT_INELIGIBLE" in codes(reasons)


# --------------------------------------------------------------------------------------
# Student-status restrictions (postings limited to students of mainland Chinese universities)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["仅限国内高校在读", "限国内高校在读", "仅接受国内院校", "大陆户籍", "中国大陆户籍"])
def test_student_status_restriction_hard_fails(make_confirmed_job, config, today, text):
    job = make_confirmed_job("hangzhou_ai_app", nationality_or_work_auth_restriction=text)
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "INELIGIBLE", text
    reason = next(r for r in reasons if r.code == "EXPLICIT_STUDENT_STATUS_RESTRICTION")
    assert reason.field == "nationality_or_work_auth_restriction" and text in reason.detail
    assert not {"STUDENT_STATUS_REVIEW", "RESTRICTION_TEXT_PRESENT_REVIEW"} & set(codes(reasons))


@pytest.mark.parametrize("text", ["需学信网可查", "国内高校优先", "中国大陆院校优先", "需国内学籍"])
def test_softer_student_status_wording_is_a_review_flag(make_confirmed_job, config, today, text):
    job = make_confirmed_job("hangzhou_ai_app", nationality_or_work_auth_restriction=text)
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "UNCERTAIN", text
    reason = next(r for r in reasons if r.code == "STUDENT_STATUS_REVIEW")
    assert reason.field == "nationality_or_work_auth_restriction" and text in reason.detail
    assert not {
        "EXPLICIT_STUDENT_STATUS_RESTRICTION",
        "EXPLICIT_NATIONALITY_RESTRICTION",
        "RESTRICTION_TEXT_PRESENT_REVIEW",
    } & set(codes(reasons))


def test_chinese_nationality_preferred_is_not_a_hard_fail(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", nationality_or_work_auth_restriction="中国国籍优先")
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status != "INELIGIBLE"
    assert "EXPLICIT_NATIONALITY_RESTRICTION" not in codes(reasons)
    # The same words without the preference still hard-fail.
    job2 = make_confirmed_job("hangzhou_ai_app", nationality_or_work_auth_restriction="要求中国国籍")
    status2, reasons2 = run_eligibility(job2, config.user_facts, today, evidence=config.evidence)
    assert status2 == "INELIGIBLE" and "EXPLICIT_NATIONALITY_RESTRICTION" in codes(reasons2)


def test_full_time_student_wording_matches_no_student_pattern(make_confirmed_job, config, today):
    # The user is a full-time student: 全日制在校生 on its own is not a restriction.
    job = make_confirmed_job("hangzhou_ai_app", nationality_or_work_auth_restriction="全日制在校生")
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status != "INELIGIBLE"
    assert not {
        "EXPLICIT_STUDENT_STATUS_RESTRICTION",
        "STUDENT_STATUS_REVIEW",
        "EXPLICIT_NATIONALITY_RESTRICTION",
        "EXPLICIT_WORK_AUTHORIZATION_RESTRICTION",
    } & set(codes(reasons))


@pytest.mark.parametrize("text", ["非大陆户籍亦可", "大陆户籍不限", "不限国内高校在读", "不仅限国内高校", "非中国大陆居民也可"])
def test_negated_student_status_wording_is_not_a_hard_fail(make_confirmed_job, config, today, text):
    # Wording that says the posting is not limited to mainland students must not close the job.
    job = make_confirmed_job("hangzhou_ai_app", nationality_or_work_auth_restriction=text)
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status != "INELIGIBLE", text
    assert "EXPLICIT_STUDENT_STATUS_RESTRICTION" not in codes(reasons)


# --------------------------------------------------------------------------------------
# Fee, non-engineering work and unpaid postings (confirmed extracted fields, never Jev)
# --------------------------------------------------------------------------------------

NO_FLAGS = {"required_skills": ["Python"], "preferred_skills": []}  # the fixture variant with no reasons at all


def test_fee_required_is_ineligible(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", pays_fee=True, **NO_FLAGS)
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "INELIGIBLE" and codes(reasons) == ["FEE_REQUIRED"]
    assert reasons[0].field == "pays_fee"


def test_mostly_sales_or_annotation_is_a_soft_flag(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", mostly_sales=True, **NO_FLAGS)
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "LIKELY_ELIGIBLE" and codes(reasons) == ["NOT_ENGINEERING_WORK"]
    assert reasons[0].field == "mostly_sales"
    job2 = make_confirmed_job("hangzhou_ai_app", mostly_annotation=True, mostly_sales=True, **NO_FLAGS)
    _, reasons2 = run_eligibility(job2, config.user_facts, today, evidence=config.evidence)
    assert [(r.code, r.field) for r in reasons2] == [
        ("NOT_ENGINEERING_WORK", "mostly_annotation"),
        ("NOT_ENGINEERING_WORK", "mostly_sales"),
    ]
    # On the plain fixture (which already carries skill-gap flags) the job stays LIKELY_ELIGIBLE.
    job3 = make_confirmed_job("hangzhou_ai_app", mostly_sales=True)
    status3, _ = run_eligibility(job3, config.user_facts, today, evidence=config.evidence)
    assert status3 == "LIKELY_ELIGIBLE"


@pytest.mark.parametrize("text", ["无薪", "不提供实习工资", "不提供薪资", "不提供补贴", "志愿者岗位", "Unpaid internship"])
def test_unpaid_wording_is_a_soft_flag(make_confirmed_job, config, today, text):
    job = make_confirmed_job("hangzhou_ai_app", salary_text=text, **NO_FLAGS)
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "LIKELY_ELIGIBLE" and codes(reasons) == ["UNPAID"], text
    assert reasons[0].field == "salary_text" and text in reasons[0].detail


@pytest.mark.parametrize("text", ["薪资面议", "面议", "300-400元/天", "有薪实习", None])
def test_negotiable_or_paid_salary_adds_nothing(make_confirmed_job, config, today, text):
    job = make_confirmed_job("hangzhou_ai_app", salary_text=text, **NO_FLAGS)
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "ELIGIBLE" and reasons == [], text


# --------------------------------------------------------------------------------------
# work_mode: remote-only postings
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["onsite", "hybrid", "not_stated", None])
def test_non_remote_work_mode_adds_nothing(make_confirmed_job, config, today, mode):
    job = make_confirmed_job("hangzhou_ai_app", work_mode=mode, **NO_FLAGS)
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "ELIGIBLE" and reasons == [], mode


def test_remote_only_posting_is_a_soft_flag(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", work_mode="remote", **NO_FLAGS)
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "LIKELY_ELIGIBLE" and codes(reasons) == ["REMOTE_ONLY"]
    assert reasons[0].field == "work_mode"


def test_unconfirmed_work_mode_alone_gives_not_run(make_confirmed_job, config, today):
    job = make_confirmed_job("hangzhou_ai_app", run=False)
    data = dict(job.extracted)
    data["work_mode"] = {**data["work_mode"], "confirmed": False}
    job.extracted = data
    status, reasons = run_eligibility(job, config.user_facts, today, evidence=config.evidence)
    assert status == "NOT_RUN"
    assert codes(reasons) == ["UNCONFIRMED_FIELDS"]
    assert "work_mode" in reasons[0].detail
