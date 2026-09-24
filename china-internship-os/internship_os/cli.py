"""Typer CLI. ``ios`` and ``python -m internship_os`` both run :data:`app`.

Every command validates the configuration first. Nothing here sends, submits or posts anything
to an external party; the only network access is the single user-supplied job URL in
``ios capture --url``.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text
from sqlalchemy import select
from sqlalchemy.orm import Session

from internship_os import __version__
from internship_os.capture import (
    CaptureError,
    CaptureNeedsPaste,
    DuplicateCaptureNeedsDecision,
    Override,
    apply_confirmation,
    attach_to_existing,
    capture as capture_core,
    create_company_from_extraction,
    find_company_matches,
)
from internship_os.config import USER_FACTS_FILE, AppConfig, ConfigError, load_config
from internship_os.db import database_url, get_engine, get_session, init_db
from internship_os.llm import LLMError
from internship_os.models import Company, Job
from internship_os.pipeline import finalize_confirmation
from internship_os.schemas import Extracted, ExtractedJob, SourceChannel, normalise_city

def _force_utf8_streams() -> None:
    """Chinese output must survive Windows consoles and redirected output."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None and (getattr(stream, "encoding", "") or "").lower().replace("-", "") != "utf8":
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - closed or exotic streams
                pass


_force_utf8_streams()

app = typer.Typer(
    help=(
        "China Internship OS. Captures job descriptions, checks eligibility and programme "
        "compatibility, and drafts text for you to send yourself. Nothing is ever sent by "
        "this tool."
    ),
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)

PRINT_KW: dict[str, Any] = {"markup": False, "highlight": False, "soft_wrap": True}


def out(message: str) -> None:
    console.print(message, **PRINT_KW)


def err(message: str) -> None:
    err_console.print(message, **PRINT_KW)


def load_config_or_exit() -> AppConfig:
    """Validate configuration; print ``file / key / problem`` lines and exit 1 on failure."""
    try:
        return load_config()
    except ConfigError as exc:
        err(exc.format())
        raise typer.Exit(code=1)


