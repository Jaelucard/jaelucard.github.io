"""Pydantic schemas and shared vocabularies.

Checkpoint 1 defines the configuration schemas (user facts, programme constraints, skill
evidence, cities) and the enumerations shared with the database models. Extraction schemas
(``ExtractedJob`` and friends) are added in Checkpoint 2.
"""

from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    RootModel,
    model_validator,
)

# --------------------------------------------------------------------------------------
# Vocabularies. Names equal values so that a stored string round-trips as the enum member.
# --------------------------------------------------------------------------------------


class HostType(StrEnum):
    startup = "startup"
    subsidiary = "subsidiary"
    large = "large"
    mnc = "mnc"
    unknown = "unknown"


class YesStatus(StrEnum):
    unknown = "unknown"
    listed_on_yes = "listed_on_yes"
    willing = "willing"
    unwilling = "unwilling"
    confirmed = "confirmed"


class Track(StrEnum):
    AI = "AI"
    SWE = "SWE"
    research = "research"
    other = "other"
    unknown = "unknown"


class SourceChannel(StrEnum):
    yes_portal = "yes_portal"
    company_site = "company_site"
    boss = "boss"
    shixiseng = "shixiseng"
    niuke = "niuke"
    maimai = "maimai"
    linkedin = "linkedin"
    wechat = "wechat"
    referral = "referral"
    xiaohongshu = "xiaohongshu"
    other = "other"


class Eligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    LIKELY_ELIGIBLE = "LIKELY_ELIGIBLE"
    UNCERTAIN = "UNCERTAIN"
    INELIGIBLE = "INELIGIBLE"
    NOT_RUN = "NOT_RUN"


class ProgrammeStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    UNKNOWN = "UNKNOWN"
    AT_RISK = "AT_RISK"
    INCOMPATIBLE = "INCOMPATIBLE"
    NOT_RUN = "NOT_RUN"


class ProgrammeDimension(StrEnum):
    SUTD_APPROVAL = "SUTD_APPROVAL"
    YES_ELIGIBILITY = "YES_ELIGIBILITY"
    HOST_COMPANY = "HOST_COMPANY"
    DURATION_AND_DATES = "DURATION_AND_DATES"
    IMMIGRATION = "IMMIGRATION"


class Fit(StrEnum):
    strong = "strong"
    ok = "ok"
    weak = "weak"
    unset = "unset"


class Quality(StrEnum):
    strong = "strong"
    ok = "ok"
    weak = "weak"
    unknown = "unknown"


class Tier(StrEnum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    HOLD = "HOLD"
    NOT_RUN = "NOT_RUN"


class Referral(StrEnum):
    none = "none"
    wanted = "wanted"
    have = "have"


class JobStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    PROGRAMME_CHECK_REQUIRED = "PROGRAMME_CHECK_REQUIRED"
    SHORTLISTED = "SHORTLISTED"
    READY_TO_APPLY = "READY_TO_APPLY"
    APPLIED = "APPLIED"
    IN_PROCESS = "IN_PROCESS"
    OFFER = "OFFER"
    INELIGIBLE = "INELIGIBLE"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    CLOSED = "CLOSED"


NON_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        JobStatus.DISCOVERED,
        JobStatus.PROGRAMME_CHECK_REQUIRED,
        JobStatus.SHORTLISTED,
        JobStatus.READY_TO_APPLY,
        JobStatus.APPLIED,
        JobStatus.IN_PROCESS,
        JobStatus.OFFER,
    }
)

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {JobStatus.INELIGIBLE, JobStatus.REJECTED, JobStatus.WITHDRAWN, JobStatus.CLOSED}
)


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES


class EventKind(StrEnum):
    captured = "captured"
    confirmed = "confirmed"
    status_change = "status_change"
    applied = "applied"
    message_drafted = "message_drafted"
    message_sent = "message_sent"  # manual record only; the tool never sends anything
    interview = "interview"
    note = "note"
    closed = "closed"
    programme_update = "programme_update"


