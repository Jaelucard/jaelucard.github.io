"""Typer CLI. ``ios`` and ``python -m internship_os`` both run :data:`app`.

Every command validates the configuration first. Nothing here sends, submits or posts anything
to an external party; the only network access is the single user-supplied job URL in
``ios capture --url``.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy.orm import Session

from internship_os import __version__
from internship_os.capture import (
    CaptureError,
    CaptureNeedsPaste,
    DuplicateCaptureNeedsDecision,
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
from internship_os.schemas import Extracted, ExtractedJob, SourceChannel

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
        text = text_file.read_text(encoding="utf-8")
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
        choice = console.input("Choose 1, 2 or 3: ").strip()
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
                raw = console.input(f"Attach to which job id {dup.candidate_ids}? ").strip()
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
        table.add_row(name, display_value(fld.value), span, "yes" if fld.confirmed else "no")
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
        "and all remaining. Lists: JSON list or comma-separated. Dates: YYYY-MM-DD. "
        "Booleans: true/false."
    )

    def decide(name: str, fld: Extracted[Any], error: str | None) -> str:
        if error:
            out(f"  invalid: {error}")
        return console.input(f"{name} [{display_value(fld.value)}]: ")

    confirmed, overrides = apply_confirmation(extracted, decide)
    company = _choose_company(session, confirmed)
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
            raw = console.input("Company choice: ").strip()
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
    out(f"  status: {job.status} | next: {job.next_action} ({job.next_action_date})")
    for note in result.notes:
        out(f"  {note}")
    if result.checklist_error:
        out(f"  quality checklist not generated: {result.checklist_error}")
