"""Deterministic tiering and ordering. First matching tier rule wins.

Role title wording never changes a tier. AI is not ranked above SWE; track preference is a
within-tier sort key applied after deadline and host type.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from internship_os.config import AppConfig
from internship_os.models import Job
from internship_os.programme import STATUS_ORDER
from internship_os.schemas import CityClass, Eligibility, Fit, ProgrammeStatus, Quality, Tier, UserFacts

TIER_ORDER: list[str] = [Tier.T1.value, Tier.T2.value, Tier.T3.value, Tier.HOLD.value, Tier.NOT_RUN.value]
ELIGIBLE_SET = frozenset({Eligibility.ELIGIBLE.value, Eligibility.LIKELY_ELIGIBLE.value})


def compute_tier(
    eligibility: str, programme_overall: str, city_class: str, fit: str, quality: str
) -> str:
    if (
        eligibility == Eligibility.INELIGIBLE
        or programme_overall == ProgrammeStatus.INCOMPATIBLE
        or city_class == CityClass.out
    ):
        return Tier.HOLD.value
    if eligibility in ELIGIBLE_SET and quality == Quality.strong and fit in (Fit.strong, Fit.ok):
        return Tier.T1.value
    if eligibility in ELIGIBLE_SET and (
        (quality == Quality.ok and fit == Fit.strong)
        or (quality == Quality.strong and fit == Fit.weak)
        or (quality == Quality.unknown and fit == Fit.strong)
    ):
        return Tier.T2.value
    return Tier.T3.value


def city_class_for(job: Job, config: AppConfig) -> str:
    """City class from cities.yaml only, using the confirmed top-level city."""
    return config.cities.classify(job.city_zh).value


def run_tiering(job: Job, config: AppConfig) -> str:
    return compute_tier(
        job.eligibility, job.programme_overall, city_class_for(job, config), job.fit, job.quality
    )


# --------------------------------------------------------------------------------------
# Ordering
# --------------------------------------------------------------------------------------


def _preference_index(value: str | None, preferences: list[str]) -> int:
    values = [getattr(p, "value", p) for p in preferences]
    return values.index(value) if value in values else len(values)


def sort_key(job: Job, user_facts: UserFacts) -> tuple:
    deadline: date | None = job.deadline
    host_type = job.company.host_type if job.company is not None else None
    programme_rank = (
        len(STATUS_ORDER) - STATUS_ORDER.index(job.programme_overall)
        if job.programme_overall in STATUS_ORDER
        else len(STATUS_ORDER) + 1
    )
    return (
        TIER_ORDER.index(job.tier) if job.tier in TIER_ORDER else len(TIER_ORDER),
        deadline is None,
        deadline or date.max,
        _preference_index(host_type, user_facts.internship.host_type_preference),
        _preference_index(job.track, user_facts.internship.track_preference),
        programme_rank,
        job.id or 0,
    )


def sort_jobs(jobs: Iterable[Job], user_facts: UserFacts) -> list[Job]:
    return sorted(jobs, key=lambda j: sort_key(j, user_facts))
