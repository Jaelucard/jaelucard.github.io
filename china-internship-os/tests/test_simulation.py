"""The lead-scan simulation under pytest: the scenarios of tests/sim_scenarios.py against the repo
fixtures (temporary root and database, fake LLM, no network), with today pinned to 2026-10-01.

``scripts/simulate.py`` runs the same scenarios in one temporary root and prints the result table.
"""

from __future__ import annotations

import difflib
import itertools
from datetime import date
from pathlib import Path

import pytest

from internship_os import capture as capture_mod
from internship_os import cli as cli_mod
from internship_os.capture import NEAR_MATCH_THRESHOLD, normalise_company
from internship_os.config import load_config
from internship_os.models import Job
from tests import sim_scenarios as sim

TODAY = sim.TODAY


@pytest.fixture
def today() -> date:
    return TODAY


@pytest.fixture
def config(project_root: Path):
    """The repo's config fixture with the simulation's user_facts.yaml written first."""
    sim.write_user_facts(project_root / "config")
    with open(project_root / "notice.log", "w") as fh:
        return load_config(project_root, notice_stream=fh)


@pytest.fixture
def sim_llm(fake_llm):
    """The fake LLM answers extract_job with the selected scenario's extraction."""
    fake_llm["extract_job"] = sim.fake_extract_job
    yield
    sim.set_current(None)


@pytest.fixture
def cli_today(monkeypatch: pytest.MonkeyPatch, today: date):
    monkeypatch.setattr(cli_mod, "today_value", lambda: today)


@pytest.fixture
def fake_web(monkeypatch: pytest.MonkeyPatch) -> sim.FakeWeb:
    web = sim.FakeWeb()
    monkeypatch.setattr(capture_mod.httpx, "get", web.get)
    return web


def _describe_failure(row: sim.Row) -> str:
    text = f"{row.id}: {'; '.join(row.mismatches) or row.actual} (where: {row.where})"
    return f"{text}; diagnosis: {row.diagnosis}" if row.diagnosis else text


def _assert_rows(rows: list[sim.Row]) -> None:
    failed = [r for r in rows if r.result == "FAIL"]
    assert not failed, "\n".join(_describe_failure(r) for r in failed)


def _confirmed(session, config, today, scenario_id: str) -> Job:
    outcome = sim.run_scenario(session, config, today, sim.SCENARIO_BY_ID[scenario_id])
    return session.get(Job, outcome.job_id)


# --------------------------------------------------------------------------------------
# Scenario data
# --------------------------------------------------------------------------------------


def test_the_posting_builder_reproduces_the_base_fixture():
    built = sim.posting(sim.BASE_COMPANY, "AI应用开发实习生")
    assert built.strip() == sim.BASE_JD_FILE.read_text(encoding="utf-8").strip()


def test_every_source_span_is_verbatim_in_its_posting():
    for scenario in sim.ALL_SCENARIOS:
        data = scenario.extraction()
        for name, (value, span) in scenario.overrides.items():
            assert data[name] == {"value": value, "confirmed": False, "source_span": span}, (scenario.id, name)
            assert span is None or span in scenario.jd, (scenario.id, name)


def test_scenario_companies_are_distinct_and_never_near_matches():
    names = {s.id: normalise_company(s.company) for s in sim.ALL_SCENARIOS}
    assert len(set(names.values())) == len(names)
    for (a_id, a), (b_id, b) in itertools.combinations(names.items(), 2):
        assert difflib.SequenceMatcher(None, a, b).ratio() < NEAR_MATCH_THRESHOLD, (a_id, b_id)


def test_the_simulation_user_facts(config):
    facts = config.user_facts
    assert facts.graduation_cohort == "2028届" and facts.expected_graduation == "2028-05"
    assert facts.mandarin_level == "professional_working_non_native"
    assert facts.internship.intended_start == date(2027, 2, 15)
    assert facts.internship.latest_end == date(2027, 8, 31)
    assert (facts.internship.min_months, facts.internship.max_months) == (4, 6)
    assert [t.value for t in facts.internship.track_preference] == ["AI", "AUTO", "SWE", "other"]
    assert [h.value for h in facts.internship.host_type_preference] == ["startup", "subsidiary", "large", "mnc", "unknown"]
    assert facts.internship.offer_deadline_personal == date(2026, 12, 4)


# --------------------------------------------------------------------------------------
# Parts A and B (P01-P03): one test per scenario through capture, confirmation and the checks
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", sim.SCENARIOS, ids=[s.id for s in sim.SCENARIOS])
def test_scenario(scenario: sim.Scenario, session, config, today, sim_llm):
    outcome = sim.run_scenario(session, config, today, scenario)
    row = sim.scenario_row(scenario, outcome)
    if scenario.known_failure:
        # The spec's literal expectation, which the product does not meet today (see the diagnosis
        # and the FAIL row of scripts/simulate.py). Exactly that mismatch is tolerated: any other
        # mismatch is a regression, and a passing row means the known failure is stale.
        assert row.mismatches, f"{scenario.id} passes now: drop its known_failure"
        assert row.mismatches == [scenario.known_failure], _describe_failure(row)
        pytest.xfail(f"{scenario.known_failure}; {scenario.diagnosis}")
    _assert_rows([row])


def test_agreed_dates_survive_recompute(session, config, today, sim_llm):
    job = _confirmed(session, config, today, "S01")
    _assert_rows(sim.run_agreed_dates(session, config, today, job))


# --------------------------------------------------------------------------------------
# Part C: ranking
# --------------------------------------------------------------------------------------


def test_ranking_and_the_auto_track_filter(session, config, today, sim_llm, cli_today):
    jobs = {sid: _confirmed(session, config, today, sid) for sid in (*sim.RANKED_IDS, "S20")}
    _assert_rows(sim.run_ranking(session, config, today, jobs))


# --------------------------------------------------------------------------------------
# Part D: capture paths and duplicates
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("scenario_id", sim.URL_SCENARIO_IDS)
def test_url_capture_paths(scenario_id: str, fake_web: sim.FakeWeb):
    if scenario_id == "U01" and not sim.SHIXISENG_FIXTURE.exists():
        pytest.skip("fixture missing: tests/fixtures/html/shixiseng_detail.html could not be downloaded (host unreachable)")
    row = sim.run_url_scenario(fake_web, scenario_id)
    if row.result == "SKIP":
        pytest.skip(row.actual)
    _assert_rows([row])


def test_duplicate_captures(session, config, today, sim_llm):
    _assert_rows(sim.run_duplicates(session, config, today))


# --------------------------------------------------------------------------------------
# Part E: CLI and web
# --------------------------------------------------------------------------------------


def test_cli_commands(session, config, today, sim_llm, cli_today):
    for scenario_id in ("S01", "S02", "S13", "S18"):
        _confirmed(session, config, today, scenario_id)
    _assert_rows(sim.run_cli())


def test_web_pages_capture_and_review(client, session, config, today, sim_llm):
    s02 = _confirmed(session, config, today, "S02")
    s13 = _confirmed(session, config, today, "S13")
    _assert_rows(sim.run_web(client, session, config, today, s02, s13))