class ContactChannel(StrEnum):
    wechat = "wechat"
    email = "email"
    linkedin = "linkedin"
    boss = "boss"
    phone = "phone"
    in_person = "in_person"
    other = "other"


class ConstraintStatus(StrEnum):
    VERIFIED = "VERIFIED"
    USER_CONFIRMED = "USER_CONFIRMED"
    LIKELY = "LIKELY"
    UNVERIFIED = "UNVERIFIED"
    CONFLICTING = "CONFLICTING"
    OUTDATED = "OUTDATED"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"


class EvidenceType(StrEnum):
    project = "project"
    internship = "internship"
    coursework = "coursework"
    competition = "competition"
    employment = "employment"
    user_fact = "user_fact"


class CityClass(StrEnum):
    primary = "primary"
    secondary = "secondary"
    expanded = "expanded"
    out = "out"
    unknown = "unknown"


class LLMProvider(StrEnum):
    claude_code = "claude_code"
    ollama = "ollama"


# --------------------------------------------------------------------------------------
# Base model: strict, unknown keys rejected. Enum fields are validated leniently so that the
# plain strings found in YAML are accepted; everything else stays strict.
# --------------------------------------------------------------------------------------


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


def _lax(tp: Any) -> Any:
    """Annotate an enum type so a plain string value is accepted under strict mode."""
    return Annotated[tp, Field(strict=False)]


