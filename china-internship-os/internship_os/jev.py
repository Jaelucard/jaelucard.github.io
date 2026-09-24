"""Jev questions about a captured posting, the stored answers, and the notes they become.

Jev runs once after capture. Its answers are stored as a ``jev_suggestions`` job event and shown
as notes on the review page (and before ``ios confirm``). No eligibility, programme or tiering
rule reads them: they only point the user at fields worth a second look.

What is sent: the pasted posting text and a few extracted values derived from it. Nothing from
user_facts, drafts or skill evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from internship_os import resolve
from internship_os.config import AppConfig, ConfigError
from internship_os.decision_provider import (
    DecisionBatch,
    DecisionProvider,
    DecisionsConfig,
    NullProvider,
    ask_safely,
    get_provider,
    load_decisions,
    read_api_key,
)
from internship_os.models import Job, JobEvent
from internship_os.schemas import EventKind, ExtractedJob
from internship_os.services.review import display

# Jev question key -> the extracted field its answer is compared with.
CHOICE_FIELDS = {
    "track": "track_guess",
    "degree": "degree_required",
    "chinese_level": "chinese_required_level",
    "start_timing": "start_timing",
}
FLAG_FIELDS = {"pays_fee": "pays_fee", "mostly_annotation": "mostly_annotation", "mostly_sales": "mostly_sales"}
WARNINGS = {
    "pays_fee": "The posting may ask you to pay a fee, deposit or training cost",
    "mostly_annotation": "The work may be mainly data labelling rather than engineering",
    "mostly_sales": "The work may be mainly sales or customer acquisition",
}
# Fields a gate reads that no question above covers, minus numbers and dates (code checks those).
CHECKED_FIELDS = ("graduation_cohort_text", "cohort_unrestricted", "role_closed", "internship_type", "research_signals")
FIELD_MEANINGS = {
    "graduation_cohort_text": "the graduation cohorts (届) the posting accepts",
    "cohort_unrestricted": "the posting explicitly accepts any graduation year (毕业时间不限)",
    "role_closed": "the posting says the position is closed or already filled",
    "internship_type": "the internship type, such as 日常实习 or 暑期实习",
    "research_signals": "research signals: a required master's or PhD, publications, CUDA, large-scale training",
}


def _choice(instructions: str, criteria: dict[str, str]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def _noul(instructions: str, true: str, false: str) -> dict[str, Any]:
    return {"type": "noul", "instructions": instructions, "criteria": {"true": true, "false": false}}


def posting_questions() -> dict[str, dict[str, Any]]:
    """Questions about the posting itself. Labels are the repo's own vocabularies."""
    return {
        "track": _choice("Which kind of role does `posting` describe?", {
            "AI": "Builds, trains, evaluates or deploys machine-learning models or LLM applications (大模型应用, 算法, 智能体)",
            "SWE": "Backend, frontend, full-stack, mobile or infrastructure software work without an ML focus (后端, 前端, 测试开发)",
            "research": "Centred on algorithm research, papers or model-training research (算法研究, 论文)",
            "other": "Not a software role: sales, operations, product, data labelling or similar",
        }),
        "degree": _choice("What minimum degree does `posting` require?", {
            "none_stated": "No degree requirement, or any degree accepted (学历不限)",
            "bachelor": "A bachelor's degree or current bachelor's study (本科及以上, 本科在读)",
            "master": "A master's degree or higher (硕士及以上, 研究生)",
            "phd": "A PhD (博士)",
        }),
        "chinese_level": _choice("What Chinese language level does `posting` require?", {
            "none_stated": "No Chinese language requirement is stated",
            "basic": "Basic Chinese (基础)",
            "working": "Chinese as a working language (可作为工作语言)",
            "fluent": "Fluent Chinese (流利, 精通)",
            "native": "Native Chinese (母语)",
        }),
        "start_timing": _choice("When does `posting` want the intern to start?", {
            "asap": "As soon as possible or immediately (尽快到岗, 随时到岗)",
            "named_month": "A named start month or date (2027年3月起)",
            "flexible": "The start date is negotiable (到岗时间可协商)",
            "not_stated": "It does not say when to start",
        }),
        "restricted": _noul(
            "Does `posting` restrict applicants by nationality or citizenship, require a mainland Chinese ID, "
            "or refuse work authorisation or visa sponsorship?",
            true="It states such a restriction",
            false="It states no such restriction, including when it says nothing about nationality, ID or visas",
        ),
        "pays_fee": _noul(
            "Does `posting` ask the applicant to pay any fee, deposit or training cost?",
            true="It asks the applicant to pay",
            false="It asks for no payment, including when it says nothing about payment",
        ),
        "mostly_annotation": _noul(
            "Is the main daily work in `posting` data labelling or annotation rather than engineering?",
            true="Mainly labelling or annotation, even under an AI or algorithm title",
            false="Mainly engineering or other technical work",
        ),
        "mostly_sales": _noul(
            "Is the main daily work in `posting` sales, promotion or customer acquisition?",
            true="Mainly sales, promotion or customer acquisition",
            false="Mainly technical work",
        ),
    }


