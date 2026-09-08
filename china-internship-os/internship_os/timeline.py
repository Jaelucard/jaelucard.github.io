"""Backward-planned programme timeline.

Anchor: the employer-agreed start date when the job has one, else the user's intended start.
An unconfirmed LLM-derived date is never used as the contractual start. Lead times come only
from ``programme_constraints.yaml``: ``value_days`` when set (a verified zero counts), else
``placeholder_days`` flagged as a placeholder. Personal buffers come from ``user_facts.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from internship_os.models import Job
from internship_os.schemas import ProgrammeConstraint, ProgrammeConstraints, UserFacts

Z_VISA_EMBASSY = "Z_VISA_EMBASSY_LEAD_TIME"
ENTRY_PERMIT = "ENTRY_PERMIT_LEAD_TIME"
LOC = "LOC_LEAD_TIME"
Z_CHAIN = "Z_VISA_PROCESS_CHAIN"

# Step names (stable identifiers used by tests, the digest and the dashboard).
START_WORK = "start_work"
POST_ARRIVAL = "post_arrival_checklist"
FLY = "fly_to_china"
Z_VISA_IN_PASSPORT = "z_visa_in_passport"
EMBASSY_SUBMISSION = "embassy_submission"
ENTRY_PERMIT_RECEIVED = "entry_permit_received"
HOST_ENTRY_PERMIT_APPLICATION = "host_entry_permit_application"
LOC_ISSUED = "loc_issued"
LOC_APPLICATION = "loc_application"
CONTRACT_BY = "contract_by"
EXCHANGE_ENDS = "exchange_ends"
PERSONAL_OFFER_DEADLINE = "personal_offer_deadline"

# Planning assumption from the Phase 1 prompt: the user must first be back in Singapore before
# submitting at the embassy, so submission earlier than exchange end + this many days is flagged.
RETURN_BUFFER_DAYS = 2


@dataclass
class Step:
    name: str
    date: date | None
    derived_from: str
    uses_placeholder: bool
    constraint_ids: list[str] = field(default_factory=list)
    informational: bool = False
    warning: str | None = None


def lead_time(constraint: ProgrammeConstraint) -> tuple[int, bool]:
    """(days, is_placeholder). Tests ``is not None`` so a verified zero still counts."""
    if constraint.value_days is not None:
        return constraint.value_days, False
    if constraint.placeholder_days is not None:
        return constraint.placeholder_days, True
    raise ValueError(
        f"{constraint.constraint_id} defines neither value_days nor placeholder_days"
    )


def start_anchor(user_facts: UserFacts, job: Job | None) -> tuple[date, str]:
    if job is not None and job.agreed_start_date is not None:
        return job.agreed_start_date, f"job {job.id} agreed_start_date"
    return user_facts.internship.intended_start, "user_facts.internship.intended_start"


def build_timeline(
    user_facts: UserFacts,
    constraints: ProgrammeConstraints,
    job: Job | None = None,
    today: date | None = None,
) -> list[Step]:
    start, start_source = start_anchor(user_facts, job)
    tl = user_facts.timeline
    embassy = constraints.require(Z_VISA_EMBASSY)
    permit = constraints.require(ENTRY_PERMIT)
    loc = constraints.require(LOC)
    chain = constraints.get(Z_CHAIN)

    embassy_days, embassy_ph = lead_time(embassy)
    permit_days, permit_ph = lead_time(permit)
    loc_days, loc_ph = lead_time(loc)

    fly = start - timedelta(days=tl.buffer_days_travel)
    embassy_submission = fly - timedelta(days=embassy_days)
    host_application = embassy_submission - timedelta(days=permit_days)
    loc_application = host_application - timedelta(days=loc_days)
    contract_by = loc_application - timedelta(days=tl.buffer_days_admin)

    exchange_end = user_facts.exchange.end_date
    offer_deadline = user_facts.internship.offer_deadline_personal

    embassy_warning = None
    earliest_submission = exchange_end + timedelta(days=RETURN_BUFFER_DAYS)
    if embassy_submission < earliest_submission:
        embassy_warning = (
            f"latest embassy submission {embassy_submission.isoformat()} is before exchange end "
            f"{exchange_end.isoformat()} + {RETURN_BUFFER_DAYS} days; the plan assumes you first "
            "return to Singapore, so the start date or lead times do not fit."
        )
    contract_warning = None
    if contract_by < offer_deadline:
        contract_warning = (
            f"contract-by {contract_by.isoformat()} is earlier than the personal offer deadline "
            f"{offer_deadline.isoformat()}; the personal deadline is too late to protect the "
            "administrative schedule."
        )

    steps = [
        Step(START_WORK, start, start_source, False),
        Step(
            POST_ARRIVAL,
            None,
            (chain.statement if chain else "Z visa process chain") + " (informational, not a planning deadline)",
            False,
            [Z_CHAIN] if chain else [],
            informational=True,
        ),
        Step(FLY, fly, f"start - buffer_days_travel ({tl.buffer_days_travel})", False),
        Step(Z_VISA_IN_PASSPORT, fly, "equals flight date", False),
        Step(
            EMBASSY_SUBMISSION,
            embassy_submission,
            f"flight - {Z_VISA_EMBASSY} ({embassy_days} days)",
            embassy_ph,
            [Z_VISA_EMBASSY],
            warning=embassy_warning,
        ),
        Step(ENTRY_PERMIT_RECEIVED, embassy_submission, "equals latest embassy submission", False),
        Step(
            HOST_ENTRY_PERMIT_APPLICATION,
            host_application,
            f"embassy submission - {ENTRY_PERMIT} ({permit_days} days)",
            permit_ph,
            [ENTRY_PERMIT],
        ),
        Step(LOC_ISSUED, host_application, "equals latest host entry-permit application", False),
        Step(
            LOC_APPLICATION,
            loc_application,
            f"host application - {LOC} ({loc_days} days)",
            loc_ph,
            [LOC],
        ),
        Step(
            CONTRACT_BY,
            contract_by,
            f"LOC application - buffer_days_admin ({tl.buffer_days_admin})",
            embassy_ph or permit_ph or loc_ph,
            [c for c, ph in ((Z_VISA_EMBASSY, embassy_ph), (ENTRY_PERMIT, permit_ph), (LOC, loc_ph)) if ph],
            warning=contract_warning,
        ),
        Step(EXCHANGE_ENDS, exchange_end, "user_facts.exchange.end_date", False),
        Step(PERSONAL_OFFER_DEADLINE, offer_deadline, "user_facts.internship.offer_deadline_personal", False),
    ]
    return steps


def step(steps: list[Step], name: str) -> Step:
    for s in steps:
        if s.name == name:
            return s
    raise KeyError(name)


def placeholders_in_use(steps: list[Step]) -> list[str]:
    """Union of placeholder constraints contributing to the contract deadline."""
    return list(step(steps, CONTRACT_BY).constraint_ids)


def top_line(steps: list[Step], today: date | None = None) -> str:
    when = today or date.today()
    contract = step(steps, CONTRACT_BY)
    assert contract.date is not None
    days = (contract.date - when).days
    ids = placeholders_in_use(steps)
    return (
        f"CONTRACT MUST BE SIGNED BY {contract.date.isoformat()} ({days} days). "
        f"Placeholders in use: {', '.join(ids) if ids else 'none'}"
    )


def warnings_for(steps: list[Step]) -> list[str]:
    return [s.warning for s in steps if s.warning]


def render(steps: list[Step], today: date | None = None) -> list[str]:
    lines = [top_line(steps, today), ""]
    for s in steps:
        if s.informational:
            lines.append(f"  {s.name:<32} (info)      {s.derived_from}")
            continue
        flag = " [placeholder]" if s.uses_placeholder else ""
        lines.append(f"  {s.name:<32} {s.date.isoformat() if s.date else '-'}  {s.derived_from}{flag}")
    for w in warnings_for(steps):
        lines.append(f"WARNING: {w}")
    return lines
