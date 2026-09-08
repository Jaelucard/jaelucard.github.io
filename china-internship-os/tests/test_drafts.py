import json
from datetime import date

import pytest

from internship_os.drafts import (
    DraftError,
    Statement,
    generate_bullets,
    generate_interview_prep,
    generate_messages,
    pack_dir,
    strip_comments,
    validate_bullet,
    validate_statements,
    write_pack,
)


def stmt(text, kind="user_claim", refs=None):
    return {"text": text, "kind": kind, "source_refs": refs or []}


def messages_json(**overrides):
    base = {
        "recruiter_zh": {"statements": [
            stmt("您好，我是新加坡科技设计大学的学生，想申请贵司的实习岗位。", "nonclaim"),
            stmt("我在MolarData做过计算机视觉实习，训练过用于RAG识别的模型。", refs=["EV_MOLARDATA_CV"]),
            stmt("中文可作为工作语言（非母语）。", refs=["user_facts.mandarin_claim_zh"]),
            stmt("期待您的回复。", "nonclaim"),
        ]},
        "recruiter_en": {"statements": [
            stmt("Hello, I am a student at SUTD applying for this internship.", refs=["user_facts.university"]),
            stmt("I built a live F1 timing dashboard using OpenF1 live data.", refs=["EV_F1_DASHBOARD"]),
            stmt("I have professional working proficiency in Mandarin (non-native).", refs=["user_facts.mandarin_claim_en"]),
            stmt("Thank you for your time.", "nonclaim"),
        ]},
        "referral_zh": {"statements": [stmt("您好，请问方便帮忙内推吗？", "nonclaim")]},
        "referral_en": {"statements": [stmt("Would you be open to referring me for this role?", "nonclaim")]},
    }
    base.update(overrides)
    return json.dumps(base, ensure_ascii=False)


def yes_json(zh_statements=None, en_statements=None):
    zh = zh_statements or [
        stmt("您好，我想介绍一下新中青年实习交流计划的安排。", "nonclaim"),
        stmt("实习最长可达6个月。", "programme_fact", ["YES_MAX_DURATION"]),
    ]
    en = en_statements or [
        stmt("The host provides a stipend, a supervisor and feedback to Business China after the stint.", "programme_fact", ["HOST_OBLIGATIONS"]),
    ]
    return json.dumps({"zh": {"statements": zh}, "en": {"statements": en}}, ensure_ascii=False)


@pytest.fixture
def confirmed_job(make_confirmed_job):
    return make_confirmed_job("hangzhou_ai_app", yes_status="willing")


# --------------------------------------------------------------------------------------
# Bullets
# --------------------------------------------------------------------------------------


def test_bullets_without_evidence_id_are_dropped_and_reported(confirmed_job, config, fake_llm):
    fake_llm["tailor_bullets"] = json.dumps({"bullets": [
        "Built a live F1 timing dashboard with track map and team radio using OpenF1 live data [EV_F1_DASHBOARD]",
        "Trained vision models for RAG-based recognition during a computer vision internship",
        "Designed a metamorphic-testing tool for LLM evaluation [EV_NOT_REAL]",
        "Placed first on a Kaggle private leaderboard [EV_KAGGLE_GENAI_DETECTION] with classical ML",
        "Did two things [EV_F1_DASHBOARD] [EV_LLM_EVALUATOR]",
    ]}, ensure_ascii=False)
    result = generate_bullets(confirmed_job, config)
    assert result.kept == [
        "Built a live F1 timing dashboard with track map and team radio using OpenF1 live data [EV_F1_DASHBOARD]"
    ]
    reasons = {r.text: r.reason for r in result.rejected}
    assert len(reasons) == 4
    assert "exactly one" in reasons["Trained vision models for RAG-based recognition during a computer vision internship"]
    assert "unknown evidence id EV_NOT_REAL" in reasons["Designed a metamorphic-testing tool for LLM evaluation [EV_NOT_REAL]"]
    assert "must end with" in reasons["Placed first on a Kaggle private leaderboard [EV_KAGGLE_GENAI_DETECTION] with classical ML"]
    content = (result.directory / "bullets.md").read_text(encoding="utf-8")
    assert "[EV_F1_DASHBOARD]" in content and "EV_NOT_REAL" in content.split("## Dropped bullets")[1]
    assert content.split("## Dropped bullets")[0].count("\n- ") == 1