def _is_empty(name: str, value: Any) -> bool:
    return value in (None, "", []) or value == ExtractedJob().get(name).value


def check_questions(extracted: ExtractedJob) -> dict[str, dict[str, Any]]:
    """One support check per field in CHECKED_FIELDS, phrased for a found or a missing value.

    Yes/no fields are asked as conditions ("does the posting say X?"), not as "is there information
    about X?", which a posting listing its cohorts would answer yes for cohort_unrestricted.
    """
    questions: dict[str, dict[str, Any]] = {}
    for name in CHECKED_FIELDS:
        value = extracted.get(name).value
        if ExtractedJob.inner_type(name) is bool:
            if value is True:
                questions[f"check__{name}"] = _noul(
                    f"The extraction says this is true: `fields.{name}.meaning`. Is that unsupported by `posting`?",
                    true="Unsupported: the posting does not say this",
                    false="Supported: the posting says this",
                )
            else:
                questions[f"check__{name}"] = _noul(
                    f"Does `posting` say this: `fields.{name}.meaning`?",
                    true="Yes, the posting states this",
                    false="No, the posting does not state this",
                )
            continue
        if _is_empty(name, value):
            questions[f"check__{name}"] = _noul(
                f"Nothing was extracted for `fields.{name}.meaning`. Does `posting` state this information?",
                true="The posting states this information",
                false="The posting does not state it",
            )
        else:
            questions[f"check__{name}"] = _noul(
                f"`fields.{name}.value` was extracted from `posting` as `fields.{name}.meaning`. "
                "Is that value unsupported by `posting`, or different from what it says?",
                true="Unsupported or different: the posting does not say this",
                false="Supported: the posting says this",
            )
    return questions


def all_questions(extracted: ExtractedJob) -> dict[str, dict[str, Any]]:
    return {**posting_questions(), **check_questions(extracted)}


def build_state(raw_text: str, extracted: ExtractedJob) -> dict[str, Any]:
    return {
        "posting": raw_text,
        "fields": {
            name: {"meaning": FIELD_MEANINGS[name], "value": display(extracted.get(name).value)}
            for name in CHECKED_FIELDS
        },
    }


# --------------------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------------------


# Bump when a question's wording or meaning changes: stored answers to other versions are not read.
QUESTIONS_VERSION = 2


@dataclass
class Outcome:
    state: str  # "on" | "off" | "failed"
    model: str | None
    detail: str | None = None  # why it is off, or the error class
    answers: int = 0


def record_detail(batch: DecisionBatch | None, *, error: str | None, model: str | None = None, asked: int = 0) -> dict[str, Any]:
    return {
        "version": QUESTIONS_VERSION,
        "model": batch.model if batch is not None else model,
        "error": error,
        "asked": asked,
        "decisions": {k: asdict(d) for k, d in batch.decisions.items()} if batch is not None else {},
    }


def _store(session: Session, job: Job, detail: dict[str, Any]) -> str | None:
    """Save the record as a job event. Returns the error class name instead of raising."""
    try:
        session.add(JobEvent(job_id=job.id, kind=EventKind.jev_suggestions.value, detail=detail))
        session.commit()
        return None
    except Exception as exc:  # noqa: BLE001 - the capture is already saved; losing the notes is acceptable
        session.rollback()
        return type(exc).__name__


def record_suggestions(session: Session, job: Job, config: AppConfig, *, provider: DecisionProvider | None = None) -> Outcome:
    """Ask Jev about ``job``'s posting and store the answers. Never raises: capture must not fail.

    Failures are stored too, so the review page can say that Jev could not check this posting.
    """
    try:
        provider = provider if provider is not None else get_provider(config)
    except Exception as exc:  # noqa: BLE001 - a bad key or config must not stop a capture
        error = type(exc).__name__
        _store(session, job, record_detail(None, error=error))
        return Outcome("failed", None, error)
    if isinstance(provider, NullProvider):
        return Outcome("off", None, provider.reason)
    if not job.extracted or not job.raw_text:
        return Outcome("off", None, "nothing to check")
    try:
        extracted = ExtractedJob.model_validate(job.extracted)
        state, questions = build_state(job.raw_text, extracted), all_questions(extracted)
    except Exception as exc:  # noqa: BLE001
        error = type(exc).__name__
        _store(session, job, record_detail(None, error=error, model=provider.model))
        return Outcome("failed", provider.model, error)
    batch, error = ask_safely(provider, state, questions)
    if batch is not None and not batch.decisions and error is None:
        error = "no usable answers"
    detail = record_detail(batch, error=error, model=provider.model, asked=len(questions))
    write_error = _store(session, job, detail)
    if write_error:
        return Outcome("failed", detail["model"], write_error)
    return Outcome("failed" if error else "on", detail["model"], error, len(detail["decisions"]))


def latest_record(job: Job) -> dict[str, Any] | None:
    for event in reversed(job.events):
        if event.kind == EventKind.jev_suggestions.value and isinstance(event.detail, dict):
            return event.detail
    return None


