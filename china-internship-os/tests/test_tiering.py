from datetime import date

from internship_os.tiering import compute_tier, sort_jobs


def test_ineligible_is_hold():
    assert compute_tier("INELIGIBLE", "LIKELY", "primary", "strong", "strong") == "HOLD"


def test_incompatible_programme_is_hold():
    assert compute_tier("ELIGIBLE", "INCOMPATIBLE", "primary", "strong", "strong") == "HOLD"


def test_out_of_region_city_is_hold(make_confirmed_job):
    assert compute_tier("ELIGIBLE", "LIKELY", "out", "strong", "strong") == "HOLD"
    job = make_confirmed_job("hangzhou_ai_app", city_zh="北京")
    assert job.tier == "HOLD"
    # Programme UNKNOWN alone is not HOLD; unknown city is not HOLD either.
    assert compute_tier("ELIGIBLE", "UNKNOWN", "primary", "unset", "unknown") == "T3"
    assert compute_tier("ELIGIBLE", "LIKELY", "unknown", "strong", "strong") == "T1"


def test_tier_rules_first_match_wins():
    assert compute_tier("LIKELY_ELIGIBLE", "UNKNOWN", "secondary", "ok", "strong") == "T1"
    assert compute_tier("ELIGIBLE", "LIKELY", "primary", "strong", "ok") == "T2"
    assert compute_tier("ELIGIBLE", "LIKELY", "primary", "weak", "strong") == "T2"
    assert compute_tier("ELIGIBLE", "LIKELY", "primary", "strong", "unknown") == "T2"
    assert compute_tier("ELIGIBLE", "LIKELY", "primary", "ok", "ok") == "T3"
    assert compute_tier("UNCERTAIN", "LIKELY", "primary", "strong", "strong") == "T3"
    assert compute_tier("ELIGIBLE", "LIKELY", "primary", "unset", "strong") == "T3"


def test_strong_swe_role_outranks_weak_ai_role(session, make_confirmed_job, config):
    swe = make_confirmed_job("suzhou_backend", yes_status="willing", duration_min_months=4, duration_max_months=6)
    ai = make_confirmed_job("hangzhou_ai_app", yes_status="willing")
    swe.eligibility, swe.quality, swe.fit = "ELIGIBLE", "strong", "ok"
    ai.eligibility, ai.quality, ai.fit = "ELIGIBLE", "weak", "strong"
    for job in (swe, ai):
        job.tier = compute_tier(job.eligibility, job.programme_overall, config.cities.classify(job.city_zh), job.fit, job.quality)
    session.commit()
    assert swe.track == "SWE" and ai.track == "AI"
    assert swe.tier == "T1" and ai.tier == "T3"
    assert [j.id for j in sort_jobs([ai, swe], config.user_facts)] == [swe.id, ai.id]


def test_ai_title_does_not_change_tier(make_confirmed_job, config):
    plain = make_confirmed_job("suzhou_backend", yes_status="willing", title_zh="后端开发实习生")
    fancy = make_confirmed_job("suzhou_backend", yes_status="willing", title_zh="AI大模型全栈实习生", title_en="AI Engineer Intern")
    for job in (plain, fancy):
        job.eligibility, job.fit, job.quality = "ELIGIBLE", "ok", "ok"
        job.tier = compute_tier(job.eligibility, job.programme_overall, config.cities.classify(job.city_zh), job.fit, job.quality)
    assert plain.tier == fancy.tier == "T3"


def test_research_role_master_required_is_hold_regardless_of_title(make_confirmed_job):
    job = make_confirmed_job("shanghai_llm_algorithm", yes_status="willing", title_zh="软件开发实习生", title_en="Software Engineer Intern", track_guess="SWE")
    assert job.eligibility == "INELIGIBLE"
    assert job.tier == "HOLD"
    job.fit, job.quality = "strong", "strong"
    assert compute_tier(job.eligibility, job.programme_overall, "primary", job.fit, job.quality) == "HOLD"


def test_within_tier_sort_uses_deadline_then_host_type_then_track(session, make_confirmed_job, config):
    def build(name, deadline, host_type, track):
        job = make_confirmed_job(name, yes_status="willing", host_type=host_type, deadline=deadline, track_guess=track)
        job.eligibility, job.fit, job.quality, job.tier = "ELIGIBLE", "ok", "strong", "T1"
        return job

    late_startup_ai = build("hangzhou_ai_app", "2026-10-30", "startup", "AI")
    early_large_swe = build("hangzhou_ai_app", "2026-10-01", "large", "SWE")
    no_deadline_startup_ai = build("hangzhou_ai_app", None, "startup", "AI")
    late_startup_swe = build("hangzhou_ai_app", "2026-10-30", "startup", "SWE")
    late_large_ai = build("hangzhou_ai_app", "2026-10-30", "large", "AI")
    session.commit()
    ordered = sort_jobs(
        [no_deadline_startup_ai, late_large_ai, late_startup_swe, late_startup_ai, early_large_swe],
        config.user_facts,
    )
    assert [j.id for j in ordered] == [
        early_large_swe.id,      # earliest deadline wins over host type and track
        late_startup_ai.id,      # same deadline: startup before large; AI before SWE
        late_startup_swe.id,
        late_large_ai.id,
        no_deadline_startup_ai.id,  # null deadline last
    ]
    # Tier dominates: a T2 job with the earliest deadline still sorts after every T1.
    t2 = build("hangzhou_ai_app", "2026-09-10", "startup", "AI")
    t2.tier = "T2"
    assert sort_jobs([t2, no_deadline_startup_ai], config.user_facts)[0].id == no_deadline_startup_ai.id
    assert late_startup_ai.deadline == date(2026, 10, 30)
