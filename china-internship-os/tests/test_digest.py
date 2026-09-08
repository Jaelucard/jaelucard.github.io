from datetime import date

from typer.testing import CliRunner

from internship_os.cli import app
from internship_os.digest import build_digest, recommended_today
from internship_os.pipeline import transition

TOP = (
    "CONTRACT MUST BE SIGNED BY 2027-01-10 (123 days). "
    "Placeholders in use: Z_VISA_EMBASSY_LEAD_TIME, ENTRY_PERMIT_LEAD_TIME, LOC_LEAD_TIME"
)


def test_digest_top_line_is_contract_deadline(session, config, today):
    lines = build_digest(session, config, today)
    assert lines[0] == TOP
    assert lines[2].startswith("Programme constraint warnings (3)")
    assert "Jobs by tier: T1 0, T2 0, T3 0, HOLD 0, NOT_RUN 0" in lines


def test_digest_cli_begins_with_contract_line(project_root, engine):
    result = CliRunner().invoke(app, ["digest"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("CONTRACT MUST BE SIGNED BY 2027-01-10 (")
    assert "Placeholders in use: Z_VISA_EMBASSY_LEAD_TIME, ENTRY_PERMIT_LEAD_TIME, LOC_LEAD_TIME" in result.output.splitlines()[0]
    result = CliRunner().invoke(app, ["timeline"])
    assert result.exit_code == 0 and result.output.startswith("CONTRACT MUST BE SIGNED BY 2027-01-10 (")
    assert "contract_by" in result.output and "[placeholder]" in result.output


def test_digest_sections_and_recommendations(session, make_confirmed_job, config, today):
    t1 = make_confirmed_job("hangzhou_ai_app", yes_status="willing", deadline="2026-09-12")
    t1.fit, t1.quality, t1.tier = "strong", "strong", "T1"
    t3 = make_confirmed_job("suzhou_backend", yes_status="willing", deadline="2026-09-30")
    t3.next_action_date = date(2026, 9, 1)  # overdue
    hold = make_confirmed_job("shanghai_llm_algorithm")
    assert hold.tier == "HOLD"
    t2_extra = make_confirmed_job("hangzhou_ai_app", yes_status="willing", title_zh="第二个")
    t2_extra.fit, t2_extra.quality, t2_extra.tier = "strong", "ok", "T2"
    t3_extra = make_confirmed_job("hangzhou_ai_app", yes_status="willing", title_zh="第三个")
    t3_extra.tier = "T3"
    closed = make_confirmed_job("hangzhou_ai_app", yes_status="willing", title_zh="已关闭", deadline="2026-09-10")
    session.commit()
    transition(session, closed, "CLOSED", next_action=None, due=None, stage=None, note=None, config=config, today=today)

    picks = recommended_today(list(session.query(type(t1))), config)
    assert [j.id for j in picks] == [t1.id, t2_extra.id, t3.id]  # max 3, tier order, HOLD and terminal excluded

    lines = build_digest(session, config, today)
    text = "\n".join(lines)
    assert lines[0] == TOP
    assert "Jobs by tier: T1 1, T2 1, T3 3, HOLD 1, NOT_RUN 0" in text  # closed job keeps its tier
    assert "Jobs by status: CLOSED 1, DISCOVERED 5" in text
    assert "Deadlines within 7 days (1):" in text and "2026-09-12" in text and "2026-09-10" not in text
    assert "Actions due (5):" in text  # every DISCOVERED job has a next action today or earlier
    assert f"2026-09-01 {t3.id}:" in text
    idx_rec = text.index("Recommended today (3):")
    assert text.index("Actions due") < idx_rec
    assert "[HOLD]" not in text.split("Recommended today")[1]
