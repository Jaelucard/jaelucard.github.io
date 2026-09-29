"""End-to-end simulation of the lead-scan rules against a temporary project root.

Run from the project root:

    .venv/bin/python scripts/simulate.py [--keep] [--live]

The scripted run pushes the postings in tests/sim_scenarios.py through the real capture,
confirmation, eligibility, programme, tiering, recompute, CLI and web paths and compares each
outcome with its expected row. It never touches the real db.sqlite, config/user_facts.yaml, .env
or packs/: a fresh temporary root gets a copy of config/ (without user_facts.yaml), the
simulation's own user_facts.yaml, a decisions.yaml with provider: none and its own database.
IOS_ROOT and IOS_DB_URL point there before any configuration loads, TYPESAFE_API_KEY is removed
from the environment, and the run aborts unless the resolved paths lie inside that root. The LLM
provider is a fake that returns each scenario's own extraction and httpx.get is a fake fed from
tests/fixtures/html, so nothing leaves this machine. Today is fixed at 2026-10-01.

The result table (id | expected | actual | PASS/FAIL) is printed and written to
<temp root>/sim-report.md. Exit code 0 only when every counted row passes; skipped rows are
listed separately. --keep leaves the temporary root in place. --live then runs part F: the real
CLI with the real claude_code provider on two public postings, in a second fresh temporary root,
never confirming what it captures. That spends your Claude subscription and fetches two pages, so
it runs only when asked for.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

TODAY = date(2026, 10, 1)
REPORT_NAME = "sim-report.md"
LIVE_POSTINGS = (
    ("https://www.shixiseng.com/intern/inn_qa5talgymf0o", "shixiseng"),
    ("https://yes.businesschina.org.sg/internship/artificial-intelligence-intern/", "yes_portal"),
)
LIVE_TIMEOUT_SECONDS = 1200  # the CLI itself gives the claude command 900 seconds


# --------------------------------------------------------------------------------------
# Temporary root
# --------------------------------------------------------------------------------------


def populate_temp_root(root: Path) -> None:
    """config/ without user_facts.yaml, decisions.yaml with provider: none, the simulation's user facts."""
    shutil.copytree(REPO / "config", root / "config", ignore=shutil.ignore_patterns("user_facts.yaml", "__pycache__"))
    decisions = root / "config" / "decisions.yaml"
    text = decisions.read_text(encoding="utf-8") if decisions.exists() else ""
    if re.search(r"^provider:", text, flags=re.MULTILINE):
        text = re.sub(r"^provider:.*$", "provider: none", text, count=1, flags=re.MULTILINE)
    else:
        text = "provider: none\n" + text
    decisions.write_text(text, encoding="utf-8")
    from tests.sim_scenarios import write_user_facts

    write_user_facts(root / "config")


