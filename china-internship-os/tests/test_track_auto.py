"""The AUTO track: automotive roles whose main work is software or AI."""

from __future__ import annotations

from typer.testing import CliRunner

from internship_os.cli import app
from internship_os.config import load_config
from internship_os.schemas import Track
from internship_os.services import jobs as job_service
from internship_os.tiering import sort_jobs


def test_auto_is_a_track_and_sits_between_ai_and_swe_in_the_example_preferences(config):
    assert Track("AUTO") is Track.AUTO
    assert config.user_facts.internship.track_preference == [Track.AI, Track.AUTO, Track.SWE, Track.other]


def test_config_accepts_auto_anywhere_in_track_preference(project_root):
    with open(project_root / "n.log", "w") as fh:
        load_config(project_root, notice_stream=fh)  # creates user_facts.yaml from the example
    uf = project_root / "config" / "user_facts.yaml"
    uf.write_text(
        uf.read_text(encoding="utf-8").replace("track_preference: [AI, AUTO, SWE, other]", "track_preference: [AUTO, AI, SWE, other]"),
        encoding="utf-8",
    )
    with open(project_root / "n.log", "w") as fh:
        cfg = load_config(project_root, notice_stream=fh)
    assert cfg.user_facts.internship.track_preference[0] == Track.AUTO


def test_job_list_filters_by_the_auto_track(make_confirmed_job, engine, project_root, monkeypatch):
    make_confirmed_job("hangzhou_ai_app")  # track AI
    make_confirmed_job("hangzhou_ai_app", track_guess="AUTO", title_zh="车载感知软件实习生", title_en="Vehicle Perception Software Intern")
    monkeypatch.setenv("COLUMNS", "200")  # Rich truncates table cells at its 80-column fallback under CliRunner
    result = CliRunner().invoke(app, ["job", "list", "--track", "AUTO"])
    assert result.exit_code == 0, result.output
    assert "1 job(s)" in result.output and "车载感知软件实习生" in result.output
    assert "AI应用开发实习生" not in result.output
    assert CliRunner().invoke(app, ["job", "list", "--track", "bogus"]).exit_code == 2


def test_web_job_list_filters_by_auto(session, make_confirmed_job, config):
    make_confirmed_job("hangzhou_ai_app")
    auto = make_confirmed_job("hangzhou_ai_app", track_guess="AUTO", title_zh="车载感知软件实习生")
    assert [j.id for j in job_service.list_jobs(session, config, track="AUTO")] == [auto.id]


def test_auto_sorts_between_ai_and_swe_within_a_tier(session, make_confirmed_job, config):
    jobs = []
    for track in ("SWE", "AUTO", "AI"):  # created in reverse preference order, so ids cannot explain the result
        job = make_confirmed_job("hangzhou_ai_app", yes_status="willing", host_type="startup", track_guess=track, deadline="2026-10-30")
        job.eligibility, job.fit, job.quality, job.tier = "ELIGIBLE", "ok", "strong", "T1"
        jobs.append(job)
    session.commit()
    assert [j.track for j in sort_jobs(jobs, config.user_facts)] == ["AI", "AUTO", "SWE"]
