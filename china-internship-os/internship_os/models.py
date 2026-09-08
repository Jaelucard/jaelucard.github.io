"""SQLAlchemy 2.x declarative models: Company, Job, JobEvent, Contact.

Invariants enforced at flush time:

* a Company must have at least one of ``name_en`` / ``name_zh``;
* a Job with a non-terminal status must have ``next_action`` and ``next_action_date``;
* moving a Job to a terminal status clears ``next_action`` and ``next_action_date``.

Jobs and companies are never deleted; closed or rejected items receive terminal statuses.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    validates,
)
from sqlalchemy.types import TypeDecorator

from internship_os.schemas import (
    ContactChannel,
    Eligibility,
    EventKind,
    Fit,
    HostType,
    JobStatus,
    ProgrammeDimension,
    ProgrammeStatus,
    Quality,
    Referral,
    SourceChannel,
    Tier,
    Track,
    YesStatus,
    is_terminal,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """Store timezone-aware UTC datetimes in SQLite and hand them back timezone-aware."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime rejected; use a timezone-aware UTC datetime")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


class InvariantError(ValueError):
    """A save-time invariant was violated."""


class ActiveJobNeedsNextAction(InvariantError):
    def __init__(self, job_id: int | None, status: str, missing: str):
        self.job_id = job_id
        self.status = status
        self.missing = missing
        ident = f"job id {job_id}" if job_id is not None else "new job (no id yet)"
        super().__init__(
            f"{ident}: status {status} is non-terminal, so {missing} must be set"
        )


class CompanyNeedsName(InvariantError):
    def __init__(self, company_id: int | None):
        ident = f"company id {company_id}" if company_id is not None else "new company"
        super().__init__(f"{ident}: at least one of name_en or name_zh must be set")


def _vocab(field: str, value: Any, allowed: type[StrEnum], *, nullable: bool = False) -> str | None:
    if value is None:
        if nullable:
            return None
        raise ValueError(f"{field} must not be null")
    try:
        return allowed(value).value
    except ValueError:
        options = ", ".join(m.value for m in allowed)
        raise ValueError(f"{field}: {value!r} is not one of [{options}]") from None