def _stringify(value: Any) -> Any:
    """YAML parses ``period: 2025`` as an int; keep it as the text the user wrote."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return value


# --------------------------------------------------------------------------------------
# user_facts.yaml
# --------------------------------------------------------------------------------------


class ExchangeFacts(StrictModel):
    institution: str
    city: str
    visa_type: str
    end_date: _lax(date)


class InternshipFacts(StrictModel):
    intended_start: _lax(date)
    min_months: int = Field(ge=1)
    max_months: int = Field(ge=1)
    host_type_preference: list[_lax(HostType)] = Field(min_length=1)
    track_preference: list[_lax(Track)] = Field(min_length=1)
    offer_deadline_personal: _lax(date)

    @model_validator(mode="after")
    def _months_ordered(self) -> InternshipFacts:
        if self.min_months > self.max_months:
            raise ValueError("min_months must not exceed max_months")
        return self


class TimelineFacts(StrictModel):
    buffer_days_travel: int = Field(ge=0)
    buffer_days_admin: int = Field(ge=0)


class LLMModels(StrictModel):
    """Model per prompt role. For claude_code use CLI aliases (sonnet, opus, fable) or full
    ids (claude-sonnet-5); for ollama use Ollama model names (qwen2.5:14b)."""

    extraction: str = Field(min_length=1, description="extract_job, quality_checklist")
    drafting: str = Field(min_length=1, description="messages, bullets, interview prep, YES explanation")


class LLMFacts(StrictModel):
    provider: _lax(LLMProvider)
    models: LLMModels
    allow_resume_upload: bool = False
    max_wait_minutes: int | None = Field(default=None, ge=0, description="null = wait until the subscription limit resets")
    claude_command: str = Field(default="claude", min_length=1)


_COHORT_YEAR = re.compile(r"(\d{4})")


class UserFacts(StrictModel):
    name: str = Field(min_length=1)
    citizenship: str = Field(min_length=1)
    university: str = Field(min_length=1)
    programme: str = Field(min_length=1)
    graduation_cohort: str = Field(pattern=r"\d{4}", description="e.g. 2028届; must contain the year")
    expected_graduation: str = Field(pattern=r"^\d{4}-\d{2}$")
    mandarin_level: str = Field(min_length=1)
    mandarin_claim_zh: str = Field(min_length=1)
    mandarin_claim_en: str = Field(min_length=1)
    languages: list[str] = Field(min_length=1)
    github: str
    linkedin: str
    exchange: ExchangeFacts
    internship: InternshipFacts
    timeline: TimelineFacts
    z_visa_plan: str = Field(min_length=1)
    z_visa_issued: bool
    prior_yes_participation: bool
    llm: LLMFacts

    @property
    def cohort_year(self) -> int | None:
        """Parse ``2028`` from ``2028届``. None when no four-digit year is present."""
        match = _COHORT_YEAR.search(self.graduation_cohort)
        return int(match.group(1)) if match else None


# --------------------------------------------------------------------------------------
# programme_constraints.yaml
# --------------------------------------------------------------------------------------


class ProgrammeConstraint(StrictModel):
    constraint_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    statement: str = Field(min_length=1)
    status: _lax(ConstraintStatus)
    source: str | None
    source_type: str | None
    date_verified: _lax(date | None)
    applies_to: str = Field(min_length=1)
    confidence: str | None
    notes: str | None
    requires_action: str | None
    next_verification_date: _lax(date | None)
    value_months: int | None = Field(default=None, ge=0)
    placeholder_days: int | None = Field(default=None, ge=0)
    value_days: int | None = Field(default=None, ge=0)

    def verification_is_past(self, today: date) -> bool:
        """A verification date is past only when it is strictly before ``today``."""
        return self.next_verification_date is not None and self.next_verification_date < today


class ProgrammeConstraints(RootModel[list[ProgrammeConstraint]]):
    @model_validator(mode="after")
    def _unique_ids(self) -> ProgrammeConstraints:
        seen: set[str] = set()
        for item in self.root:
            if item.constraint_id in seen:
                raise ValueError(f"duplicate constraint_id {item.constraint_id}")
            seen.add(item.constraint_id)
        return self

    def __iter__(self):  # type: ignore[override]
        return iter(self.root)

    def __len__(self) -> int:
        return len(self.root)

    def ids(self) -> list[str]:
        return [c.constraint_id for c in self.root]

    def get(self, constraint_id: str) -> ProgrammeConstraint | None:
        for item in self.root:
            if item.constraint_id == constraint_id:
                return item
        return None

    def require(self, constraint_id: str) -> ProgrammeConstraint:
        item = self.get(constraint_id)
        if item is None:
            raise KeyError(
                f"programme constraint {constraint_id} is missing from programme_constraints.yaml"
            )
        return item


# --------------------------------------------------------------------------------------
# skill_evidence.yaml
# --------------------------------------------------------------------------------------


class SkillEvidence(StrictModel):
    id: str = Field(pattern=r"^EV_[A-Z0-9_]+$")
    title: str = Field(min_length=1)
    type: _lax(EvidenceType)
    period: Annotated[str | None, BeforeValidator(_stringify)]
    skills: list[str] = Field(min_length=1)
    claims: list[str] = Field(min_length=1)
    sources: list[str] = Field(min_length=1)
    restrictions: str | None


class SkillEvidenceSet(RootModel[list[SkillEvidence]]):
    @model_validator(mode="after")
    def _unique_ids(self) -> SkillEvidenceSet:
        seen: set[str] = set()
        for item in self.root:
            if item.id in seen:
                raise ValueError(f"duplicate evidence id {item.id}")
            seen.add(item.id)
        return self

    def __iter__(self):  # type: ignore[override]
        return iter(self.root)

    def __len__(self) -> int:
        return len(self.root)

    def ids(self) -> list[str]:
        return [e.id for e in self.root]

    def get(self, evidence_id: str) -> SkillEvidence | None:
        for item in self.root:
            if item.id == evidence_id:
                return item
        return None


# --------------------------------------------------------------------------------------
# cities.yaml
# --------------------------------------------------------------------------------------

_WS = re.compile(r"\s+")


def normalise_city(name: str | None) -> str:
    """Deterministic, case-insensitive city key.

    Accepts ``杭州``, ``杭州市``, ``Hangzhou``, ``Hangzhou City`` and equivalents.
    """
    if name is None:
        return ""
    text = _WS.sub(" ", name.strip()).casefold()
    if text.endswith("市"):
        text = text[:-1]
    if text.endswith(" city"):
        text = text[: -len(" city")]
    return text.strip()


class City(StrictModel):
    zh: str = Field(min_length=1)
    en: str = Field(min_length=1)
    province: str = Field(min_length=1)

    def matches(self, name: str | None) -> bool:
        key = normalise_city(name)
        return bool(key) and key in {normalise_city(self.zh), normalise_city(self.en)}


class CitiesConfig(StrictModel):
    primary: list[City]
    secondary: list[City]
    expanded: list[City]
    region_name_zh: str = Field(min_length=1)
    region_name_en: str = Field(min_length=1)

    def classify(self, name: str | None) -> CityClass:
        """Classify a city name from the configured lists only.

        Empty or None gives ``unknown``; a non-empty name matching no list gives ``out``.
        """
        if not normalise_city(name):
            return CityClass.unknown
        for city_class, cities in (
            (CityClass.primary, self.primary),
            (CityClass.secondary, self.secondary),
            (CityClass.expanded, self.expanded),
        ):
            if any(city.matches(name) for city in cities):
                return city_class
        return CityClass.out

    def find(self, name: str | None) -> City | None:
        for cities in (self.primary, self.secondary, self.expanded):
            for city in cities:
                if city.matches(name):
                    return city
        return None




# --------------------------------------------------------------------------------------
# Extraction schema (Checkpoint 2). Every field is wrapped in ``Extracted`` and starts
# ``confirmed: false``. capture.py forces that regardless of what the model returned.
# --------------------------------------------------------------------------------------

from typing import Generic, TypeVar  # noqa: E402

T = TypeVar("T")


class InternshipType(StrEnum):
    daily = "日常实习"
    summer = "暑期实习"
    winter = "寒假实习"
    campus = "校招实习"
    conversion = "转正实习"
    retention = "留用实习"
    international = "留学生实习"
    long_term = "长期实习"
    short_term = "短期实习"
    unknown = "unknown"


class Degree(StrEnum):
    none_stated = "none_stated"
    bachelor = "bachelor"
    master = "master"
    phd = "phd"


class ChineseLevel(StrEnum):
    none_stated = "none_stated"
    basic = "basic"
    working = "working"
    fluent = "fluent"
    native = "native"


class ResearchSignal(StrEnum):
    master_required = "master_required"
    phd_preferred = "phd_preferred"
    publications = "publications"
    cuda = "cuda"
    large_scale_training = "large_scale_training"
    deep_math_ml = "deep_math_ml"


class Extracted(BaseModel, Generic[T]):
    """One extracted field: value, whether the user confirmed it, and the verbatim JD span."""

    model_config = ConfigDict(extra="forbid")

    value: T | None = None
    confirmed: bool = False
    source_span: str | None = None


class UnconfirmedField(Exception):
    """A deterministic module asked for a field the user has not confirmed."""

    def __init__(self, fields: list[str]):
        self.fields = fields
        super().__init__("unconfirmed extracted field(s): " + ", ".join(fields))


# Fields whose ``None`` means "absent" and which therefore carry a sentinel with no span.
_SENTINEL_DEFAULTS: dict[str, Any] = {
    "internship_type": InternshipType.unknown,
    "cohort_years": [],
    "cohort_unrestricted": False,
    "degree_required": Degree.none_stated,
    "degree_preferred": Degree.none_stated,
    "required_skills": [],
    "preferred_skills": [],
    "chinese_required_level": ChineseLevel.none_stated,
    "role_closed": False,
    "track_guess": Track.unknown,
    "research_signals": [],
}


class ExtractedJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name_zh: Extracted[str] = Field(default_factory=Extracted)
    company_name_en: Extracted[str] = Field(default_factory=Extracted)
    title_zh: Extracted[str] = Field(default_factory=Extracted)
    title_en: Extracted[str] = Field(default_factory=Extracted)
    city_zh: Extracted[str] = Field(default_factory=Extracted)
    district: Extracted[str] = Field(default_factory=Extracted)
    internship_type: Extracted[InternshipType] = Field(default_factory=Extracted)
    graduation_cohort_text: Extracted[str] = Field(default_factory=Extracted)
    cohort_years: Extracted[list[int]] = Field(default_factory=Extracted)
    cohort_unrestricted: Extracted[bool] = Field(default_factory=Extracted)
    degree_required: Extracted[Degree] = Field(default_factory=Extracted)
    degree_preferred: Extracted[Degree] = Field(default_factory=Extracted)
    major_requirement: Extracted[str] = Field(default_factory=Extracted)
    days_per_week_min: Extracted[int] = Field(default_factory=Extracted)
    duration_min_months: Extracted[int] = Field(default_factory=Extracted)
    duration_max_months: Extracted[int] = Field(default_factory=Extracted)
    start_date_text: Extracted[str] = Field(default_factory=Extracted)
    start_date: Extracted[date] = Field(default_factory=Extracted)
    deadline: Extracted[date] = Field(default_factory=Extracted)
    salary_text: Extracted[str] = Field(default_factory=Extracted)
    required_skills: Extracted[list[str]] = Field(default_factory=Extracted)
    preferred_skills: Extracted[list[str]] = Field(default_factory=Extracted)
    language_requirement: Extracted[str] = Field(default_factory=Extracted)
    chinese_required_level: Extracted[ChineseLevel] = Field(default_factory=Extracted)
    nationality_or_work_auth_restriction: Extracted[str] = Field(default_factory=Extracted)
    role_closed: Extracted[bool] = Field(default_factory=Extracted)
    application_method: Extracted[str] = Field(default_factory=Extracted)
    referral_info: Extracted[str] = Field(default_factory=Extracted)
    responsibilities_summary: Extracted[str] = Field(default_factory=Extracted)
    track_guess: Extracted[Track] = Field(default_factory=Extracted)
    research_signals: Extracted[list[ResearchSignal]] = Field(default_factory=Extracted)

    @model_validator(mode="after")
    def _fill_sentinels(self) -> ExtractedJob:
        for name, sentinel in _SENTINEL_DEFAULTS.items():
            field: Extracted[Any] = getattr(self, name)
            if field.value is None:
                field.value = sentinel
                field.source_span = None
        return self

    # -- helpers used by capture, confirmation and the deterministic modules ------------

    @classmethod
    def field_names(cls) -> list[str]:
        return list(cls.model_fields)

    @classmethod
    def inner_type(cls, name: str) -> Any:
        """The ``T`` in ``Extracted[T]`` for ``name``."""
        annotation = cls.model_fields[name].annotation
        return annotation.__pydantic_generic_metadata__["args"][0]  # type: ignore[union-attr]

    def get(self, name: str) -> Extracted[Any]:
        return getattr(self, name)

    def unconfirmed_fields(self) -> list[str]:
        return [n for n in self.field_names() if not self.get(n).confirmed]

    @property
    def all_confirmed(self) -> bool:
        return not self.unconfirmed_fields()

    def confirmed_value(self, name: str) -> Any:
        """Value of ``name`` only if the user confirmed it; raises otherwise."""
        field = self.get(name)
        if not field.confirmed:
            raise UnconfirmedField([name])
        return field.value

    def require_confirmed(self, names: list[str]) -> None:
        missing = [n for n in names if not self.get(n).confirmed]
        if missing:
            raise UnconfirmedField(missing)


EXTRACTED_KEYS = frozenset({"value", "confirmed", "source_span"})


def force_unconfirmed(data: Any) -> Any:
    """Recursively set ``confirmed: false`` on every extracted-field dict in ``data``."""
    if isinstance(data, dict):
        out = {k: force_unconfirmed(v) for k, v in data.items()}
        if EXTRACTED_KEYS <= set(out):
            out["confirmed"] = False
        return out
    if isinstance(data, list):
        return [force_unconfirmed(v) for v in data]
    return data


# --------------------------------------------------------------------------------------
# Quality checklist schema (Checkpoint 3)
# --------------------------------------------------------------------------------------


class QualitySignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: str
    present: bool | None
    note: str | None = None


class QualityChecklist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signals: list[QualitySignal]