def status(config: AppConfig) -> str:
    """One line for the review page and ``ios llm-check``. Builds no client and sends nothing."""
    try:
        decisions = load_decisions(config.root)
    except ConfigError:
        return "off (config/decisions.yaml is invalid; run ios llm-check for details)"
    if decisions.provider != "typesafe":
        return "off (provider: none in config/decisions.yaml)"
    if not read_api_key(config.root):
        return "off (no TYPESAFE_API_KEY in the environment or .env)"
    return f"on ({decisions.model})"


# --------------------------------------------------------------------------------------
# Answers -> review notes
# --------------------------------------------------------------------------------------


@dataclass
class JevView:
    model: str | None
    error: str | None
    notes: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    asked: int = 0
    answered: int = 0


def _expected_kind(key: str) -> str | None:
    if key.startswith("check__") or key == "restricted" or key in FLAG_FIELDS:
        return "noul"
    return "choice" if key in CHOICE_FIELDS else None


def _usable(key: str, d: Any) -> bool:
    """A stored answer of the kind its question expects, with a value of the right type."""
    if not isinstance(d, dict) or d.get("kind") != _expected_kind(key):
        return False
    value = d.get("value")
    if d["kind"] == "noul":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, str) and isinstance(d.get("confidence"), (int, float))


def interpret(record: dict[str, Any], extracted: ExtractedJob, cfg: DecisionsConfig) -> JevView:
    """Turn stored answers into per-field notes and posting warnings, using the two thresholds."""
    model = record.get("model")
    decisions = {k: d for k, d in (record.get("decisions") or {}).items() if _usable(k, d)}
    asked = int(record.get("asked") or 0)
    if record.get("version") != QUESTIONS_VERSION:
        return JevView(model, f"its answers were given to an older question set (version {record.get('version')})", asked=asked)
    notes: dict[str, list[str]] = {}
    warnings: list[str] = []
    yes, no = cfg.noul_flag_p, 1 - cfg.noul_flag_p

    def note(name: str, text: str) -> None:
        notes.setdefault(name, []).append(text)

    for key, name in CHOICE_FIELDS.items():
        d = decisions.get(key)
        if not d:
            continue
        confidence = float(d["confidence"])
        if confidence < cfg.choice_min_confidence:
            note(name, f"Jev is unsure (leans {d['value']}, confidence {confidence:.2f})")
        elif d["value"] != display(extracted.get(name).value):
            note(name, f"Jev suggests {d['value']} (confidence {confidence:.2f})")

    d = decisions.get("restricted")
    if d:
        extracted_restriction = bool(extracted.nationality_or_work_auth_restriction.value)
        if d["value"] >= yes and not extracted_restriction:
            note("nationality_or_work_auth_restriction",
                 f"Jev: the posting may restrict nationality, ID or visas (P={d['value']:.2f}); nothing was extracted")
        elif d["value"] <= no and extracted_restriction:
            note("nationality_or_work_auth_restriction", f"Jev found no such restriction in the posting (P={d['value']:.2f})")

    for key, name in FLAG_FIELDS.items():
        d = decisions.get(key)
        if not d:
            continue
        extracted_value = extracted.get(name).value
        if d["value"] >= yes:
            warnings.append(f"{WARNINGS[key]} (Jev, P={d['value']:.2f}).")
            if extracted_value is not True:
                note(name, f"Jev says yes (P={d['value']:.2f})")
        elif d["value"] <= no and extracted_value is True:
            note(name, f"Jev says no (P={d['value']:.2f})")

    for name in CHECKED_FIELDS:
        d = decisions.get(f"check__{name}")
        if not d or d["value"] < yes:
            continue
        if ExtractedJob.inner_type(name) is bool and extracted.get(name).value is not True:
            note(name, f"Jev: this may be true: {FIELD_MEANINGS[name]} (P={d['value']:.2f})")
        elif _is_empty(name, extracted.get(name).value):
            note(name, f"Jev: the posting may state {FIELD_MEANINGS[name]} (P={d['value']:.2f})")
        else:
            note(name, f"Jev: the posting may not support this value (P={d['value']:.2f})")

    return JevView(model, record.get("error"), notes, warnings, asked=asked, answered=len(decisions))


def review_notes(job: Job, extracted: ExtractedJob, config: AppConfig) -> tuple[JevView | None, dict[str, list[str]]]:
    """Jev's stored answers and the regex cross-checks as notes per field, for the web review and
    ``ios confirm``. Nothing here is sent anywhere, and nothing it returns changes a value."""
    view: JevView | None = None
    record = latest_record(job)
    if record is not None:
        try:
            view = interpret(record, extracted, load_decisions(config.root))
        except ConfigError:
            view = JevView(record.get("model"), "config/decisions.yaml is invalid")
        except Exception:  # noqa: BLE001 - unreadable stored answers must not break the review
            view = JevView(record.get("model"), "its stored answers could not be read")
    notes = {name: list(items) for name, items in (view.notes if view else {}).items()}
    for name, text in resolve.cross_check(job.raw_text or "", extracted).items():
        notes.setdefault(name, []).append(text)
    return view, notes