def test_mindef_bullet_with_digit_is_dropped(confirmed_job, config, fake_llm):
    fake_llm["tailor_bullets"] = json.dumps({"bullets": [
        "Maintained a service-injury database for 2 years and automated reports [EV_MINDEF_DB]",
        "Maintained a service-injury database and built an Excel VBA workflow to support it [EV_MINDEF_DB]",
        "Handled 3,000 records in the database [EV_MINDEF_DB]",
    ]})
    result = generate_bullets(confirmed_job, config)
    assert result.kept == ["Maintained a service-injury database and built an Excel VBA workflow to support it [EV_MINDEF_DB]"]
    assert [r.reason for r in result.rejected][0] == "EV_MINDEF_DB bullets may not contain any digit"
    assert validate_bullet("Built a dashboard in 2026 [EV_F1_DASHBOARD]", config) is None  # digits fine elsewhere
    assert validate_bullet("Native Mandarin speaker who built tools [EV_LANGUAGES]", config) == "claims native Mandarin"


# --------------------------------------------------------------------------------------
# Messages
# --------------------------------------------------------------------------------------


def test_messages_never_claim_native_mandarin(confirmed_job, config, fake_llm, today):
    fake_llm["recruiter_message"] = messages_json(
        recruiter_zh={"statements": [
            stmt("您好，我想申请贵司的实习岗位。", "nonclaim"),
            stmt("我的母语是中文，沟通无障碍。", refs=["user_facts.mandarin_claim_zh"]),
            stmt("中文可作为工作语言（非母语）。", refs=["user_facts.mandarin_claim_zh"]),
        ]},
        recruiter_en={"statements": [
            stmt("I am a native Mandarin speaker.", refs=["user_facts.mandarin_claim_en"]),
            stmt("I am fluent in Chinese.", refs=["EV_LANGUAGES"]),
            stmt("I have professional working proficiency in Mandarin (non-native).", refs=["user_facts.mandarin_claim_en"]),
        ]},
    )
    fake_llm["yes_explanation"] = yes_json()
    result = generate_messages(confirmed_job, config, today)
    zh = strip_comments(result.sections["recruiter_zh"])
    en = strip_comments(result.sections["recruiter_en"])
    assert "母语是" not in zh and "中文可作为工作语言（非母语）" in zh
    assert "native Mandarin speaker" not in en and "fluent in Chinese" not in en
    assert "professional working proficiency in Mandarin (non-native)" in en
    reasons = [r.reason for r in result.rejected]
    assert reasons.count("claims native Mandarin") == 2
    assert any("verbatim" in r for r in reasons)
    content = (result.directory / "messages.md").read_text(encoding="utf-8")
    assert "母语是" not in content.split("## Refused statements")[0]
    assert "<!-- user_facts.mandarin_claim_zh -->" in content


def test_yes_explanation_uses_only_verified_or_user_confirmed_constraints(confirmed_job, config, fake_llm, today):
    seen = {}

    def yes_provider(prompt):
        seen["prompt"] = prompt
        return yes_json(
            zh_statements=[
                stmt("实习最长可达6个月。", "programme_fact", ["YES_MAX_DURATION"]),
                stmt("LOC通常需要14天。", "programme_fact", ["LOC_LEAD_TIME"]),
                stmt("可申请Global Ready Talent资助。", "programme_fact", ["FUNDING_OPTIONS"]),
                stmt("签证由学校办理。", "programme_fact", []),
            ],
            en_statements=[
                stmt("Host companies are onboarded by SUTD and Business China between themselves.", "programme_fact", ["HOST_ONBOARDING_ROUTE"]),
                stmt("The intern applies for the Z visa at the Chinese Embassy in Singapore.", "programme_fact", ["Z_VISA_PROCESS_CHAIN"]),
                stmt("Happy to connect you with my school for the paperwork.", "nonclaim"),
            ],
        )

    fake_llm["recruiter_message"] = messages_json()
    fake_llm["yes_explanation"] = yes_provider
    result = generate_messages(confirmed_job, config, today)
    prompt = seen["prompt"]
    for cid in ("HOST_OBLIGATIONS", "Z_VISA_PROCESS_CHAIN", "HOST_ONBOARDING_ROUTE", "YES_MAX_DURATION"):
        assert config.constraints.require(cid).statement in prompt
    for cid in ("LOC_LEAD_TIME", "FUNDING_OPTIONS", "Z_VISA_EMBASSY_LEAD_TIME"):
        assert config.constraints.require(cid).statement not in prompt
    zh = strip_comments(result.sections["yes_zh"])
    assert "6个月" in zh and "14天" not in zh and "Global Ready Talent" not in zh and "签证由学校办理" not in zh
    assert "<!-- HOST_ONBOARDING_ROUTE -->" in result.sections["yes_en"]
    reasons = {r.text: r.reason for r in result.rejected}
    assert "LOC_LEAD_TIME" in reasons["LOC通常需要14天。"]
    assert "FUNDING_OPTIONS" in reasons["可申请Global Ready Talent资助。"]
    assert "no source_refs" in reasons["签证由学校办理。"]

    # A constraint that is neither VERIFIED nor USER_CONFIRMED is withheld from the prompt.
    from internship_os.config import AppConfig
    constraints = config.constraints.model_copy(deep=True)
    constraints.require("HOST_ONBOARDING_ROUTE").status = "UNVERIFIED"
    cfg2 = AppConfig(root=config.root, user_facts=config.user_facts, constraints=constraints, evidence=config.evidence, cities=config.cities)
    result2 = generate_messages(confirmed_job, cfg2, today)
    assert config.constraints.require("HOST_ONBOARDING_ROUTE").statement not in seen["prompt"]
    assert "HOST_ONBOARDING_ROUTE" in {r.reason for r in result2.rejected}.__str__()


