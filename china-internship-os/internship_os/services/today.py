"""Data for the Today page: the digest's computations returned as data. No LLM, no writes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from internship_os.config import AppConfig
from internship_os.digest import DEADLINE_WINDOW_DAYS, recommended_today
from internship_os.models import Job
from internship_os.programme import constraint_warnings, global_dimensions
from internship_os.schemas import NON_TERMINAL_STATUSES
from internship_os.tiering import TIER_ORDER
from internship_os.timeline import build_timeline, top_line


@dataclass
class Summary:
    top_line: str
    constraint_warnings: list[str]
    global_dimensions: dict[str, Any]
    needs_review: list[Job]
    due: list[Job]
    upcoming: list[Job]
    deadlines_soon: list[Job]
    recommended: list[Job]
    by_tier: list[tuple[str, int]]
    by_status: list[tuple[str, int]]
    by_programme: list[tuple[str, int]]


def summary(session: Session, config: AppConfig, today: date) -> Summary:
    jobs = list(session.scalars(select(Job).order_by(Job.id)))
    active = [j for j in jobs if j.status in NON_TERMINAL_STATUSES]
    dated = sorted((j for j in active if j.next_action_date is not None), key=lambda j: (j.next_action_date, j.id))
    horizon = today + timedelta(days=DEADLINE_WINDOW_DAYS)
    by_tier = Counter(j.tier for j in jobs)
    return Summary(
        top_line=top_line(build_timeline(config.user_facts, config.constraints, None, today), today),
        constraint_warnings=constraint_warnings(config.constraints, today),
        global_dimensions=global_dimensions(config.constraints, config.user_facts, today),
        needs_review=[j for j in active if j.confirmed_at is None and j.extracted],
        due=[j for j in dated if j.next_action_date <= today],
        upcoming=[j for j in dated if j.next_action_date > today],
        deadlines_soon=sorted(
            (j for j in active if j.deadline is not None and today <= j.deadline <= horizon),
            key=lambda j: (j.deadline, j.id),
        ),
        recommended=recommended_today(jobs, config),
        by_tier=[(t, by_tier.get(t, 0)) for t in TIER_ORDER],
        by_status=sorted(Counter(j.status for j in jobs).items()),
        by_programme=sorted(Counter(j.programme_overall for j in jobs).items()),
    )