def inside(path: Path | str, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(root)
    except ValueError:
        return False
    return True


def guard(config: Any, temp_root: Path, db_url: str, load_decisions: Callable[[Path], Any]) -> None:
    """Abort unless everything the run will read or write is inside ``temp_root``."""
    problems: list[str] = []
    if not inside(config.root, temp_root):
        problems.append(f"project root {config.root} is outside {temp_root}")
    if not inside(config.config_dir, temp_root):
        problems.append(f"config directory {config.config_dir} is outside {temp_root}")
    prefix = "sqlite:///"
    if not db_url.startswith(prefix):
        problems.append(f"database URL {db_url} is not a local SQLite file")
    else:
        db_path = Path(db_url[len(prefix):])
        if not inside(db_path, temp_root):
            problems.append(f"database {db_path} is outside {temp_root}")
        if db_path.resolve() == (REPO / "db.sqlite").resolve():
            problems.append("the database path is the repository's db.sqlite")
    if config.user_facts.internship.latest_end != date(2027, 8, 31):
        problems.append("the loaded user_facts.yaml is not the simulation's (latest_end is not 2027-08-31)")
    if load_decisions(config.root).provider != "none":
        problems.append("decisions.yaml in the temporary root does not say provider: none")
    if os.environ.get("TYPESAFE_API_KEY"):
        problems.append("TYPESAFE_API_KEY is still in the environment")
    if problems:
        print("ABORT: the simulation is not confined to its temporary root:")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(2)


def _blocked(*_args: Any, **_kwargs: Any) -> Any:
    raise RuntimeError("simulation: a real LLM provider was called")


# --------------------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------------------


def _cell(text: str) -> str:
    return " ".join(text.replace("|", "/").split())


def render_report(rows: list[Any], *, title: str, temp_root: Path) -> str:
    counted = [r for r in rows if r.result != "SKIP"]
    skipped = [r for r in rows if r.result == "SKIP"]
    failed = [r for r in counted if r.result == "FAIL"]
    passed = len(counted) - len(failed)
    lines = [
        f"# {title}",
        "",
        f"today = {TODAY.isoformat()}; temp root = {temp_root}",
        "",
        "id | expected | actual | PASS/FAIL",
        "--- | --- | --- | ---",
    ]
    lines += [f"{r.id} | {_cell(r.expected)} | {_cell(r.actual)} | {r.result}" for r in counted]
    if failed:
        lines += ["", "## FAIL rows", ""]
        lines += [
            f"- {r.id}: {'; '.join(r.mismatches) or r.actual} (where: {r.where})"
            + (f"; diagnosis: {r.diagnosis}" if r.diagnosis else "")
            for r in failed
        ]
    if skipped:
        lines += ["", "## SKIP rows (not counted)", ""]
        lines += [f"- {r.id}: {r.expected} -> {r.actual}" for r in skipped]
    lines += ["", f"{passed}/{len(counted)} passed"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------
# The scripted run
# --------------------------------------------------------------------------------------


def run_scripted(keep: bool) -> bool:
    """Every scripted part in one temporary root. Returns True when every counted row passed."""
    temp_root = Path(tempfile.mkdtemp(prefix="ios-sim-")).resolve()
    os.environ["IOS_ROOT"] = str(temp_root)
    os.environ["IOS_DB_URL"] = f"sqlite:///{temp_root / 'db.sqlite'}"
    os.environ.pop("TYPESAFE_API_KEY", None)
    populate_temp_root(temp_root)

    # Imported only now: nothing below may resolve a path before the environment points here.
    from fastapi.testclient import TestClient

    from internship_os import capture as capture_mod
    from internship_os import cli as cli_mod
    from internship_os import llm
    from internship_os.config import load_config
    from internship_os.db import database_url, get_engine, get_session, init_db
    from internship_os.decision_provider import load_decisions
    from internship_os.models import Job
    from internship_os.web import deps
    from internship_os.web.app import create_app
    from tests import sim_scenarios as sim

    config = load_config()
    guard(config, temp_root, database_url(), load_decisions)
    print(f"temp root: {temp_root}")
    print(f"database:  {database_url()}")
    print(f"today:     {TODAY.isoformat()}")

    llm.set_fake_provider(sim.fake_provider)
    llm._claude_code_call = _blocked
    llm._ollama_call = _blocked
    web = sim.FakeWeb()
    capture_mod.httpx.get = web.get
    cli_mod.today_value = lambda: TODAY

    engine = get_engine(database_url())
    init_db(engine)
    session = get_session(engine)
    rows: list[sim.Row] = []
    jobs: dict[str, Job] = {}

    def part(row_ids: tuple[str, ...], where: str, needs: tuple[str, ...], run: Callable[[], list[sim.Row]]) -> None:
        missing = [sid for sid in needs if sid not in jobs]
        if missing:
            for row_id in row_ids:
                rows.append(sim.Row(row_id, "(see the scenario table)", f"not run: scenario {', '.join(missing)} did not produce a job", "FAIL", ["prerequisite scenario failed"], where))
            return
        try:
            rows.extend(run())
        except Exception as exc:  # noqa: BLE001 - one broken part must not hide the rest of the table
            session.rollback()
            for row_id in row_ids:
                rows.append(sim.Row(row_id, "(see the scenario table)", f"error: {type(exc).__name__}: {exc}", "FAIL", [f"{type(exc).__name__}: {exc}"], where))

    try:
        # Parts A and B (P01-P03): capture, confirm like `ios confirm` with 'a', run the checks.
        for scenario in sim.SCENARIOS:
            expected = f"{scenario.summary} -> {scenario.expected.describe()}"
            try:
                outcome = sim.run_scenario(session, config, TODAY, scenario)
            except Exception as exc:  # noqa: BLE001 - report the row, keep going
                session.rollback()
                rows.append(sim.Row(scenario.id, expected, f"error: {type(exc).__name__}: {exc}", "FAIL", [f"{type(exc).__name__}: {exc}"], scenario.where))
                continue
            jobs[scenario.id] = session.get(Job, outcome.job_id)
            rows.append(sim.scenario_row(scenario, outcome))

        # Part B: agreed dates on S01 (the `ios job dates` path) and their survival of recompute.
        part(sim.AGREED_ROW_IDS, sim.WHERE_AGREED, ("S01",), lambda: sim.run_agreed_dates(session, config, TODAY, jobs["S01"]))
        # Part C: ranking.
        part(sim.RANKING_ROW_IDS, sim.WHERE_SORT, (*sim.RANKED_IDS, "S20"), lambda: sim.run_ranking(session, config, TODAY, jobs))
        # Part D: URL capture paths and duplicates.
        part(sim.URL_SCENARIO_IDS, sim.WHERE_FETCH, (), lambda: sim.run_url_paths(web))
        part(sim.DUPLICATE_ROW_IDS, sim.WHERE_DUPLICATES, (), lambda: sim.run_duplicates(session, config, TODAY))
        # Part E: the CLI in-process, then the web app through its test client.
        part(sim.CLI_ROW_IDS, sim.WHERE_CLI, (), sim.run_cli)

        def web_part() -> list[sim.Row]:
            web_app = create_app()
            web_app.dependency_overrides[deps.today] = lambda: TODAY
            with TestClient(web_app, base_url="http://127.0.0.1:8765", follow_redirects=False) as client:
                return sim.run_web(client, session, config, TODAY, jobs["S02"], jobs["S13"])

        part(sim.WEB_ROW_IDS, sim.WHERE_WEB, ("S02", "S13"), web_part)
    finally:
        session.close()
        engine.dispose()

    report = render_report(rows, title="Lead-scan simulation", temp_root=temp_root)
    report_path = temp_root / REPORT_NAME
    report_path.write_text(report, encoding="utf-8")
    print()
    print(report, end="")
    print()
    if keep:
        print(f"kept temp root: {temp_root} (report: {report_path})")
    else:
        shutil.rmtree(temp_root, ignore_errors=True)
        print(f"removed temp root {temp_root} (use --keep to inspect it and {REPORT_NAME})")
    return not any(r.result == "FAIL" for r in rows)


# --------------------------------------------------------------------------------------
# Part F: the live check (only on request)
# --------------------------------------------------------------------------------------


def _show_fields(output: str) -> dict[str, str]:
    """The extracted field values from ``ios job show`` output."""
    fields: dict[str, str] = {}
    inside_extraction = False
    for line in output.splitlines():
        if line.strip() in ("extraction (UNCONFIRMED):", "confirmed extraction:"):
            inside_extraction = True
            continue
        match = re.match(r"^ {4}(\w+): (.*)$", line) if inside_extraction else None
        if match:
            fields[match.group(1)] = match.group(2).strip()
    return fields


def _filled(value: str | None) -> bool:
    return bool(value) and value not in ("null", "unknown", "not_stated", "[]")


def run_live(keep: bool) -> bool:
    """The real CLI and LLM provider on two public postings in a fresh temporary root. Never confirms."""
    from tests.sim_scenarios import Row

    temp_root = Path(tempfile.mkdtemp(prefix="ios-live-")).resolve()
    populate_temp_root(temp_root)
    env = {key: value for key, value in os.environ.items() if key != "TYPESAFE_API_KEY"}
    env["IOS_ROOT"] = str(temp_root)
    env["IOS_DB_URL"] = f"sqlite:///{temp_root / 'db.sqlite'}"
    launcher = REPO / ".venv" / "bin" / "ios"
    command = [str(launcher)] if launcher.exists() else [sys.executable, "-m", "internship_os"]
    print()
    print(f"live check: temp root {temp_root}, Jev off, provider claude_code via {' '.join(command)}")

    def ios(*args: str) -> subprocess.CompletedProcess[str]:
        print(f"$ ios {' '.join(args)}")
        proc = subprocess.run(
            [*command, *args], env=env, cwd=str(temp_root), capture_output=True, text=True,
            encoding="utf-8", timeout=LIVE_TIMEOUT_SECONDS,
        )
        print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="")
        return proc

    rows: list[Row] = []
    try:
        init = ios("init")
        rows.append(Row("F-INIT", "ios init exits 0", f"exit {init.returncode}", "PASS" if init.returncode == 0 else "FAIL"))
        for url, source in LIVE_POSTINGS:
            captured = ios("capture", "--url", url, "--source", source)
            match = re.search(r"Captured job (\d+)", captured.stdout)
            ok = captured.returncode == 0 and match is not None
            rows.append(Row(f"F-CAPTURE-{source}", f"ios capture --url {url} --source {source} exits 0 and reports the job id",
                            f"exit {captured.returncode}" + ("" if match else f"; {captured.stderr.strip().splitlines()[-1:] or 'no job id'}"),
                            "PASS" if ok else "FAIL"))
            if not ok:
                continue
            shown = ios("job", "show", match.group(1))
            fields = _show_fields(shown.stdout)
            checks = {
                "work_mode": _filled(fields.get("work_mode")),
                "start_timing": _filled(fields.get("start_timing")),
                "salary_text with digits": bool(re.search(r"\d", fields.get("salary_text", ""))),
                "track_guess": _filled(fields.get("track_guess")),
            }
            if source == "yes_portal":
                checks["degree_required or restriction reflects the master's-or-graduated-bachelor's wording"] = (
                    fields.get("degree_required") in ("master", "bachelor") or _filled(fields.get("nationality_or_work_auth_restriction"))
                )
            actual = "; ".join(f"{name}: {'ok' if ok else 'MISSING'}" for name, ok in checks.items())
            actual += f" (work_mode={fields.get('work_mode')}, start_timing={fields.get('start_timing')}, salary_text={fields.get('salary_text')}, track_guess={fields.get('track_guess')}, degree_required={fields.get('degree_required')}, restriction={fields.get('nationality_or_work_auth_restriction')})"
            rows.append(Row(f"F-SHOW-{source}", "the extraction filled " + ", ".join(checks), actual, "PASS" if all(checks.values()) else "FAIL"))
    finally:
        print()
        print("id | expected | actual | PASS/FAIL")
        for row in rows:
            print(f"{row.id} | {_cell(row.expected)} | {_cell(row.actual)} | {row.result}")
        print(f"{sum(r.result == 'PASS' for r in rows)}/{len(rows)} passed (live)")
        if keep:
            print(f"kept live temp root: {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)
            print(f"removed live temp root {temp_root}")
    return all(r.result == "PASS" for r in rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", action="store_true", help="keep the temporary root(s) for inspection")
    parser.add_argument(
        "--live", action="store_true",
        help="after the scripted run, run part F: the real CLI and LLM provider on two public postings (spends your Claude subscription)",
    )
    args = parser.parse_args(argv)
    ok = run_scripted(keep=args.keep)
    if args.live:
        ok = run_live(keep=args.keep) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