def test_unsourced_user_claims_are_refused_and_reported(config):
    report = validate_statements(
        [
            Statement(text="I led a team of ten engineers.", kind="user_claim"),
            Statement(text="I studied at SUTD.", kind="user_claim", source_refs=["user_facts.university"]),
            Statement(text="I have a PhD.", kind="user_claim", source_refs=["user_facts.phd"]),
            Statement(text="I won a prize.", kind="user_claim", source_refs=["EV_UNKNOWN"]),
            Statement(text="Thanks for reading.", kind="nonclaim"),
        ],
        config,
    )
    assert [s.text for s in report.kept] == ["I studied at SUTD.", "Thanks for reading."]
    lines = [r.line() for r in report.rejected]
    assert lines[0].startswith("Refused unsourced claim: I led a team of ten engineers.")
    assert "user_facts.phd" in lines[1] and "EV_UNKNOWN" in lines[2]


def test_message_length_limit_retries_once_then_reports(confirmed_job, config, fake_llm, today):
    calls = []
    too_long = "我" * 160

    def recruiter(prompt):
        calls.append(prompt)
        return messages_json(recruiter_zh={"statements": [stmt(too_long, "nonclaim")]})

    fake_llm["recruiter_message"] = recruiter
    fake_llm["yes_explanation"] = yes_json()
    result = generate_messages(confirmed_job, config, today)
    assert len(calls) == 2
    assert "rejected" in calls[1] and "160" in calls[1]
    assert "recruiter_zh" not in result.sections
    assert "150" in result.failures["recruiter_zh"]
    assert set(result.sections) == {"recruiter_en", "referral_zh", "referral_en", "yes_zh", "yes_en"}
    content = (result.directory / "messages.md").read_text(encoding="utf-8")
    assert "NOT GENERATED" in content.split("## 2.")[0]
    assert too_long not in content


# --------------------------------------------------------------------------------------
# Pack and interview prep
# --------------------------------------------------------------------------------------


def test_pack_files_written_with_sourced_strengths(confirmed_job, config, today, project_root):
    result = write_pack(confirmed_job, config, today)
    assert result.directory == project_root / "packs" / "杭州星河智能科技有限公司--ai应用开发实习生"
    for name in ("job.md", "fit.md", "checklist.md"):
        assert (result.directory / name).exists()
    fit = result.files["fit.md"]
    strengths_block = fit.split("## Strengths to lead with")[1].strip().splitlines()
    assert strengths_block and all(line.rstrip().endswith("]") and "[EV_" in line for line in strengths_block)
    assert "| Python | required | EV_MOLARDATA_CV" in fit
    assert "| PyTorch | preferred | - | yes |" in fit
    assert "CONTRACT MUST BE SIGNED BY 2027-01-10" in result.files["checklist.md"]
    assert result.files["job.md"].rstrip().endswith("```")
    assert "杭州星河智能科技有限公司" in result.files["job.md"]


def test_pack_requires_confirmed_job(capture_fixture, config, today):
    job = capture_fixture("hangzhou_ai_app")
    with pytest.raises(DraftError):
        write_pack(job, config, today)


def test_interview_prep_requires_in_process(session, confirmed_job, config, fake_llm, today):
    from internship_os.pipeline import transition

    fake_llm["interview_prep"] = json.dumps({
        "technical_questions": ["请介绍RAG检索链路的设计。"],
        "behavioural_questions": ["描述一次与算法同学协作的经历。"],
        "evidence_to_rehearse": ["EV_MOLARDATA_CV", "EV_BOGUS", "EV_LLM_EVALUATOR"],
    }, ensure_ascii=False)
    with pytest.raises(DraftError, match="IN_PROCESS"):
        generate_interview_prep(confirmed_job, config)
    transition(session, confirmed_job, "IN_PROCESS", next_action="prepare", due=today, stage="interview 1", note=None, config=config, today=today)
    result = generate_interview_prep(confirmed_job, config)
    assert result.evidence_ids == ["EV_MOLARDATA_CV", "EV_LLM_EVALUATOR"]
    assert [r.text for r in result.rejected] == ["EV_BOGUS"]
    assert (result.directory / "interview-prep.md").read_text(encoding="utf-8").count("EV_BOGUS") == 0
    assert pack_dir(confirmed_job, config.root) == result.directory
