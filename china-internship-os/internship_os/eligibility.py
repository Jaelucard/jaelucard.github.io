"""Deterministic candidate eligibility.

Reads confirmed extracted fields and ``user_facts.yaml`` only. Never calls an LLM. Every
reason carries ``code``, ``field`` and ``detail``; the detail names the triggering value.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from internship_os.models import Job
from internship_os.schemas import (
    ChineseLevel,
    Degree,
    Eligibility,
    ExtractedJob,
    SkillEvidenceSet,
    UnconfirmedField,
    UserFacts,
)


@dataclass(frozen=True)
class Reason:
    code: str
    field: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


# Fields the decision reads. If any is unconfirmed the result is NOT_RUN.
DECISION_FIELDS = [
    "degree_required",
    "graduation_cohort_text",
    "cohort_years",
    "cohort_unrestricted",
    "nationality_or_work_auth_restriction",
    "role_closed",
    "deadline",
    "chinese_required_level",
    "days_per_week_min",
    "required_skills",
    "preferred_skills",
    "research_signals",
]

HARD_FAIL_CODES = frozenset(
    {
        "DEGREE_INELIGIBLE",
        "GRADUATION_COHORT_INELIGIBLE",
        "EXPLICIT_NATIONALITY_RESTRICTION",
        "EXPLICIT_WORK_AUTHORIZATION_RESTRICTION",
        "ROLE_CLOSED",
        "DEADLINE_PASSED",
    }
)
UNCERTAIN_CODES = frozenset(
    {"RESTRICTION_TEXT_PRESENT_REVIEW", "CHINESE_LEVEL_REVIEW", "COHORT_TEXT_UNPARSEABLE"}
)

# Clearly exclusionary nationality wording. Silence never matches anything here.
NATIONALITY_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"仅限中国籍",
        r"限中国籍",
        r"中国国籍",
        r"仅限内地",
        r"仅限大陆",
        r"仅限中国大陆",
        r"中国大陆籍",
        r"不接受外籍",
        r"不招(收|聘)?外籍",
        r"PRC\s+nationals?\s+only",
        r"Chinese\s+(citizens?|nationals?)\s+only",
        r"must\s+be\s+(a\s+)?(PRC|Chinese)\s+(citizen|national)",
        r"only\s+open\s+to\s+(PRC|Chinese)\s+(citizens?|nationals?)",
    )
]
# Explicit pre-existing work-authorisation requirements or refusal of visa support.
WORK_AUTH_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"must\s+(already\s+)?(be|have)\s+(been\s+)?authori[sz]ed\s+to\s+work\s+in\s+China",
        r"existing\s+(China|PRC)\s+work\s+authori[sz]ation",
        r"(valid|existing)\s+(China|PRC)\s+work\s+permit\s+required",
        r"no\s+visa\s+sponsorship",
        r"(cannot|will\s+not|do\s+not|does\s+not|unable\s+to)\s+(sponsor|provide)\s+(a\s+)?(work\s+)?visa",
        r"不提供(工作)?签证(支持|担保|办理)?",
        r"不(提供|办理)工作许可",
        r"需(已)?持有(中国)?工作(许可|签证)",
        r"已具备(中国)?工作(许可|资格)",
    )
]
EXPERIENCE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (r"\d+\s*年(以上|及以上)?(工作|相关)?经验", r"年经验", r"\d+\+?\s*years?")
]

SKILL_MATCH_THRESHOLD = 0.85  # difflib ratio on normalised strings; documented, fixed
_NON_ALNUM = re.compile(r"[_\-/]+")
_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-z0-9+#.]+")


def normalise_skill(text: str) -> str:
    return _WS.sub(" ", _NON_ALNUM.sub(" ", text.casefold())).strip()


def skill_matches(skill: str, evidence: SkillEvidenceSet) -> list[str]:
    """Evidence ids whose skill tags match ``skill`` deterministically."""
    wanted = normalise_skill(skill)
    if not wanted:
        return []
    tokens = set(_TOKEN.findall(wanted))
    matched: list[str] = []
    for item in evidence:
        for tag in item.skills:
            candidate = normalise_skill(tag)
            if not candidate:
                continue
            hit = (
                candidate == wanted
                or candidate in tokens
                or (len(candidate) >= 3 and candidate in wanted)
                or (len(wanted) >= 3 and wanted in candidate)
                or difflib.SequenceMatcher(None, candidate, wanted).ratio() >= SKILL_MATCH_THRESHOLD
            )
            if hit:
                matched.append(item.id)
                break
    return matched


def skill_gaps(skills: list[str], evidence: SkillEvidenceSet) -> list[str]:
    return [s for s in skills if not skill_matches(s, evidence)]


def _matches_any(patterns: list[re.Pattern[str]], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def run_eligibility(
    job: Job,
    user_facts: UserFacts,
    today: date | None = None,
    *,
    evidence: SkillEvidenceSet | None = None,
) -> tuple[str, list[Reason]]:
    """Return ``(status, reasons)``. Reads confirmed extracted fields only."""
    when = today or date.today()
    if not job.extracted:
        return Eligibility.NOT_RUN.value, [
            Reason("UNCONFIRMED_FIELDS", "extracted", "no extraction has been captured yet")
        ]
    extracted = ExtractedJob.model_validate(job.extracted)
    try:
        extracted.require_confirmed(DECISION_FIELDS)
    except UnconfirmedField as exc:
        return Eligibility.NOT_RUN.value, [
            Reason("UNCONFIRMED_FIELDS", "extracted", "unconfirmed: " + ", ".join(exc.fields))
        ]

    v: dict[str, Any] = {name: extracted.confirmed_value(name) for name in DECISION_FIELDS}
    reasons: list[Reason] = []

    # ---- hard fails -------------------------------------------------------------------
    degree = v["degree_required"]
    if degree in (Degree.master, Degree.phd):
        reasons.append(
            Reason("DEGREE_INELIGIBLE", "degree_required", f"degree_required is {degree.value}")
        )

    cohort_years: list[int] = v["cohort_years"] or []
    user_year = user_facts.cohort_year
    if not v["cohort_unrestricted"] and cohort_years and user_year not in cohort_years:
        reasons.append(
            Reason(
                "GRADUATION_COHORT_INELIGIBLE",
                "cohort_years",
                f"JD cohorts {cohort_years} exclude user cohort {user_facts.graduation_cohort} ({user_year})",
            )
        )

    restriction = v["nationality_or_work_auth_restriction"]
    if restriction:
        nat = _matches_any(NATIONALITY_PATTERNS, restriction)
        auth = _matches_any(WORK_AUTH_PATTERNS, restriction)
        if nat:
            reasons.append(
                Reason(
                    "EXPLICIT_NATIONALITY_RESTRICTION",
                    "nationality_or_work_auth_restriction",
                    f"matched '{nat}' in: {restriction}",
                )
            )
        if auth:
            reasons.append(
                Reason(
                    "EXPLICIT_WORK_AUTHORIZATION_RESTRICTION",
                    "nationality_or_work_auth_restriction",
                    f"matched '{auth}' in: {restriction}",
                )
            )
        if not nat and not auth:
            reasons.append(
                Reason(
                    "RESTRICTION_TEXT_PRESENT_REVIEW",
                    "nationality_or_work_auth_restriction",
                    f"restriction text present but no deterministic pattern matched: {restriction}",
                )
            )

    if v["role_closed"] is True:
        reasons.append(Reason("ROLE_CLOSED", "role_closed", "role_closed is true"))

    deadline = v["deadline"]
    if deadline is not None and deadline < when:
        reasons.append(
            Reason("DEADLINE_PASSED", "deadline", f"deadline {deadline.isoformat()} is before {when.isoformat()}")
        )

    # ---- soft flags -------------------------------------------------------------------
    level = v["chinese_required_level"]
    if level == ChineseLevel.native:
        reasons.append(
            Reason(
                "CHINESE_LEVEL_ABOVE_STATED",
                "chinese_required_level",
                f"JD requires native Chinese; user level is {user_facts.mandarin_level}",
            )
        )
    elif level == ChineseLevel.fluent:
        reasons.append(
            Reason(
                "CHINESE_LEVEL_REVIEW",
                "chinese_required_level",
                f"JD requires fluent Chinese; user level is {user_facts.mandarin_level}",
            )
        )

    days = v["days_per_week_min"]
    if days is not None and days > 5:
        reasons.append(Reason("DAYS_PER_WEEK_HIGH", "days_per_week_min", f"days_per_week_min is {days}"))

    required: list[str] = v["required_skills"] or []
    preferred: list[str] = v["preferred_skills"] or []
    for skill in required:
        hit = _matches_any(EXPERIENCE_PATTERNS, skill)
        if hit:
            reasons.append(
                Reason("EXPERIENCE_YEARS_ASKED", "required_skills", f"'{hit}' in required skill: {skill}")
            )

    if evidence is not None:
        gaps = skill_gaps(preferred, evidence)
        if gaps:
            reasons.append(
                Reason("PREFERRED_SKILL_GAPS", "preferred_skills", "no evidence for: " + ", ".join(gaps))
            )
        gaps = skill_gaps(required, evidence)
        if gaps:
            reasons.append(
                Reason("REQUIRED_SKILL_GAPS", "required_skills", "no evidence for: " + ", ".join(gaps))
            )

    signals = v["research_signals"] or []
    if signals:
        reasons.append(
            Reason(
                "RESEARCH_ROLE_SIGNALS",
                "research_signals",
                "signals: " + ", ".join(getattr(s, "value", str(s)) for s in signals),
            )
        )

    cohort_text = v["graduation_cohort_text"]
    if cohort_text and not v["cohort_unrestricted"] and not cohort_years:
        reasons.append(
            Reason(
                "COHORT_TEXT_UNPARSEABLE",
                "graduation_cohort_text",
                f"cohort text present but no years parsed: {cohort_text}",
            )
        )

    # ---- final status -----------------------------------------------------------------
    codes = {r.code for r in reasons}
    if codes & HARD_FAIL_CODES:
        status = Eligibility.INELIGIBLE
    elif codes & UNCERTAIN_CODES:
        status = Eligibility.UNCERTAIN
    elif codes:
        status = Eligibility.LIKELY_ELIGIBLE
    else:
        status = Eligibility.ELIGIBLE
    return status.value, reasons
