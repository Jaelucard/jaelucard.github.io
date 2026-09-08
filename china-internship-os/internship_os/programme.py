"""Deterministic programme compatibility.

All programme values (durations, lead times, eligibility rules) are read from
``config/programme_constraints.yaml``. Nothing here duplicates a programme value as a literal.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from internship_os.models import Company, Job
from internship_os.schemas import (
    ConstraintStatus,
    ExtractedJob,
    ProgrammeConstraint,
    ProgrammeConstraints,
    ProgrammeDimension,
    ProgrammeStatus,
    UnconfirmedField,
    UserFacts,
    YesStatus,
)

# Worst to best. NOT_RUN only exists before any evaluation.
STATUS_ORDER: list[str] = [
    ProgrammeStatus.INCOMPATIBLE.value,
    ProgrammeStatus.AT_RISK.value,
    ProgrammeStatus.UNKNOWN.value,
    ProgrammeStatus.LIKELY.value,
    ProgrammeStatus.CONFIRMED.value,
]

YES_MAX = "YES_MAX_DURATION"
SUTD_MIN = "SUTD_MIN_DURATION"
YES_CITIZEN = "YES_ELIGIBILITY_CITIZEN_STUDENT"
YES_NO_PRIOR = "YES_NO_PRIOR_PARTICIPATION"
HOST_ROUTE = "HOST_ONBOARDING_ROUTE"
Z_ROUTE = "Z_VISA_ROUTE_USER"
Z_CHAIN = "Z_VISA_PROCESS_CHAIN"

Dimension = dict[str, Any]  # {"status": ..., "note": ...}


def dim(status: ProgrammeStatus | str, note: str | None) -> Dimension:
    return {"status": getattr(status, "value", status), "note": note}


def worst(statuses: list[str]) -> str:
    ranked = [s for s in statuses if s in STATUS_ORDER]
    if not ranked:
        return ProgrammeStatus.NOT_RUN.value
    return min(ranked, key=STATUS_ORDER.index)


def downgrade(status: str) -> str:
    """CONFIRMED -> LIKELY, LIKELY -> UNKNOWN; anything else unchanged."""
    if status == ProgrammeStatus.CONFIRMED:
        return ProgrammeStatus.LIKELY.value
    if status == ProgrammeStatus.LIKELY:
        return ProgrammeStatus.UNKNOWN.value
    return status


def is_stale(constraint: ProgrammeConstraint, today: date) -> bool:
    return constraint.verification_is_past(today)


def _apply_stale(status: str, note: str, constraints: list[ProgrammeConstraint], today: date) -> Dimension:
    stale = [c.constraint_id for c in constraints if is_stale(c, today)]
    if stale:
        new_status = downgrade(status)
        if new_status != status:
            note = f"{note} Downgraded {status} -> {new_status}: verification date past for {', '.join(stale)}."
            status = new_status
    return dim(status, note)


def programme_interval(constraints: ProgrammeConstraints) -> tuple[int, int]:
    """Permissible internship duration [SUTD_MIN_DURATION, YES_MAX_DURATION] in months."""
    lo = constraints.require(SUTD_MIN).value_months
    hi = constraints.require(YES_MAX).value_months
    if lo is None or hi is None:
        raise ValueError(f"{SUTD_MIN} and {YES_MAX} must both define value_months")
    return lo, hi


# --------------------------------------------------------------------------------------
# Dimensions
# --------------------------------------------------------------------------------------


def yes_eligibility(constraints: ProgrammeConstraints, user_facts: UserFacts, today: date) -> Dimension:
    citizen = constraints.get(YES_CITIZEN)
    prior = constraints.get(YES_NO_PRIOR)
    if (
        citizen is not None
        and citizen.status == ConstraintStatus.VERIFIED
        and prior is not None
        and prior.status in (ConstraintStatus.VERIFIED, ConstraintStatus.USER_CONFIRMED)
        and user_facts.prior_yes_participation is False
        and user_facts.citizenship.strip().casefold() == "singapore"
    ):
        return _apply_stale(
            ProgrammeStatus.CONFIRMED.value,
            f"{YES_CITIZEN} is {citizen.status.value}; {YES_NO_PRIOR} is {prior.status.value}; "
            "user is a Singapore citizen with no prior YES participation.",
            [citizen, prior],
            today,
        )
    missing = []
    if citizen is None or citizen.status != ConstraintStatus.VERIFIED:
        missing.append(f"{YES_CITIZEN} is not VERIFIED")
    if prior is None or prior.status not in (ConstraintStatus.VERIFIED, ConstraintStatus.USER_CONFIRMED):
        missing.append(f"{YES_NO_PRIOR} is not VERIFIED or USER_CONFIRMED")
    if user_facts.prior_yes_participation:
        missing.append("user_facts.prior_yes_participation is true")
    if user_facts.citizenship.strip().casefold() != "singapore":
        missing.append(f"user_facts.citizenship is {user_facts.citizenship}")
    return dim(ProgrammeStatus.UNKNOWN, "; ".join(missing) or "not established")


def immigration(constraints: ProgrammeConstraints, user_facts: UserFacts, today: date) -> Dimension:
    if user_facts.z_visa_issued:
        return dim(ProgrammeStatus.CONFIRMED, "user_facts.z_visa_issued is true.")
    route = constraints.get(Z_ROUTE)
    chain = constraints.get(Z_CHAIN)
    if (
        route is not None
        and route.status == ConstraintStatus.USER_CONFIRMED
        and chain is not None
        and chain.status == ConstraintStatus.VERIFIED
    ):
        return _apply_stale(
            ProgrammeStatus.LIKELY.value,
            f"{Z_ROUTE} is USER_CONFIRMED and {Z_CHAIN} is VERIFIED; Z visa not yet issued.",
            [route, chain],
            today,
        )
    return dim(
        ProgrammeStatus.UNKNOWN,
        f"{Z_ROUTE} must be USER_CONFIRMED and {Z_CHAIN} VERIFIED, or the Z visa must be issued.",
    )


def host_company(company: Company | None) -> Dimension:
    if company is None:
        return dim(ProgrammeStatus.UNKNOWN, "no company linked yet.")
    mapping = {
        YesStatus.confirmed.value: ProgrammeStatus.CONFIRMED,
        YesStatus.listed_on_yes.value: ProgrammeStatus.LIKELY,
        YesStatus.willing.value: ProgrammeStatus.LIKELY,
        YesStatus.unwilling.value: ProgrammeStatus.INCOMPATIBLE,
        YesStatus.unknown.value: ProgrammeStatus.UNKNOWN,
    }
    status = mapping.get(company.yes_status, ProgrammeStatus.UNKNOWN)
    return dim(status, f"company.yes_status is {company.yes_status}.")


def sutd_approval(job: Job, constraints: ProgrammeConstraints, today: date) -> Dimension:
    if job.sutd_approved_at is not None:
        return dim(ProgrammeStatus.CONFIRMED, f"SUTD approved this host on {job.sutd_approved_at.date().isoformat()}.")
    route = constraints.get(HOST_ROUTE)
    if route is not None and route.status == ConstraintStatus.USER_CONFIRMED:
        if is_stale(route, today):
            return dim(
                ProgrammeStatus.UNKNOWN,
                f"{HOST_ROUTE} is USER_CONFIRMED but its verification date "
                f"{route.next_verification_date} has passed; re-verify with SUTD.",
            )
        return dim(
            ProgrammeStatus.LIKELY,
            f"The SUTD onboarding route is known ({HOST_ROUTE} is USER_CONFIRMED), but SUTD has "
            "not yet explicitly approved this host. Run 'ios job approve-sutd' once it has.",
        )
    return dim(ProgrammeStatus.UNKNOWN, f"{HOST_ROUTE} is not USER_CONFIRMED.")


def duration_and_dates(job: Job, constraints: ProgrammeConstraints, user_facts: UserFacts) -> Dimension:
    lo, hi = programme_interval(constraints)
    intended = user_facts.internship.intended_start

    if job.agreed_start_date is not None and job.agreed_duration_months is not None:
        months = job.agreed_duration_months
        if months < lo or months > hi:
            return dim(
                ProgrammeStatus.AT_RISK,
                f"Agreed duration {months} months is outside the programme interval "
                f"{lo}-{hi} months ({SUTD_MIN}={lo}, {YES_MAX}={hi}).",
            )
        if job.agreed_start_date < intended:
            return dim(
                ProgrammeStatus.AT_RISK,
                f"Agreed start {job.agreed_start_date.isoformat()} is before the intended start "
                f"{intended.isoformat()}.",
            )
        return dim(
            ProgrammeStatus.CONFIRMED,
            f"Agreed start {job.agreed_start_date.isoformat()} and duration {months} months "
            f"satisfy the programme interval {lo}-{hi} months.",
        )

    if not job.extracted or job.confirmed_at is None:
        return dim(ProgrammeStatus.UNKNOWN, "extraction not confirmed; no agreed dates.")
    extracted = ExtractedJob.model_validate(job.extracted)
    try:
        dmin = extracted.confirmed_value("duration_min_months")
        dmax = extracted.confirmed_value("duration_max_months")
        start = extracted.confirmed_value("start_date")
    except UnconfirmedField as exc:
        return dim(ProgrammeStatus.UNKNOWN, f"unconfirmed: {', '.join(exc.fields)}")

    if start is not None and start < intended:
        return dim(
            ProgrammeStatus.AT_RISK,
            f"JD start {start.isoformat()} is before the intended start {intended.isoformat()}; "
            "the start may be negotiable.",
        )
    if dmin is None and dmax is None:
        return dim(
            ProgrammeStatus.UNKNOWN,
            "JD states no duration; agree dates with the employer (ios job dates).",
        )

    jd_lo = dmin if dmin is not None else None
    jd_hi = dmax if dmax is not None else None
    jd_text = _interval_text(jd_lo, jd_hi)
    if jd_hi is not None and jd_hi < lo:
        return dim(
            ProgrammeStatus.AT_RISK,
            f"JD duration {jd_text} months does not currently satisfy the SUTD minimum of {lo} months "
            f"({SUTD_MIN}={lo}); the posted duration may be negotiable with the employer.",
        )
    if jd_lo is not None and jd_lo > hi:
        return dim(
            ProgrammeStatus.AT_RISK,
            f"JD duration {jd_text} months exceeds the YES maximum of {hi} months "
            f"({YES_MAX}={hi}); the minimum may be negotiable with the employer.",
        )
    return dim(
        ProgrammeStatus.LIKELY,
        f"JD duration {jd_text} months overlaps the programme interval {lo}-{hi} months"
        + (f"; JD start {start.isoformat()} is compatible." if start else "."),
    )


def _interval_text(lo: int | None, hi: int | None) -> str:
    if lo is not None and hi is not None:
        return f"{lo}" if lo == hi else f"{lo}-{hi}"
    if lo is not None:
        return f"minimum {lo}"
    return f"maximum {hi}"


# --------------------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------------------


def run_programme(
    job: Job,
    company: Company | None,
    constraints: ProgrammeConstraints,
    user_facts: UserFacts,
    today: date | None = None,
) -> tuple[dict[str, Dimension], str]:
    when = today or date.today()
    dimensions: dict[str, Dimension] = {
        ProgrammeDimension.SUTD_APPROVAL.value: sutd_approval(job, constraints, when),
        ProgrammeDimension.YES_ELIGIBILITY.value: yes_eligibility(constraints, user_facts, when),
        ProgrammeDimension.HOST_COMPANY.value: host_company(company),
        ProgrammeDimension.DURATION_AND_DATES.value: duration_and_dates(job, constraints, user_facts),
        ProgrammeDimension.IMMIGRATION.value: immigration(constraints, user_facts, when),
    }
    overall = worst([d["status"] for d in dimensions.values()])
    return dimensions, overall


def global_dimensions(
    constraints: ProgrammeConstraints, user_facts: UserFacts, today: date | None = None
) -> dict[str, Dimension]:
    """The user-level dimensions that do not depend on a host (dashboard use)."""
    when = today or date.today()
    return {
        ProgrammeDimension.YES_ELIGIBILITY.value: yes_eligibility(constraints, user_facts, when),
        ProgrammeDimension.IMMIGRATION.value: immigration(constraints, user_facts, when),
    }


def constraint_warnings(constraints: ProgrammeConstraints, today: date | None = None) -> list[str]:
    when = today or date.today()
    warnings: list[str] = []
    for c in constraints:
        if is_stale(c, when):
            warnings.append(
                f"{c.constraint_id}: verification date {c.next_verification_date} has passed "
                f"(status {c.status.value}); re-check the source."
            )
        if c.status == ConstraintStatus.REQUIRES_CONFIRMATION:
            warnings.append(
                f"{c.constraint_id}: REQUIRES_CONFIRMATION"
                + (f" ({c.requires_action})" if c.requires_action else "")
            )
        elif c.status == ConstraintStatus.UNVERIFIED:
            warnings.append(
                f"{c.constraint_id}: UNVERIFIED" + (f" ({c.requires_action})" if c.requires_action else "")
            )
    return warnings
