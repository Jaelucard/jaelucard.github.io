"""Typer CLI. ``ios`` and ``python -m internship_os`` both run :data:`app`.

Checkpoint 1 provides ``ios init`` only. Every command validates the configuration first.
"""

from __future__ import annotations

import typer
from rich.console import Console

from internship_os import __version__
from internship_os.config import USER_FACTS_FILE, AppConfig, ConfigError, load_config
from internship_os.db import database_url, get_engine, init_db

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


def load_config_or_exit() -> AppConfig:
    """Validate configuration; print ``file / key / problem`` lines and exit 1 on failure."""
    try:
        return load_config()
    except ConfigError as exc:
        err_console.print(exc.format(), markup=False, highlight=False, soft_wrap=True)
        raise typer.Exit(code=1)


@app.callback()
def main(ctx: typer.Context) -> None:
    ctx.obj = load_config_or_exit()


@app.command()
def init(ctx: typer.Context) -> None:
    """Create the database tables and, if absent, config/user_facts.yaml."""
    cfg: AppConfig = ctx.obj
    url = database_url(cfg.root)
    init_db(get_engine(url))
    console.print(f"Initialised database: {url}", markup=False, highlight=False, soft_wrap=True)
    console.print(
        f"User facts: {cfg.config_dir / USER_FACTS_FILE} (cohort {cfg.user_facts.graduation_cohort})",
        markup=False,
        highlight=False,
        soft_wrap=True,
    )


@app.command()
def version() -> None:
    """Print the package version."""
    console.print(f"internship_os {__version__}")
