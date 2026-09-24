"""Regex cross-checks for numbers and dates in the posting text.

Used on the review page only: when the posting text states a duration, a start month or days per
week that differs from the extracted value, that field gets a note. Nothing here sets a value or
feeds eligibility, programme or tiering.
"""

from __future__ import annotations

import re

from internship_os.schemas import ExtractedJob

_CN_NUMBERS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
               "十": 10, "十一": 11, "十二": 12}
NUM = r"(\d{1,2}|十[一二]?|[一二两三四五六七八九])"
DASH = r"\s*(?:-|~|～|—|–|至|到)\s*"
# A month followed by joining wording is a start date, not a duration ("3月入职", "3-4月到岗").
_NOT_START = r"(?!\s*(?:份|初|中|底)?\s*(?:起|开始|前)?\s*可?\s*(?:入职|到岗))"


def _number(token: str) -> int | None:
    return int(token) if token.isdigit() else _CN_NUMBERS.get(token)


_DURATION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"{NUM}\s*(?:个月|月)?{DASH}{NUM}\s*个?月{_NOT_START}"), "range"),
    (re.compile(r"(\d{1,2})\s*(?:-|~|to)\s*(\d{1,2})\s*months?", re.IGNORECASE), "range"),
    (re.compile(rf"(?:至少|最少|不少于|不低于)\s*(?:实习)?\s*{NUM}\s*个月"), "minimum"),
    (re.compile(rf"{NUM}\s*个月\s*(?:及)?以上"), "minimum"),
    (re.compile(r"(?:minimum|at\s+least)\s*(?:of\s*)?(\d{1,2})\s*months?", re.IGNORECASE), "minimum"),
    (re.compile(r"(?:至少|最少|不少于)\s*(?:实习)?\s*半年|半年(?:及)?以上"), "half_year"),
    (re.compile(rf"(?:固定|为期)\s*{NUM}\s*个月"), "fixed"),
    (re.compile(r"(\d{1,2})[- ]month", re.IGNORECASE), "fixed"),
]


def duration_months(text: str) -> tuple[int, int | None] | None:
    """(minimum, maximum) months stated in ``text``; maximum None for "at least N". None if absent."""
    for pattern, kind in _DURATION_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        if kind == "half_year":
            return 6, None
        first = _number(match.group(1))
        if first is None:
            continue
        if kind == "range":
            second = _number(match.group(2))
            if second is not None:
                return first, second
        elif kind == "minimum":
            return first, None
        else:
            return first, first
    return None


_DAYS_PATTERNS = [
    re.compile(rf"(?:每周|一周)\s*(?:到岗|实习|工作|出勤|至少|最少|不少于)*\s*{NUM}\s*(?:{DASH}{NUM})?\s*天"),
    re.compile(rf"{NUM}\s*天\s*/\s*周"),
    re.compile(r"(?:at\s+least\s*)?(\d)\s*days?\s*(?:a|per|/)\s*week", re.IGNORECASE),
]


def days_per_week(text: str) -> int | None:
    """The minimum days per week stated in ``text``, or None."""
    for pattern in _DAYS_PATTERNS:
        match = pattern.search(text)
        if match:
            value = _number(match.group(1))
            if value is not None and 1 <= value <= 7:
                return value
    return None


MONTH = r"(\d{1,2}|十[一二]?|[一二三四五六七八九])"
_START_PATTERNS = [
    re.compile(rf"(?:(\d{{4}})\s*年\s*)?{MONTH}\s*月(?:份)?(?:\s*\d{{1,2}}\s*[日号])?\s*(?:初|中|底)?\s*(?:起)?\s*(?:可)?\s*(?:入职|到岗)"),
    re.compile(rf"(?:入职|到岗)(?:时间|日期)?\s*[:：]\s*(?:(\d{{4}})\s*年\s*)?{MONTH}\s*月"),
]


def start_month(text: str) -> tuple[int | None, int] | None:
    """(year or None, month) of a stated start, or None."""
    for pattern in _START_PATTERNS:
        match = pattern.search(text)
        if match:
            month = _number(match.group(2))
            if month is not None and 1 <= month <= 12:
                return (int(match.group(1)) if match.group(1) else None), month
    return None


def _months(value: tuple[int, int | None]) -> str:
    low, high = value
    if high is None:
        return f"at least {low} months"
    return f"{low} months" if low == high else f"{low}-{high} months"


def cross_check(text: str, extracted: ExtractedJob) -> dict[str, str]:
    """Notes for fields whose extracted value differs from what the posting text states."""
    notes: dict[str, str] = {}
    duration = duration_months(text)
    if duration is not None:
        low, high = duration
        said = f"The posting text reads as {_months(duration)}"
        if low != extracted.duration_min_months.value:
            notes["duration_min_months"] = f"{said}; the extraction has {extracted.duration_min_months.value}."
        if high is not None and high != extracted.duration_max_months.value:
            notes["duration_max_months"] = f"{said}; the extraction has {extracted.duration_max_months.value}."
    days = days_per_week(text)
    if days is not None and days != extracted.days_per_week_min.value:
        notes["days_per_week_min"] = f"The posting text says {days} days a week; the extraction has {extracted.days_per_week_min.value}."
    start = start_month(text)
    if start is not None:
        year, month = start
        stated = f"{year}-{month:02d}" if year else f"month {month}"
        current = extracted.start_date.value
        if current is None or current.month != month or (year is not None and current.year != year):
            notes["start_date"] = f"The posting text mentions a start in {stated}; the extraction has {current}."
    return notes
