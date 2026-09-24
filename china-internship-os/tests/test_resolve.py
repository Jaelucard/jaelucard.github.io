"""Regex cross-checks shown on the review page. They only add notes; they never set a value."""

from __future__ import annotations

from datetime import date

import pytest

from internship_os import resolve
from tests.conftest import load_extracted


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("实习4-6个月", (4, 6)),
        ("实习时间：4个月-6个月", (4, 6)),
        ("实习周期3~6月", None),  # a bare 月 is a calendar month: "3~6月" may mean March to June
        ("实习4—6个月", (4, 6)),
        ("实习期3个月以上", (3, None)),
        ("至少实习3个月", (3, None)),
        ("实习三个月以上", (3, None)),
        ("实习期至少半年", (6, None)),
        ("实习期固定3个月", (3, 3)),
        ("Minimum 3 months", (3, None)),
        ("6-month internship", (6, 6)),
        ("3~6 months", (3, 6)),
        ("3月入职，每周4天", None),
    ],
)
def test_duration_months(text, expected):
    assert resolve.duration_months(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("每周到岗4天", 4),
        ("每周至少四天", 4),
        ("一周至少3天", 3),
        ("4天/周", 4),
        ("每周3-5天", 3),
        ("5 days a week", 5),
        ("at least 4 days per week", 4),
        ("实习4-6个月", None),
    ],
)
def test_days_per_week(text, expected):
    assert resolve.days_per_week(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2027年3月起可入职", (2027, 3)),
        ("可3月入职优先", (None, 3)),
        ("入职时间：2027年3月", (2027, 3)),
        ("3月份到岗", (None, 3)),
        ("可尽快到岗", None),
    ],
)
def test_start_month(text, expected):
    assert resolve.start_month(text) == expected


def test_cross_check_flags_a_duration_that_differs_from_the_text():
    extracted = load_extracted("hangzhou_ai_app")  # 4-6 months, 4 days, start 2027-03-01
    notes = resolve.cross_check("实习6-12个月，每周4天，2027年3月起可入职", extracted)
    assert set(notes) == {"duration_min_months", "duration_max_months"}
    assert "6" in notes["duration_min_months"]


def test_cross_check_is_silent_when_text_and_extraction_agree():
    extracted = load_extracted("hangzhou_ai_app")
    assert resolve.cross_check("实习4-6个月，每周到岗4天，2027年3月起可入职", extracted) == {}


def test_cross_check_is_silent_when_the_text_has_nothing_to_compare():
    extracted = load_extracted("hangzhou_ai_app")
    assert resolve.cross_check("负责RAG检索链路开发", extracted) == {}


def test_cross_check_flags_a_start_month_that_differs():
    extracted = load_extracted("hangzhou_ai_app")
    extracted.start_date.value = date(2027, 3, 1)
    notes = resolve.cross_check("2027年6月入职", extracted)
    assert "start_date" in notes and "2027-06" in notes["start_date"]


@pytest.mark.parametrize(
    "text",
    [
        "实习时间：2027年3月至8月",
        "实习时间：3月-6月",
        "暑期实习（6-8月）",
        "2027年3-6月实习",
        "能在1-2个月内到岗",
        "试用期1-3个月",
        "Stipend: RMB 8000 monthly",
        "Salary 4000 month",
        "Reply within 2 months",
    ],
)
def test_dates_salaries_and_windows_are_not_durations(text):
    assert resolve.duration_months(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [("3 months minimum", (3, None)), ("3 months or longer", (3, None)), ("Duration: 6 months", (6, 6))],
)
def test_english_minimum_and_plain_durations(text, expected):
    assert resolve.duration_months(text) == expected


def test_a_days_range_gives_its_minimum():
    assert resolve.days_per_week("3-5 days per week") == 3


@pytest.mark.parametrize("text", ["3月或4月入职", "2027年1-3月入职"])
def test_two_start_months_give_no_single_start(text):
    assert resolve.start_month(text) is None


def test_missing_extracted_values_read_as_nothing():
    extracted = load_extracted("hangzhou_ai_app")
    extracted.start_date.value = None
    notes = resolve.cross_check("2027年3月起可入职", extracted)
    assert "None" not in notes["start_date"] and "nothing" in notes["start_date"]
