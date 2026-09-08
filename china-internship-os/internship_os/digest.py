"""Deterministic daily digest. No fetching, no LLM."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from internship_os.config import AppConfig
from internship_os.models import Job
from internship_os.programme import constraint_warnings
from internship_os.schemas import NON_TERMINAL_STATUSES, Tier
from internship_os.tiering import TIER_ORDER, sort_jobs
from internship_os.timeline import build_timeline, top_line

DEADLINE_WINDOW_DAYS = 7
RECOMMEND_LIMIT = 3
RECOMMENDABLE_TIERS = frozenset({Tier.T1.value, Tier.T2.value, Tier.T3.value})


def recommended_today(jobs: list[Job], config: AppConfig, limit: int = RECOMMEND_LIMIT) -> list[Job]:
    candidates = [
        j for j in jobs if j.status in NON_TERMINAL_STATUSES and j.tier in RECOMMENDABLE_TIERS
    ]
    return sort_jobs(candidates, config.user_facts)[:limit]


def _label(job: Job) -> str:
    company = job.company.display_name if job.company else "(no company)"
    return f"{job.id}: {job.display_title} @ {company}"


def build_digest(session: Session, config: AppConfig, today: date | None = None) -> list[str]:
    when = today or date.today()
    jobs = list(session.scalars(select(Job).order_by(Job.id)))
    lines: list[str] = []

    # 1. timeline top line
    lines.append(top_line(build_timeline(config.user_facts, config.constraints, None, when), when))

    # 2. constraint warnings
    warnings = constraint_warnings(config.constraints, when)
    lines.append("")
    lines.append(f"Programme constraint warnings ({len(warnings)}):")
    lines.extend(f"  - {w}" for w in warnings) if warnings else lines.append("  none")

    # 3. counts
    by_tier = Counter(j.tier for j in jobs)
    by_status = Counter(j.status for j in jobs)
    by_programme = Counter(j.programme_overall for j in jobs)
    lines.append("")
    lines.append("Jobs by tier: " + ", ".join(f"{t} {by_tier.get(t, 0)}" for t in TIER_ORDER))
    lines.append("Jobs by status: " + (", ".join(f"{s} {n}" for s, n in sorted(by_status.items())) or "none"))
    lines.append(
        "Programme overall: " + (", ".join(f"{s} {n}" for s, n in sorted(by_programme.items())) or "none")
    )

    # 4. deadlines within 7 days
    horizon = when + timedelta(days=DEADLINE_WINDOW_DAYS)
    soon = [
        j for j in jobs
        if j.status in NON_TERMINAL_STATUSES and j.deadline is not None and when <= j.deadline <= horizon
    ]
    lines.append("")
    lines.append(f"Deadlines within {DEADLINE_WINDOW_DAYS} days ({len(soon)}):")
    lines.extend(f"  - {j.deadline} {_label(j)}" for j in sorted(soon, key=lambda j: j.deadline)) if soon else lines.append("  none")

    # 5. active jobs with next_action_date <= today
    due = [
        j for j in jobs
        if j.status in NON_TERMINAL_STATUSES and j.next_action_date is not None and j.next_action_date <= when
    ]
    lines.append("")
    lines.append(f"Actions due ({len(due)}):")
    lines.extend(
        f"  - {j.next_action_date} {_label(j)} -> {j.next_action}"
        for j in sorted(due, key=lambda j: (j.next_action_date, j.id))
    ) if due else lines.append("  none")

    # 6. recommended today
    picks = recommended_today(jobs, config)
    lines.append("")
    lines.append(f"Recommended today ({len(picks)}):")
    lines.extend(f"  - [{j.tier}] {_label(j)} ({j.status}; next: {j.next_action})" for j in picks) if picks else lines.append("  none")
    return lines