def programme_not_run() -> dict[str, dict[str, Any]]:
    """The ``programme`` JSON before any programme evaluation has run."""
    return {
        dim.value: {"status": ProgrammeStatus.NOT_RUN.value, "note": None}
        for dim in ProgrammeDimension
    }


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint(
            "name_en IS NOT NULL OR name_zh IS NOT NULL", name="ck_companies_has_name"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_en: Mapped[str | None] = mapped_column(String(255))
    name_zh: Mapped[str | None] = mapped_column(String(255))
    city_zh: Mapped[str | None] = mapped_column(String(64))
    website: Mapped[str | None] = mapped_column(String(512))
    host_type: Mapped[str] = mapped_column(String(32), nullable=False)
    yes_status: Mapped[str] = mapped_column(String(32), nullable=False)
    referral_notes: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    jobs: Mapped[list["Job"]] = relationship(back_populates="company")
    contacts: Mapped[list["Contact"]] = relationship(back_populates="company")

    def __init__(self, **kwargs: Any):
        kwargs.setdefault("host_type", HostType.unknown.value)
        kwargs.setdefault("yes_status", YesStatus.unknown.value)
        super().__init__(**kwargs)

    @validates("host_type")
    def _v_host_type(self, _key: str, value: Any) -> str:
        return _vocab("host_type", value, HostType)  # type: ignore[return-value]

    @validates("yes_status")
    def _v_yes_status(self, _key: str, value: Any) -> str:
        return _vocab("yes_status", value, YesStatus)  # type: ignore[return-value]

    @property
    def display_name(self) -> str:
        return self.name_zh or self.name_en or f"company {self.id}"

    def __repr__(self) -> str:
        return f"<Company id={self.id} {self.display_name!r} yes_status={self.yes_status}>"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    title_en: Mapped[str | None] = mapped_column(String(255))
    title_zh: Mapped[str | None] = mapped_column(String(255))
    city_zh: Mapped[str | None] = mapped_column(String(64))
    track: Mapped[str] = mapped_column(String(16), nullable=False)
    source_channel: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    deadline: Mapped[date | None]
    start_date: Mapped[date | None]
    duration_months: Mapped[int | None]
    agreed_start_date: Mapped[date | None]
    agreed_duration_months: Mapped[int | None]
    sutd_approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    next_action: Mapped[str | None] = mapped_column(String(512))
    next_action_date: Mapped[date | None]
    eligibility: Mapped[str] = mapped_column(String(32), nullable=False)
    eligibility_reasons: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    programme: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=programme_not_run
    )
    programme_overall: Mapped[str] = mapped_column(String(32), nullable=False)
    fit: Mapped[str] = mapped_column(String(16), nullable=False)
    quality: Mapped[str] = mapped_column(String(16), nullable=False)
    quality_checklist: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    referral: Mapped[str] = mapped_column(String(16), nullable=False)
    extracted: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    raw_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    company: Mapped[Company | None] = relationship(back_populates="jobs")
    events: Mapped[list["JobEvent"]] = relationship(
        back_populates="job", order_by="JobEvent.at", cascade="all"
    )

    def __init__(self, **kwargs: Any):
        kwargs.setdefault("track", Track.unknown.value)
        kwargs.setdefault("status", JobStatus.DISCOVERED.value)
        kwargs.setdefault("eligibility", Eligibility.NOT_RUN.value)
        kwargs.setdefault("eligibility_reasons", [])
        kwargs.setdefault("programme", programme_not_run())
        kwargs.setdefault("programme_overall", ProgrammeStatus.NOT_RUN.value)
        kwargs.setdefault("fit", Fit.unset.value)
        kwargs.setdefault("quality", Quality.unknown.value)
        kwargs.setdefault("quality_checklist", [])
        kwargs.setdefault("tier", Tier.NOT_RUN.value)
        kwargs.setdefault("referral", Referral.none.value)
        super().__init__(**kwargs)

    @validates("track")
    def _v_track(self, _key: str, value: Any) -> str:
        return _vocab("track", value, Track)  # type: ignore[return-value]

    @validates("source_channel")
    def _v_source_channel(self, _key: str, value: Any) -> str:
        return _vocab("source_channel", value, SourceChannel)  # type: ignore[return-value]

    @validates("status")
    def _v_status(self, _key: str, value: Any) -> str:
        return _vocab("status", value, JobStatus)  # type: ignore[return-value]

    @validates("eligibility")
    def _v_eligibility(self, _key: str, value: Any) -> str:
        return _vocab("eligibility", value, Eligibility)  # type: ignore[return-value]

    @validates("programme_overall")
    def _v_programme_overall(self, _key: str, value: Any) -> str:
        return _vocab("programme_overall", value, ProgrammeStatus)  # type: ignore[return-value]

    @validates("fit")
    def _v_fit(self, _key: str, value: Any) -> str:
        return _vocab("fit", value, Fit)  # type: ignore[return-value]

    @validates("quality")
    def _v_quality(self, _key: str, value: Any) -> str:
        return _vocab("quality", value, Quality)  # type: ignore[return-value]

    @validates("tier")
    def _v_tier(self, _key: str, value: Any) -> str:
        return _vocab("tier", value, Tier)  # type: ignore[return-value]

    @validates("referral")
    def _v_referral(self, _key: str, value: Any) -> str:
        return _vocab("referral", value, Referral)  # type: ignore[return-value]

    @property
    def is_terminal(self) -> bool:
        return is_terminal(self.status)

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None

    @property
    def display_title(self) -> str:
        return self.title_zh or self.title_en or f"job {self.id}"

    def __repr__(self) -> str:
        return f"<Job id={self.id} {self.display_title!r} status={self.status} tier={self.tier}>"


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[Any | None] = mapped_column(JSON)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id"))

    job: Mapped[Job] = relationship(back_populates="events")
    contact: Mapped["Contact | None"] = relationship()

    @validates("kind")
    def _v_kind(self, _key: str, value: Any) -> str:
        return _vocab("kind", value, EventKind)  # type: ignore[return-value]

    def __repr__(self) -> str:
        return f"<JobEvent id={self.id} job_id={self.job_id} kind={self.kind}>"


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(255))
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    last_contact: Mapped[date | None]
    next_followup: Mapped[date | None]
    notes: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="contacts")

    @validates("channel")
    def _v_channel(self, _key: str, value: Any) -> str:
        return _vocab("channel", value, ContactChannel)  # type: ignore[return-value]

    def __repr__(self) -> str:
        return f"<Contact id={self.id} {self.name!r} channel={self.channel}>"


# --------------------------------------------------------------------------------------
# Save-time invariants
# --------------------------------------------------------------------------------------


@event.listens_for(Job, "before_insert")
@event.listens_for(Job, "before_update")
def _enforce_active_job_next_action(_mapper: Any, _connection: Any, job: Job) -> None:
    status = job.status or JobStatus.DISCOVERED.value
    if is_terminal(status):
        # Terminal transitions clear the next action.
        job.next_action = None
        job.next_action_date = None
        return
    if job.next_action is None or not job.next_action.strip():
        raise ActiveJobNeedsNextAction(job.id, status, "next_action")
    if job.next_action_date is None:
        raise ActiveJobNeedsNextAction(job.id, status, "next_action_date")


@event.listens_for(Company, "before_insert")
@event.listens_for(Company, "before_update")
def _enforce_company_name(_mapper: Any, _connection: Any, company: Company) -> None:
    if company.name_en is None and company.name_zh is None:
        raise CompanyNeedsName(company.id)
