"""Application material: pack (deterministic), messages, bullets, interview prep (LLM-drafted).

Provenance boundary: every generated factual statement is structured as ``{text, source_refs,
kind}`` before rendering. ``user_claim`` must cite valid ``EV_...`` ids or ``user_facts.<key>``
paths; ``programme_fact`` must cite allowed programme constraint ids; ``nonclaim`` needs no
source. Anything else is dropped and reported as ``Refused unsourced claim: <text>``.

This is not semantic fact-checking; it is an enforceable provenance check. Mandarin proficiency
is enforced separately: statements about Mandarin must carry the verbatim configured claim and
may never claim native Mandarin.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from internship_os import llm
from internship_os.config import AppConfig
from internship_os.eligibility import skill_matches
from internship_os.models import Job
from internship_os.programme import constraint_warnings, programme_interval
from internship_os.schemas import ConstraintStatus, ExtractedJob, JobStatus, UserFacts
from internship_os.timeline import build_timeline, render as render_timeline, top_line

PACKS_DIRNAME = "packs"
YES_EXPLANATION_CONSTRAINTS = [
    "HOST_OBLIGATIONS",
    "Z_VISA_PROCESS_CHAIN",
    "HOST_ONBOARDING_ROUTE",
    "YES_MAX_DURATION",
]
ALLOWED_YES_STATUSES = (ConstraintStatus.VERIFIED, ConstraintStatus.USER_CONFIRMED)
LIMIT_ZH_CHARS = 150
LIMIT_EN_WORDS = 120
MIN_BULLETS, MAX_BULLETS = 4, 6


class DraftError(Exception):
    """Draft generation could not run."""


# --------------------------------------------------------------------------------------
# Structured statements
# --------------------------------------------------------------------------------------

Kind = Literal["user_claim", "programme_fact", "nonclaim"]


class Statement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    source_refs: list[str] = Field(default_factory=list)
    kind: Kind


class MessageDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statements: list[Statement]


class MessagesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recruiter_zh: MessageDraft
    recruiter_en: MessageDraft
    referral_zh: MessageDraft
    referral_en: MessageDraft


class YesExplanationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zh: MessageDraft
    en: MessageDraft


class BulletsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bullets: list[str]


class InterviewPrepOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technical_questions: list[str]
    behavioural_questions: list[str]
    evidence_to_rehearse: list[str]


@dataclass
class Rejection:
    text: str
    reason: str

    def line(self) -> str:
        return f"Refused unsourced claim: {self.text} ({self.reason})"


@dataclass
class ValidationReport:
    kept: list[Statement] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)


EV_REF = re.compile(r"^EV_[A-Z0-9_]+$")
USER_FACTS_REF = re.compile(r"^user_facts\.([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*)$")
MANDARIN_MARKERS = ("中文", "汉语", "普通话", "华语", "mandarin", "chinese")
_NATIVE_ZH = re.compile(r"(?<!非)母语")
_NATIVE_EN = re.compile(r"(?<!non-)(?<!non )\bnative\b", re.IGNORECASE)


def user_facts_key_exists(user_facts: UserFacts, path: str) -> bool:
    node: Any = user_facts
    for part in path.split("."):
        if isinstance(node, BaseModel) and part in type(node).model_fields:
            node = getattr(node, part)
        else:
            return False
    return True


def mandarin_problem(text: str, user_facts: UserFacts) -> str | None:
    """None when the statement is acceptable, else the reason it is not."""
    lowered = text.casefold()
    if not any(marker in lowered for marker in MANDARIN_MARKERS):
        return None
    if _NATIVE_ZH.search(text) or _NATIVE_EN.search(text):
        return "claims native Mandarin"
    # Remove the verbatim configured claim, then scan what remains: anything that still reads
    # as a proficiency claim is an addition beyond the allowed wording.
    remainder = text.replace(user_facts.mandarin_claim_zh, "").replace(user_facts.mandarin_claim_en, "")
    remainder_lowered = remainder.casefold()
    if not any(marker in remainder_lowered for marker in MANDARIN_MARKERS):
        return None
    # Mentions of Chinese that are not about proficiency (e.g. the Chinese market) are allowed;
    # anything that reads as a proficiency claim must use the verbatim configured wording.
    if any(p in remainder_lowered for p in PROFICIENCY_MARKERS):
        return "Mandarin proficiency must use mandarin_claim_zh or mandarin_claim_en verbatim"
    return None


PROFICIENCY_MARKERS = ("proficien", "fluent", "speak", "流利", "熟练", "精通", "水平", "能力", "工作语言", "会说")
# A nonclaim may not carry facts: no digits, no achievement verbs, no programme vocabulary.
_CLAIM_VERBS = re.compile(
    r"\b(built|developed|designed|led|trained|maintained|placed|won|achieved|improved|implemented|"
    r"deployed|optimi[sz]ed|shipped|published)\b|开发了|设计了|训练了|负责过|获得|带领|实现了|发表",
    re.IGNORECASE,
)
_PROGRAMME_WORDS = re.compile(
    r"visa|permit|stipend|sponsor|business china|\bLOC\b|\bYES\b|months?|weeks?|days?|签证|许可|津贴|"
    r"补贴|个月|周|天|通商中国|实习计划",
    re.IGNORECASE,
)


def nonclaim_problem(text: str, *, programme_context: bool) -> str | None:
    if re.search(r"\d", text):
        return "nonclaim contains a number; facts must be user_claim or programme_fact with sources"
    if _CLAIM_VERBS.search(text):
        return "nonclaim reads as an achievement claim; cite evidence as user_claim"
    if programme_context and _PROGRAMME_WORDS.search(text):
        return "nonclaim introduces programme vocabulary; cite an allowed constraint as programme_fact"
    return None


def validate_statements(
    statements: list[Statement],
    config: AppConfig,
    *,
    allowed_constraint_ids: list[str] | None = None,
) -> ValidationReport:
    report = ValidationReport()
    evidence_ids = set(config.evidence.ids())
    allowed = set(allowed_constraint_ids or [])
    for st in statements:
        text = st.text.strip()
        if not text:
            continue
        problem = mandarin_problem(text, config.user_facts)
        if problem:
            report.rejected.append(Rejection(text, problem))
            continue
        if st.kind == "user_claim":
            if not st.source_refs:
                report.rejected.append(Rejection(text, "user_claim with no source_refs"))
                continue
            bad = [
                r for r in st.source_refs
                if not (
                    (EV_REF.match(r) and r in evidence_ids)
                    or (USER_FACTS_REF.match(r) and user_facts_key_exists(config.user_facts, USER_FACTS_REF.match(r).group(1)))  # type: ignore[union-attr]
                )
            ]
            if bad:
                report.rejected.append(Rejection(text, f"invalid source_refs: {', '.join(bad)}"))
                continue
        elif st.kind == "programme_fact":
            if not st.source_refs:
                report.rejected.append(Rejection(text, "programme_fact with no source_refs"))
                continue
            bad = [r for r in st.source_refs if r not in allowed]
            if bad:
                report.rejected.append(Rejection(text, f"constraint ids not allowed here: {', '.join(bad)}"))
                continue
        else:
            problem = nonclaim_problem(text, programme_context=allowed_constraint_ids is not None)
            if problem:
                report.rejected.append(Rejection(text, problem))
                continue
        report.kept.append(Statement(text=text, source_refs=list(st.source_refs), kind=st.kind))
    return report


# --------------------------------------------------------------------------------------
# Rendering and limits
# --------------------------------------------------------------------------------------

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def render_statements(statements: list[Statement]) -> str:
    lines = []
    for st in statements:
        tag = f" <!-- {', '.join(st.source_refs)} -->" if st.source_refs else ""
        lines.append(st.text + tag)
    return "\n".join(lines)


def strip_comments(text: str) -> str:
    return _COMMENT.sub("", text)


def zh_length(text: str) -> int:
    return len(re.sub(r"\s+", "", strip_comments(text)))


def en_words(text: str) -> int:
    return len(strip_comments(text).split())


def length_problem(text: str, lang: str) -> str | None:
    if lang == "zh":
        n = zh_length(text)
        return None if n <= LIMIT_ZH_CHARS else f"{n} Chinese characters exceeds the limit of {LIMIT_ZH_CHARS}"
    n = en_words(text)
    return None if n <= LIMIT_EN_WORDS else f"{n} words exceeds the limit of {LIMIT_EN_WORDS}"


# --------------------------------------------------------------------------------------
# Pack directory
# --------------------------------------------------------------------------------------

_SLUG_KEEP = re.compile(r"[^0-9a-z一-鿿]+")


def slug(text: str | None, fallback: str = "unknown") -> str:
    cleaned = _SLUG_KEEP.sub("-", (text or "").casefold()).strip("-")
    return (cleaned or fallback)[:40].strip("-") or fallback


def pack_dir(job: Job, root: Path) -> Path:
    company = job.company.display_name if job.company else "no-company"
    return root / PACKS_DIRNAME / f"{slug(company, 'company')}--{slug(job.display_title, 'job')}"


def _require_confirmed(job: Job) -> ExtractedJob:
    if job.confirmed_at is None or not job.extracted:
        raise DraftError(f"job {job.id} is not confirmed; run 'ios confirm {job.id}' first")
    extracted = ExtractedJob.model_validate(job.extracted)
    if not extracted.all_confirmed:
        raise DraftError(f"job {job.id} has unconfirmed fields: {', '.join(extracted.unconfirmed_fields())}")
    return extracted


def _evidence_json(config: AppConfig) -> str:
    return json.dumps([e.model_dump() for e in config.evidence], ensure_ascii=False, indent=1)


def _user_facts_json(config: AppConfig) -> str:
    uf = config.user_facts
    subset = {
        "user_facts.name": uf.name,
        "user_facts.citizenship": uf.citizenship,
        "user_facts.university": uf.university,
        "user_facts.programme": uf.programme,
        "user_facts.graduation_cohort": uf.graduation_cohort,
        "user_facts.expected_graduation": uf.expected_graduation,
        "user_facts.mandarin_claim_zh": uf.mandarin_claim_zh,
        "user_facts.mandarin_claim_en": uf.mandarin_claim_en,
        "user_facts.languages": uf.languages,
        "user_facts.github": uf.github,
        "user_facts.linkedin": uf.linkedin,
        "user_facts.exchange.institution": uf.exchange.institution,
        "user_facts.exchange.city": uf.exchange.city,
        "user_facts.internship.intended_start": uf.internship.intended_start.isoformat(),
    }
    return json.dumps(subset, ensure_ascii=False, indent=1)


def _job_variables(job: Job, extracted: ExtractedJob) -> dict[str, Any]:
    return {
        "title": job.display_title,
        "company": job.company.display_name if job.company else "",
        "city": job.city_zh or "",
        "required_skills": extracted.required_skills.value or [],
        "preferred_skills": extracted.preferred_skills.value or [],
        "responsibilities": extracted.responsibilities_summary.value or "",
    }


# --------------------------------------------------------------------------------------
# ios job pack: job.md, fit.md, checklist.md (deterministic, no LLM)
# --------------------------------------------------------------------------------------


@dataclass
class PackResult:
    directory: Path
    files: dict[str, str]  # filename -> content


def _skill_rows(extracted: ExtractedJob, config: AppConfig) -> list[tuple[str, str, list[str]]]:
    rows = []
    for kind, skills in (("required", extracted.required_skills.value or []), ("preferred", extracted.preferred_skills.value or [])):
        for skill in skills:
            rows.append((skill, kind, skill_matches(skill, config.evidence)))
    return rows


def strengths(extracted: ExtractedJob, config: AppConfig) -> list[str]:
    """Deterministic strength lines from evidence matching the JD skills. Each ends with [EV_ID]."""
    matched_ids: list[str] = []
    for _, _, ids in _skill_rows(extracted, config):
        for i in ids:
            if i not in matched_ids:
                matched_ids.append(i)
    lines = []
    for ev_id in matched_ids:
        item = config.evidence.get(ev_id)
        if item is None:
            continue
        lines.append(f"{item.title}: {item.claims[0]} [{item.id}]")
    return lines


def write_pack(job: Job, config: AppConfig, today: date | None = None) -> PackResult:
    when = today or date.today()
    extracted = _require_confirmed(job)
    directory = pack_dir(job, config.root)
    directory.mkdir(parents=True, exist_ok=True)
    company = job.company.display_name if job.company else "(no company)"

    job_md = [f"# {job.display_title} @ {company}", ""]
    job_md += [f"- company: {company}", f"- title: {job.title_zh or ''} / {job.title_en or ''}",
               f"- source: {job.source_channel} {job.source_url or ''}", f"- status: {job.status}", "",
               "## Confirmed extraction", ""]
    for name in ExtractedJob.field_names():
        fld = extracted.get(name)
        value = fld.value
        if isinstance(value, list):
            value = ", ".join(getattr(v, "value", str(v)) for v in value)
        elif value is not None:
            value = getattr(value, "value", value)
        job_md.append(f"- {name}: {value if value not in (None, '') else '-'}")
    job_md += ["", "## Raw JD", "", "```", job.raw_text or "", "```", ""]

    fit_md = [f"# Fit: {job.display_title} @ {company}", "", f"- eligibility: {job.eligibility}"]
    fit_md += [f"  - {r['code']} [{r['field']}]: {r['detail']}" for r in (job.eligibility_reasons or [])]
    fit_md += ["", "## Programme", ""]
    fit_md += [f"- {name}: {d['status']}" + (f" — {d['note']}" if d.get("note") else "") for name, d in (job.programme or {}).items()]
    fit_md += [f"- programme_overall: {job.programme_overall}", "", "## Skill comparison", "",
               "| skill | required/preferred | matching evidence ids | gap |", "|---|---|---|---|"]
    for skill, kind, ids in _skill_rows(extracted, config):
        fit_md.append(f"| {skill} | {kind} | {', '.join(ids) or '-'} | {'yes' if not ids else 'no'} |")
    fit_md += ["", "## Quality checklist", ""]
    if job.quality_checklist:
        fit_md += [f"- {s['signal']}: {s.get('present')}" + (f" ({s['note']})" if s.get("note") else "") for s in job.quality_checklist]
    else:
        fit_md.append("- not generated")
    fit_md += [f"- quality (user-set): {job.quality}", "", "## Strengths to lead with", ""]
    lines = strengths(extracted, config)
    fit_md += [f"- {line}" for line in lines] or ["- none matched; set fit manually after reading the JD"]
    fit_md.append("")

    steps = build_timeline(config.user_facts, config.constraints, job, when)
    checklist_md = [f"# Checklist: {job.display_title} @ {company}", "", "## Application steps", "",
                    f"1. Apply via: {extracted.application_method.value or 'not stated in JD'}",
                    "2. Attach the documents below and send the recruiter message yourself.",
                    "3. Record the application: ios job status <id> APPLIED --next \"...\" --due YYYY-MM-DD", "",
                    "## Referral status", "", f"- referral: {job.referral}",
                    f"- JD referral info: {extracted.referral_info.value or '-'}", "",
                    "## Documents to attach", "", "- 中文简历 (Chinese resume)", "- English resume",
                    f"- GitHub: {config.user_facts.github}", f"- LinkedIn: {config.user_facts.linkedin}", "",
                    "## Job-specific timeline", ""]
    checklist_md += render_timeline(steps, when)
    checklist_md += ["", f"**{top_line(steps, when)}**", ""]
    warnings = constraint_warnings(config.constraints, when)
    if warnings:
        checklist_md += ["## Programme constraint warnings", ""] + [f"- {w}" for w in warnings] + [""]

    files = {"job.md": "\n".join(job_md), "fit.md": "\n".join(fit_md), "checklist.md": "\n".join(checklist_md)}
    for name, content in files.items():
        (directory / name).write_text(content, encoding="utf-8")
    return PackResult(directory=directory, files=files)


# --------------------------------------------------------------------------------------
# ios job messages
# --------------------------------------------------------------------------------------

SECTION_ORDER = [
    ("recruiter_zh", "1. Recruiter message (中文)", "zh", True),
    ("recruiter_en", "2. Recruiter message (English)", "en", True),
    ("referral_zh", "3. Referral request (中文)", "zh", True),
    ("referral_en", "4. Referral request (English)", "en", True),
    ("yes_zh", "5. YES employer explanation (中文)", "zh", False),
    ("yes_en", "6. YES employer explanation (English)", "en", False),
]


@dataclass
class MessagesResult:
    directory: Path
    sections: dict[str, str]  # key -> rendered text (only successful sections)
    rejected: list[Rejection]
    failures: dict[str, str]  # key -> reason a section was not emitted
    content: str = ""


def allowed_yes_constraints(config: AppConfig) -> list[Any]:
    out = []
    for cid in YES_EXPLANATION_CONSTRAINTS:
        c = config.constraints.get(cid)
        if c is not None and c.status in ALLOWED_YES_STATUSES:
            out.append(c)
    return out


def _messages_call(variables: dict[str, Any], config: AppConfig, retry_error: str | None) -> MessagesOutput:
    if retry_error:
        variables = {**variables, "retry_note": f"Your previous draft was rejected: {retry_error}. Shorten accordingly."}
    else:
        variables = {**variables, "retry_note": ""}
    result = llm.complete("recruiter_message", variables, MessagesOutput, config=config)
    assert isinstance(result, MessagesOutput)
    return result


def generate_messages(job: Job, config: AppConfig, today: date | None = None) -> MessagesResult:
    extracted = _require_confirmed(job)
    directory = pack_dir(job, config.root)
    directory.mkdir(parents=True, exist_ok=True)
    rejected: list[Rejection] = []
    sections: dict[str, str] = {}
    failures: dict[str, str] = {}

    lo, hi = programme_interval(config.constraints)
    variables = {
        **_job_variables(job, extracted),
        "evidence_json": _evidence_json(config),
        "user_facts_json": _user_facts_json(config),
        "programme_duration_months": f"{lo} to {hi} months (SUTD_MIN_DURATION, YES_MAX_DURATION)",
        "mandarin_claim_zh": config.user_facts.mandarin_claim_zh,
        "mandarin_claim_en": config.user_facts.mandarin_claim_en,
        "limit_zh": LIMIT_ZH_CHARS,
        "limit_en": LIMIT_EN_WORDS,
    }

    def render_section(key: str, lang: str, draft: MessageDraft) -> tuple[str | None, str | None]:
        report = validate_statements(draft.statements, config)
        rejected.extend(report.rejected)
        if not report.kept:
            return None, "no valid statements remained after provenance validation"
        text = render_statements(report.kept)
        problem = length_problem(text, lang)
        return (None, problem) if problem else (text, None)

    output = _messages_call(variables, config, None)
    pending: dict[str, str] = {}
    for key, _, lang, limited in SECTION_ORDER:
        if not limited:
            continue
        text, problem = render_section(key, lang, getattr(output, key))
        if text is not None:
            sections[key] = text
        else:
            pending[key] = problem or "invalid"
    if pending:
        retry = _messages_call(variables, config, "; ".join(f"{k}: {v}" for k, v in pending.items()))
        for key, problem in pending.items():
            lang = next(l for k, _, l, _ in SECTION_ORDER if k == key)
            text, problem2 = render_section(key, lang, getattr(retry, key))
            if text is not None:
                sections[key] = text
            else:
                failures[key] = f"first attempt: {problem}; retry: {problem2}"

    # YES explanation from allowed constraint statements only.
    allowed = allowed_yes_constraints(config)
    yes_vars = {
        **_job_variables(job, extracted),
        "constraints_json": json.dumps(
            [{"constraint_id": c.constraint_id, "statement": c.statement} for c in allowed], ensure_ascii=False, indent=1
        ),
        "allowed_ids": ", ".join(c.constraint_id for c in allowed),
    }
    try:
        yes_out = llm.complete("yes_explanation", yes_vars, YesExplanationOutput, config=config)
        assert isinstance(yes_out, YesExplanationOutput)
        for key, draft in (("yes_zh", yes_out.zh), ("yes_en", yes_out.en)):
            report = validate_statements(draft.statements, config, allowed_constraint_ids=[c.constraint_id for c in allowed])
            rejected.extend(report.rejected)
            if report.kept:
                sections[key] = render_statements(report.kept)
            else:
                failures[key] = "no valid statements remained after provenance validation"
    except llm.LLMError as exc:
        failures["yes_zh"] = failures["yes_en"] = f"LLM failure: {exc}"

    lines = [f"# Messages: {job.display_title} @ {job.company.display_name if job.company else ''}", "",
             "Provenance tags are HTML comments; strip them before sending. Nothing is sent by this tool.", ""]
    for key, heading, _, _ in SECTION_ORDER:
        lines += [f"## {heading}", ""]
        if key in sections:
            lines += [sections[key], ""]
        else:
            lines += [f"NOT GENERATED: {failures.get(key, 'unknown')}", ""]
    if rejected:
        lines += ["## Refused statements", ""] + [f"- {r.line()}" for r in rejected] + [""]
    content = "\n".join(lines)
    (directory / "messages.md").write_text(content, encoding="utf-8")
    return MessagesResult(directory=directory, sections=sections, rejected=rejected, failures=failures, content=content)


# --------------------------------------------------------------------------------------
# ios job bullets
# --------------------------------------------------------------------------------------

_BULLET_ID = re.compile(r"\[(EV_[A-Z0-9_]+)\]\s*$")
_ANY_ID = re.compile(r"\[EV_[A-Z0-9_]+\]")
NO_DIGIT_EVIDENCE = frozenset({"EV_MINDEF_DB"})


@dataclass
class BulletsResult:
    directory: Path
    kept: list[str]
    rejected: list[Rejection]
    content: str = ""


def validate_bullet(bullet: str, config: AppConfig) -> str | None:
    """None when valid, else the reason."""
    text = bullet.strip()
    if len(_ANY_ID.findall(text)) != 1:
        return "must contain exactly one [EV_ID]"
    match = _BULLET_ID.search(text)
    if not match:
        return "must end with [EV_ID]"
    ev_id = match.group(1)
    if config.evidence.get(ev_id) is None:
        return f"unknown evidence id {ev_id}"
    if ev_id in NO_DIGIT_EVIDENCE and re.search(r"\d", text):
        return f"{ev_id} bullets may not contain any digit"
    problem = mandarin_problem(text, config.user_facts)
    if problem:
        return problem
    return None


def generate_bullets(job: Job, config: AppConfig) -> BulletsResult:
    extracted = _require_confirmed(job)
    directory = pack_dir(job, config.root)
    directory.mkdir(parents=True, exist_ok=True)
    variables = {
        **_job_variables(job, extracted),
        "evidence_json": _evidence_json(config),
        "min_bullets": MIN_BULLETS,
        "max_bullets": MAX_BULLETS,
    }
    output = llm.complete("tailor_bullets", variables, BulletsOutput, config=config)
    assert isinstance(output, BulletsOutput)
    kept: list[str] = []
    rejected: list[Rejection] = []
    for bullet in output.bullets:
        problem = validate_bullet(bullet, config)
        if problem:
            rejected.append(Rejection(bullet.strip(), problem))
        else:
            kept.append(bullet.strip())
    lines = [f"# Tailored resume bullets: {job.display_title}", ""] + [f"- {b}" for b in kept]
    if rejected:
        lines += ["", "## Dropped bullets", ""] + [f"- {r.text} — {r.reason}" for r in rejected]
    content = "\n".join(lines) + "\n"
    (directory / "bullets.md").write_text(content, encoding="utf-8")
    return BulletsResult(directory=directory, kept=kept, rejected=rejected, content=content)


# --------------------------------------------------------------------------------------
# ios job interview-prep
# --------------------------------------------------------------------------------------


@dataclass
class InterviewPrepResult:
    directory: Path
    technical: list[str]
    behavioural: list[str]
    evidence_ids: list[str]
    rejected: list[Rejection]
    content: str = ""


def generate_interview_prep(job: Job, config: AppConfig) -> InterviewPrepResult:
    if job.status != JobStatus.IN_PROCESS:
        raise DraftError(f"interview prep is only available when status is IN_PROCESS (job {job.id} is {job.status})")
    extracted = _require_confirmed(job)
    directory = pack_dir(job, config.root)
    directory.mkdir(parents=True, exist_ok=True)
    variables = {**_job_variables(job, extracted), "evidence_json": _evidence_json(config)}
    output = llm.complete("interview_prep", variables, InterviewPrepOutput, config=config)
    assert isinstance(output, InterviewPrepOutput)
    rejected: list[Rejection] = []
    evidence_ids = []
    for ev_id in output.evidence_to_rehearse:
        if config.evidence.get(ev_id) is None:
            rejected.append(Rejection(ev_id, "unknown evidence id"))
        elif ev_id not in evidence_ids:
            evidence_ids.append(ev_id)
    lines = [f"# Interview prep: {job.display_title}", "", "## Likely technical questions", ""]
    lines += [f"- {q}" for q in output.technical_questions] or ["- none"]
    lines += ["", "## Likely behavioural questions", ""]
    lines += [f"- {q}" for q in output.behavioural_questions] or ["- none"]
    lines += ["", "## Evidence to rehearse", ""]
    for ev_id in evidence_ids:
        item = config.evidence.get(ev_id)
        assert item is not None
        lines.append(f"- [{ev_id}] {item.title}: {' '.join(item.claims)}" + (f" (restriction: {item.restrictions})" if item.restrictions else ""))
    content = "\n".join(lines) + "\n"
    (directory / "interview-prep.md").write_text(content, encoding="utf-8")
    return InterviewPrepResult(directory=directory, technical=output.technical_questions,
                               behavioural=output.behavioural_questions, evidence_ids=evidence_ids,
                               rejected=rejected, content=content)