def get_job_or_exit(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        err(f"job {job_id} does not exist")
        raise typer.Exit(code=1)
    return job


def display_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(display_value(v) for v in value) if value else "[]"
    return str(getattr(value, "value", value))


def today_value() -> date:
    return date.today()


@app.callback()
def main(ctx: typer.Context) -> None:
    ctx.obj = load_config_or_exit()


@app.command()
def init(ctx: typer.Context) -> None:
    """Create the database tables and, if absent, config/user_facts.yaml."""
    cfg: AppConfig = ctx.obj
    url = database_url(cfg.root)
    init_db(get_engine(url))
    out(f"Initialised database: {url}")
    out(f"User facts: {cfg.config_dir / USER_FACTS_FILE} (cohort {cfg.user_facts.graduation_cohort})")


@app.command()
def version() -> None:
    """Print the package version."""
    out(f"internship_os {__version__}")


# --------------------------------------------------------------------------------------
# capture
# --------------------------------------------------------------------------------------

SOURCE_HELP = "Source channel: " + ", ".join(s.value for s in SourceChannel)
PASTE_FINISH_HINT = (
    "Paste the job description, then finish with Ctrl-Z followed by Enter on an empty line."
    if sys.platform.startswith("win")
    else "Paste the job description, then finish with Ctrl-D on an empty line."
)


def read_jd_file(path: Path) -> str:
    """Read a JD saved as UTF-8 (with or without BOM); fall back to GB18030 for files saved as ANSI on a Chinese Windows."""
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("gb18030")
    except UnicodeDecodeError:
        err(f"{path} is neither UTF-8 nor GB18030; re-save it as UTF-8")
        raise typer.Exit(code=1) from None
    err(f"note: {path} was not UTF-8; decoded it as GB18030")
    return text


@app.command()
def capture(
    ctx: typer.Context,
    text_file: Optional[Path] = typer.Option(None, "--text-file", help="Read the JD from a file."),
    paste: bool = typer.Option(False, "--paste", help="Read the JD from stdin until EOF."),
    url: Optional[str] = typer.Option(None, "--url", help="GET one public job URL."),
    source: str = typer.Option(..., "--source", help=SOURCE_HELP),
) -> None:
    """Capture a job description and extract fields for you to confirm."""
    cfg: AppConfig = ctx.obj
    supplied = sum(1 for flag in (text_file is not None, paste, url is not None) if flag)
    if supplied != 1:
        err("supply exactly one of --text-file, --paste, --url")
        raise typer.Exit(code=2)
    try:
        SourceChannel(source)
    except ValueError:
        err(f"--source must be one of: {', '.join(s.value for s in SourceChannel)}")
        raise typer.Exit(code=2)

    text: str | None = None
    if text_file is not None:
        if not text_file.exists():
            err(f"file not found: {text_file}")
            raise typer.Exit(code=1)
        text = read_jd_file(text_file)
    elif paste:
        err(PASTE_FINISH_HINT)
        text = sys.stdin.read()

    session = get_session()
    try:
        try:
            job = capture_core(text, url, source, session=session, config=cfg, today=today_value())
        except DuplicateCaptureNeedsDecision as dup:
            job = _resolve_duplicate(session, cfg, dup)
            if job is None:
                return
    except CaptureNeedsPaste as exc:
        err(f"URL capture failed: {exc}")
        raise typer.Exit(code=1)
    except CaptureError as exc:
        err(str(exc))
        raise typer.Exit(code=1)
    except LLMError as exc:
        err(f"extraction failed: {exc}")
        raise typer.Exit(code=1)
    out(f"Captured job {job.id}: {job.display_title} (status DISCOVERED, next: confirm extraction)")
    out(f"Run: ios confirm {job.id}")


def _resolve_duplicate(
    session: Session, cfg: AppConfig, dup: DuplicateCaptureNeedsDecision
) -> Job | None:
    out("Possible duplicate. Existing job(s):")
    for job_id in dup.candidate_ids:
        existing = session.get(Job, job_id)
        if existing is not None:
            out(f"  {existing.id}: {existing.display_title} [{existing.status}] {existing.source_url or ''}")
    out("1. attach this capture as a note to existing job")
    out("2. create a separate new job")
    out("3. cancel")
    while True:
        choice = console.input("Choose 1, 2 or 3: ", markup=False).strip()
        if choice in ("1", "2", "3"):
            break
        out("enter 1, 2 or 3")
    if choice == "3":
        out("Cancelled. No job was created.")
        return None
    if choice == "1":
        target = dup.candidate_ids[0]
        if len(dup.candidate_ids) > 1:
            while True:
                raw = console.input(f"Attach to which job id {dup.candidate_ids}? ", markup=False).strip()
                if raw.isdigit() and int(raw) in dup.candidate_ids:
                    target = int(raw)
                    break
        attach_to_existing(
            session, target, text=dup.text, url=dup.url, source_channel=dup.source_channel
        )
        out(f"Attached capture as a note to job {target}. No new job was created.")
        return None
    return capture_core(
        dup.text,
        dup.url,
        dup.source_channel,
        session=session,
        config=cfg,
        today=today_value(),
        extracted=dup.extracted,
        force_new=True,
    )


# --------------------------------------------------------------------------------------
# confirm
# --------------------------------------------------------------------------------------


def _extraction_table(extracted: ExtractedJob, *, span_width: int = 48) -> Table:
    table = Table(title="Extracted fields", show_lines=False)
    table.add_column("field")
    table.add_column("value")
    table.add_column("source span")
    table.add_column("confirmed")
    for name in ExtractedJob.field_names():
        fld: Extracted[Any] = extracted.get(name)
        span = (fld.source_span or "").replace("\n", " ")
        if len(span) > span_width:
            span = span[: span_width - 1] + "…"
        table.add_row(Text(name), Text(display_value(fld.value)), Text(span), Text("yes" if fld.confirmed else "no"))
    return table


@app.command()
def confirm(ctx: typer.Context, job_id: int) -> None:
    """Interactively confirm every extracted field, link the company and run the checks."""
    cfg: AppConfig = ctx.obj
    session = get_session()
    job = get_job_or_exit(session, job_id)
    if job.confirmed_at is not None:
        out(f"job {job.id} was already confirmed at {job.confirmed_at.isoformat()}")
        raise typer.Exit(code=0)
    if not job.extracted:
        err(f"job {job.id} has no extraction to confirm")
        raise typer.Exit(code=1)
    extracted = ExtractedJob.model_validate(job.extracted)
    console.print(_extraction_table(extracted))
    out(
        "Enter = confirm shown value | typed value = override | '-' = null | 'a' = accept this "
        "and all remaining except the must-check fields, which are still asked. Lists: JSON list "
        "or comma-separated. Dates: YYYY-MM-DD. Booleans: true/false."
    )

    def decide(name: str, fld: Extracted[Any], error: str | None) -> str:
        if error:
            out(f"  invalid: {error}")
        return console.input(f"{name} [{display_value(fld.value)}]: ", markup=False)

    confirmed, overrides = apply_confirmation(extracted, decide)
    if not (confirmed.company_name_zh.value or confirmed.company_name_en.value):
        out("No company name was confirmed. Enter the company name (Chinese or English), or leave blank to abort:")
        name = console.input("Company name: ", markup=False).strip()
        if not name:
            err("aborted: a company name is required; run ios confirm again")
            raise typer.Exit(code=1)
        target = "company_name_zh" if any("\u4e00" <= ch <= "\u9fff" for ch in name) else "company_name_en"
        fld = confirmed.get(target)
        overrides.append(Override(target, fld.value, name))
        fld.value = name
        fld.source_span = None
    try:
        company = _choose_company(session, confirmed)
    except CaptureError as exc:
        err(str(exc))
        raise typer.Exit(code=1) from None
    result = finalize_confirmation(
        session, job, confirmed, company, overrides, cfg, today=today_value()
    )
    _report_confirmation(result)


def _choose_company(session: Session, confirmed: ExtractedJob) -> Company:
    exact, near = find_company_matches(
        session, confirmed.company_name_zh.value, confirmed.company_name_en.value
    )
    if exact is not None:
        out(f"Linked existing company {exact.id}: {exact.display_name}")
        return exact
    if near:
        out("Similar companies exist. Select one or create a new company:")
        for index, candidate in enumerate(near, start=1):
            out(f"  {index}. {candidate.display_name} (id {candidate.id})")
        out("  0. create a new company")
        while True:
            raw = console.input("Company choice: ", markup=False).strip()
            if raw.isdigit() and 0 <= int(raw) <= len(near):
                break
            out(f"enter a number between 0 and {len(near)}")
        if int(raw) > 0:
            chosen = near[int(raw) - 1]
            out(f"Linked existing company {chosen.id}: {chosen.display_name}")
            return chosen
    company = create_company_from_extraction(session, confirmed)
    out(f"Created company {company.id}: {company.display_name}")
    return company


def _report_confirmation(result: Any) -> None:
    job = result.job
    out(f"Confirmed job {job.id}: {job.display_title} @ {result.company.display_name}")
    out(f"  eligibility: {job.eligibility} | programme: {job.programme_overall} | tier: {job.tier}")
    out(f"  status: {job.status} | next: {job.next_action or '-'} ({job.next_action_date or '-'})")
    for note in result.notes:
        out(f"  {note}")
    if result.checklist_error:
        out(f"  quality checklist not generated: {result.checklist_error}")


# ======================================================================================
# Checkpoint 3: job / company sub-commands, recompute, constraints
# ======================================================================================

from internship_os.pipeline import (  # noqa: E402
    TransitionError,
    add_note,
    approve_sutd as approve_sutd_core,
    recompute_all,
    set_agreed_dates,
    set_fit,
    set_quality,
    transition,
    update_company,
)
from internship_os.programme import constraint_warnings  # noqa: E402
from internship_os.schemas import HostType, JobStatus, Quality, Tier, Track, YesStatus  # noqa: E402
from internship_os.tiering import city_class_for, sort_jobs  # noqa: E402

job_app = typer.Typer(help="Job commands.", no_args_is_help=True)
company_app = typer.Typer(help="Company commands.", no_args_is_help=True)
app.add_typer(job_app, name="job")
app.add_typer(company_app, name="company")


def _parse_date(raw: str, flag: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        err(f"{flag} must be a date in YYYY-MM-DD form, got {raw!r}")
        raise typer.Exit(code=2)


def _choice(value: str, enum: Any, flag: str) -> str:
    try:
        return enum(value).value
    except ValueError:
        err(f"{flag} must be one of: {', '.join(m.value for m in enum)}")
        raise typer.Exit(code=2)


def job_show_lines(job: Job, cfg: AppConfig) -> list[str]:
    """The ``ios job show`` text for one job."""
    lines: list[str] = []
    out = lines.append
    company = job.company
    out(f"Job {job.id}")
    out(f"  company:      {company.display_name if company else '(not linked)'}"
        + (f" [id {company.id}, host_type {company.host_type}, yes_status {company.yes_status}]" if company else ""))
    out(f"  title:        {job.title_zh or ''} / {job.title_en or ''}")
    out(f"  source:       {job.source_channel} {job.source_url or ''}")
    out(f"  pipeline:     {job.status} | next: {job.next_action or '-'} ({job.next_action_date or '-'})")
    out(f"  confirmed_at: {job.confirmed_at.isoformat() if job.confirmed_at else 'not confirmed'}")
    out(f"  city:         {job.city_zh or '-'} (class {city_class_for(job, cfg)}) | track {job.track}")
    out(f"  deadline:     {job.deadline or '-'} | JD start {job.start_date or '-'} | duration_months {job.duration_months or '-'}")
    if job.agreed_start_date or job.agreed_duration_months:
        out(f"  agreed:       start {job.agreed_start_date} for {job.agreed_duration_months} months")
    if job.sutd_approved_at:
        out(f"  sutd_approved_at: {job.sutd_approved_at.isoformat()}")
    out(f"  eligibility:  {job.eligibility}")
    for reason in job.eligibility_reasons or []:
        out(f"    - {reason['code']} [{reason['field']}]: {reason['detail']}")
    out(f"  programme:    {job.programme_overall}")
    for name, d in (job.programme or {}).items():
        out(f"    - {name}: {d['status']}" + (f" ({d['note']})" if d.get('note') else ""))
    out(f"  fit: {job.fit} | quality: {job.quality} | tier: {job.tier} | referral: {job.referral}")
    if job.quality_checklist:
        present = [s["signal"] for s in job.quality_checklist if s.get("present") is True]
        absent = [s["signal"] for s in job.quality_checklist if s.get("present") is False]
        out(f"  quality checklist present: {', '.join(present) or '-'}")
        out(f"  quality checklist absent:  {', '.join(absent) or '-'}")
    if job.extracted:
        out("  confirmed extraction:" if job.confirmed_at else "  extraction (UNCONFIRMED):")
        extracted = ExtractedJob.model_validate(job.extracted)
        for name in ExtractedJob.field_names():
            fld = extracted.get(name)
            if fld.value not in (None, [], ""):
                out(f"    {name}: {display_value(fld.value)}")
    return lines


@job_app.command("show")
def job_show(ctx: typer.Context, job_id: int) -> None:
    """Show everything known about one job."""
    cfg: AppConfig = ctx.obj
    session = get_session()
    job = get_job_or_exit(session, job_id)
    for line in job_show_lines(job, cfg):
        out(line)


@job_app.command("list")
def job_list(
    ctx: typer.Context,
    tier: Optional[str] = typer.Option(None, "--tier"),
    status: Optional[str] = typer.Option(None, "--status"),
    track: Optional[str] = typer.Option(None, "--track"),
    city: Optional[str] = typer.Option(None, "--city"),
) -> None:
    """List jobs, sorted by tier then the within-tier rules."""
    cfg: AppConfig = ctx.obj
    session = get_session()
    jobs = list(session.scalars(select(Job)))
    if tier:
        jobs = [j for j in jobs if j.tier == _choice(tier, Tier, "--tier")]
    if status:
        jobs = [j for j in jobs if j.status == _choice(status, JobStatus, "--status")]
    if track:
        jobs = [j for j in jobs if j.track == _choice(track, Track, "--track")]
    if city:
        wanted = cfg.cities.find(city)
        jobs = [
            j for j in jobs
            if (wanted is not None and wanted.matches(j.city_zh)) or normalise_city(j.city_zh) == normalise_city(city)
        ]
    table = Table(title=f"{len(jobs)} job(s)")
    for col in ("id", "tier", "company", "title", "city", "track", "status", "elig", "programme", "deadline", "next"):
        table.add_column(col)
    for j in sort_jobs(jobs, cfg.user_facts):
        table.add_row(*[
            Text(str(v)) for v in (
                j.id, j.tier, j.company.display_name if j.company else "-", j.display_title,
                j.city_zh or "-", j.track, j.status, j.eligibility, j.programme_overall,
                j.deadline or "-", f"{j.next_action or '-'} ({j.next_action_date or '-'})",
            )
        ])
    console.print(table)


@job_app.command("fit")
def job_fit(ctx: typer.Context, job_id: int, value: str) -> None:
    """Set fit (strong|ok|weak) and rerun tiering."""
    cfg: AppConfig = ctx.obj
    session = get_session()
    job = get_job_or_exit(session, job_id)
    if value not in ("strong", "ok", "weak"):
        err("fit must be strong, ok or weak")
        raise typer.Exit(code=2)
    old_fit = job.fit
    old_tier, new_tier = set_fit(session, job, value, cfg)
    out(f"job {job.id} fit: {old_fit} -> {job.fit}; tier: {old_tier} -> {new_tier}")


@job_app.command("quality")
def job_quality(ctx: typer.Context, job_id: int, value: str) -> None:
    """Set quality (strong|ok|weak|unknown) and rerun tiering."""
    cfg: AppConfig = ctx.obj
    session = get_session()
    job = get_job_or_exit(session, job_id)
    value = _choice(value, Quality, "quality")
    old_quality = job.quality
    old_tier, new_tier = set_quality(session, job, value, cfg)
    out(f"job {job.id} quality: {old_quality} -> {job.quality}; tier: {old_tier} -> {new_tier}")


@job_app.command("status")
def job_status(
    ctx: typer.Context,
    job_id: int,
    state: str,
    next_action: Optional[str] = typer.Option(None, "--next", help="Next action (required for non-terminal states)."),
    due: Optional[str] = typer.Option(None, "--due", help="Next action date YYYY-MM-DD (required for non-terminal states)."),
    stage: Optional[str] = typer.Option(None, "--stage", help="Free-text stage, stored in the event."),
    note: Optional[str] = typer.Option(None, "--note", help="Note stored in the event (required when moving to INELIGIBLE)."),
) -> None:
    """Move a job to a pipeline state. READY_TO_APPLY is gated on programme status."""
    cfg: AppConfig = ctx.obj
    session = get_session()
    job = get_job_or_exit(session, job_id)
    state = _choice(state, JobStatus, "state")
    due_date = _parse_date(due, "--due") if due else None
    try:
        result = transition(
            session, job, state, next_action=next_action, due=due_date, stage=stage, note=note,
            config=cfg, today=today_value(),
        )
    except TransitionError as exc:
        err(str(exc))
        raise typer.Exit(code=2)
    if result.refused:
        out(f"job {job.id} status: {result.previous} -> {result.final} (refused {result.requested}: "
            f"programme_overall is {job.programme_overall}); next: {job.next_action} ({job.next_action_date})")
        raise typer.Exit(code=1)
    for warning in result.warnings:
        err(f"warning: {warning}")
    out(f"job {job.id} status: {result.previous} -> {result.final}"
        + (f"; next: {job.next_action} ({job.next_action_date})" if job.next_action else ""))


@job_app.command("approve-sutd")
def job_approve_sutd(ctx: typer.Context, job_id: int) -> None:
    """Record explicit SUTD approval of this host and recompute programme and tier."""
    cfg: AppConfig = ctx.obj
    session = get_session()
    job = get_job_or_exit(session, job_id)
    before = (job.programme_overall, job.tier)
    approve_sutd_core(session, job, cfg, today_value())
    out(f"job {job.id} sutd_approved_at: null -> {job.sutd_approved_at.isoformat()}; "
        f"programme: {before[0]} -> {job.programme_overall}; tier: {before[1]} -> {job.tier}")


@job_app.command("dates")
def job_dates(
    ctx: typer.Context,
    job_id: int,
    start: str = typer.Option(..., "--start", help="Employer-agreed start date YYYY-MM-DD."),
    months: int = typer.Option(..., "--months", help="Employer-agreed duration in months."),
) -> None:
    """Record employer-agreed start and duration. Does not touch the JD-extracted start date."""
    cfg: AppConfig = ctx.obj
    session = get_session()
    job = get_job_or_exit(session, job_id)
    start_date = _parse_date(start, "--start")
    old = (job.agreed_start_date, job.agreed_duration_months, job.programme_overall, job.tier)
    set_agreed_dates(session, job, start_date, months, cfg, today_value())
    dd = job.programme["DURATION_AND_DATES"]
    out(f"job {job.id} agreed dates: {old[0]}/{old[1]} -> {start_date}/{months}; "
        f"DURATION_AND_DATES {dd['status']}; programme: {old[2]} -> {job.programme_overall}; tier: {old[3]} -> {job.tier}")
    if dd.get("note"):
        out(f"  {dd['note']}")


@job_app.command("note")
def job_note(ctx: typer.Context, job_id: int, text: str) -> None:
    """Add a note event to a job."""
    session = get_session()
    job = get_job_or_exit(session, job_id)
    event = add_note(session, job, text)
    out(f"job {job.id} note event {event.id} added")


@company_app.command("set")
def company_set(
    ctx: typer.Context,
    company_id: int,
    host_type: Optional[str] = typer.Option(None, "--host-type", help="startup|subsidiary|large|mnc|unknown"),
    yes_status: Optional[str] = typer.Option(None, "--yes-status", help="unknown|listed_on_yes|willing|unwilling|confirmed"),
    note: Optional[str] = typer.Option(None, "--note"),
) -> None:
    """Update a company's host type, YES status or notes. Run 'ios recompute' afterwards."""
    session = get_session()
    company = session.get(Company, company_id)
    if company is None:
        err(f"company {company_id} does not exist")
        raise typer.Exit(code=1)
    if host_type is not None:
        host_type = _choice(host_type, HostType, "--host-type")
    if yes_status is not None:
        yes_status = _choice(yes_status, YesStatus, "--yes-status")
    if host_type is None and yes_status is None and note is None:
        err("nothing to set; use --host-type, --yes-status or --note")
        raise typer.Exit(code=2)
    changes = update_company(session, company, host_type=host_type, yes_status=yes_status, note=note)
    for field_name, old, new in changes:
        out(f"company {company.id} {field_name}: {old!r} -> {new!r}")
    if yes_status is not None or host_type is not None:
        out("run 'ios recompute' to refresh programme status and tiers of linked jobs")


@app.command()
def recompute(ctx: typer.Context) -> None:
    """Rerun eligibility, programme and tiering for every non-terminal confirmed job. No LLM."""
    cfg: AppConfig = ctx.obj
    session = get_session()
    changes = recompute_all(session, cfg, today_value())
    for job, before, after in changes:
        diff = [f"{k}: {before[k]} -> {after[k]}" for k in before if before[k] != after[k]]
        out(f"job {job.id}: " + ("; ".join(diff) if diff else "no change"))
    out(f"recomputed {len(changes)} job(s)")


@app.command()
def constraints(ctx: typer.Context) -> None:
    """Show programme constraints and warnings."""
    cfg: AppConfig = ctx.obj
    table = Table(title="Programme constraints")
    for col in ("id", "status", "date_verified", "next_verification", "value"):
        table.add_column(col)
    for c in cfg.constraints:
        value = ""
        if c.value_months is not None:
            value = f"{c.value_months} months"
        elif c.value_days is not None:
            value = f"{c.value_days} days"
        elif c.placeholder_days is not None:
            value = f"placeholder {c.placeholder_days} days"
        table.add_row(*[Text(str(v)) for v in (c.constraint_id, c.status.value, c.date_verified or "-", c.next_verification_date or "-", value)])
    console.print(table)
    warnings = constraint_warnings(cfg.constraints, today_value())
    out(f"{len(warnings)} warning(s)")
    for w in warnings:
        out(f"  - {w}")


# ======================================================================================
# Checkpoint 4: timeline, digest, contacts
# ======================================================================================

from internship_os.digest import build_digest  # noqa: E402
from internship_os.models import Contact  # noqa: E402
from internship_os.schemas import ContactChannel  # noqa: E402
from internship_os.timeline import build_timeline, render as render_timeline  # noqa: E402

contact_app = typer.Typer(help="Contact commands.", no_args_is_help=True)
app.add_typer(contact_app, name="contact")


@app.command()
def timeline(ctx: typer.Context, job: Optional[int] = typer.Option(None, "--job", help="Use this job's agreed start date.")) -> None:
    """Backward-planned dates from the intended (or agreed) start."""
    cfg: AppConfig = ctx.obj
    target = None
    if job is not None:
        session = get_session()
        target = get_job_or_exit(session, job)
    steps = build_timeline(cfg.user_facts, cfg.constraints, target, today_value())
    for line in render_timeline(steps, today_value()):
        out(line)


@app.command()
def digest(ctx: typer.Context) -> None:
    """Today's digest: contract deadline, warnings, counts, due actions, recommendations."""
    cfg: AppConfig = ctx.obj
    session = get_session()
    for line in build_digest(session, cfg, today_value()):
        out(line)


@contact_app.command("add")
def contact_add(
    ctx: typer.Context,
    company: int = typer.Option(..., "--company"),
    name: str = typer.Option(..., "--name"),
    role: Optional[str] = typer.Option(None, "--role"),
    channel: str = typer.Option(..., "--channel", help="wechat|email|linkedin|boss|phone|in_person|other"),
    notes: Optional[str] = typer.Option(None, "--notes"),
) -> None:
    """Add a contact at a company."""
    session = get_session()
    if session.get(Company, company) is None:
        err(f"company {company} does not exist")
        raise typer.Exit(code=1)
    channel = _choice(channel, ContactChannel, "--channel")
    contact = Contact(company_id=company, name=name, role=role, channel=channel, notes=notes)
    session.add(contact)
    session.commit()
    out(f"contact {contact.id} added: {name} ({role or '-'}, {channel}) at company {company}")


@contact_app.command("list")
def contact_list(ctx: typer.Context, company: Optional[int] = typer.Option(None, "--company")) -> None:
    """List contacts, optionally for one company."""
    session = get_session()
    query = select(Contact).order_by(Contact.company_id, Contact.id)
    if company is not None:
        query = query.where(Contact.company_id == company)
    table = Table(title="Contacts")
    for col in ("id", "company", "name", "role", "channel", "last_contact", "next_followup", "notes"):
        table.add_column(col)
    for c in session.scalars(query):
        table.add_row(*[
            Text(str(v)) for v in (
                c.id, f"{c.company.display_name} ({c.company_id})", c.name, c.role or "-", c.channel,
                c.last_contact or "-", c.next_followup or "-", c.notes or "",
            )
        ])
    console.print(table)


@contact_app.command("touch")
def contact_touch(ctx: typer.Context, contact_id: int, next_followup: str = typer.Option(..., "--next", help="Next follow-up YYYY-MM-DD.")) -> None:
    """Record contact today and set the next follow-up date."""
    session = get_session()
    contact = session.get(Contact, contact_id)
    if contact is None:
        err(f"contact {contact_id} does not exist")
        raise typer.Exit(code=1)
    when = _parse_date(next_followup, "--next")
    old = (contact.last_contact, contact.next_followup)
    contact.last_contact = today_value()
    contact.next_followup = when
    session.commit()
    out(f"contact {contact.id} last_contact: {old[0]} -> {contact.last_contact}; next_followup: {old[1]} -> {contact.next_followup}")


# ======================================================================================
# Checkpoint 5: application material
# ======================================================================================

from internship_os.drafts import (  # noqa: E402
    DraftError,
    generate_bullets,
    generate_interview_prep,
    generate_messages,
    write_pack,
)


def _draft_job(session: Session, job_id: int) -> Job:
    job = get_job_or_exit(session, job_id)
    if job.confirmed_at is None:
        err(f"job {job.id} is not confirmed; run 'ios confirm {job.id}' first")
        raise typer.Exit(code=1)
    return job


@job_app.command("pack")
def job_pack(ctx: typer.Context, job_id: int) -> None:
    """Write job.md, fit.md and checklist.md under packs/. No LLM."""
    cfg: AppConfig = ctx.obj
    session = get_session()
    job = _draft_job(session, job_id)
    try:
        result = write_pack(job, cfg, today_value())
    except DraftError as exc:
        err(str(exc))
        raise typer.Exit(code=1)
    for name, content in result.files.items():
        out(f"===== {result.directory / name} =====")
        out(content)
    out(f"wrote {', '.join(result.files)} to {result.directory}")


@job_app.command("messages")
def job_messages(ctx: typer.Context, job_id: int) -> None:
    """Draft recruiter, referral and YES-explanation messages (zh/en) into messages.md."""
    cfg: AppConfig = ctx.obj
    session = get_session()
    job = _draft_job(session, job_id)
    try:
        result = generate_messages(job, cfg, today_value())
    except (DraftError, LLMError) as exc:
        err(str(exc))
        raise typer.Exit(code=1)
    out(result.content)
    for r in result.rejected:
        err(r.line())
    for key, reason in result.failures.items():
        err(f"section {key} not generated: {reason}")
    out(f"wrote messages.md to {result.directory} ({len(result.sections)}/6 sections)")


@job_app.command("bullets")
def job_bullets(ctx: typer.Context, job_id: int) -> None:
    """Draft 4-6 tailored resume bullets, each ending in a valid evidence id, into bullets.md."""
    cfg: AppConfig = ctx.obj
    session = get_session()
    job = _draft_job(session, job_id)
    try:
        result = generate_bullets(job, cfg)
    except (DraftError, LLMError) as exc:
        err(str(exc))
        raise typer.Exit(code=1)
    out(result.content)
    for r in result.rejected:
        err(f"dropped bullet: {r.text} ({r.reason})")
    out(f"wrote bullets.md to {result.directory} ({len(result.kept)} kept, {len(result.rejected)} dropped)")


@job_app.command("interview-prep")
def job_interview_prep(ctx: typer.Context, job_id: int) -> None:
    """Draft interview-prep.md. Only for jobs in IN_PROCESS."""
    cfg: AppConfig = ctx.obj
    session = get_session()
    job = _draft_job(session, job_id)
    try:
        result = generate_interview_prep(job, cfg)
    except (DraftError, LLMError) as exc:
        err(str(exc))
        raise typer.Exit(code=1)
    out(result.content)
    for r in result.rejected:
        err(f"dropped evidence reference: {r.text} ({r.reason})")
    out(f"wrote interview-prep.md to {result.directory}")


# ======================================================================================
# LLM provider check
# ======================================================================================

from internship_os.llm import PROMPT_ROLES, claude_code_status  # noqa: E402


@app.command("llm-check")
def llm_check(ctx: typer.Context) -> None:
    """Show the configured LLM provider and, for claude_code, whether the CLI is installed and logged in."""
    cfg: AppConfig = ctx.obj
    llm_cfg = cfg.user_facts.llm
    out(f"provider: {llm_cfg.provider}")
    out(f"models: extraction={llm_cfg.models.extraction} ({', '.join(p for p, r in PROMPT_ROLES.items() if r == 'extraction')}); "
        f"drafting={llm_cfg.models.drafting} ({', '.join(p for p, r in PROMPT_ROLES.items() if r == 'drafting')})")
    out(f"rate-limit wait: {'until the limit resets' if llm_cfg.max_wait_minutes is None else str(llm_cfg.max_wait_minutes) + ' minutes'}")
    if llm_cfg.provider != "claude_code":
        out("ollama: POST http://localhost:11434/api/generate; make sure 'ollama serve' is running")
        return
    info = claude_code_status(cfg)
    if not info.get("found"):
        err(f"claude CLI: {info.get('error', 'not found')}. Install: npm install -g @anthropic-ai/claude-code, then: claude auth login")
        raise typer.Exit(code=1)
    out(f"claude CLI: {info['executable']} (version {info.get('version', '?')})")
    logged_in = info.get("loggedIn")
    out(f"logged in: {logged_in} | auth: {info.get('authMethod', '?')} | provider: {info.get('apiProvider', '?')}")
    if logged_in is False:
        err("not logged in: run 'claude auth login' and sign in with your Claude subscription")
        raise typer.Exit(code=1)
    if logged_in is None:
        err("could not determine login state: " + str(info.get("error") or info.get("auth_raw") or "no JSON from 'claude auth status'"))
        raise typer.Exit(code=1)
    stripped = [v for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN") if os.environ.get(v)]
    if stripped:
        out(f"note: {', '.join(stripped)} is set in your shell; it is stripped for the CLI so your subscription is used")


# ======================================================================================
# Local web UI
# ======================================================================================


@app.command()
def ui(ctx: typer.Context, port: int = typer.Option(8765, "--port", min=1, max=65535, help="Port on 127.0.0.1.")) -> None:
    """Serve the web UI at http://127.0.0.1:<port>. It listens on this machine only."""
    import socket

    import uvicorn

    cfg: AppConfig = ctx.obj
    try:
        with socket.create_server(("127.0.0.1", port)):
            pass
    except OSError as exc:
        err(f"port {port} on 127.0.0.1 is not available ({exc.strerror or exc}); try --port N")
        raise typer.Exit(code=1)
    init_db(get_engine(database_url(cfg.root)))
    out(f"Internship OS UI: http://127.0.0.1:{port}  (Ctrl-C to stop)")
    uvicorn.run("internship_os.web.app:app", host="127.0.0.1", port=port)
