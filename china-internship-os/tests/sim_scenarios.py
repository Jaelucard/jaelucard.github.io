"""Scenario data and the shared runner for the lead-scan simulation.

Two entry points use this module: ``scripts/simulate.py`` (a temporary project root, a fake LLM
provider, a printed report) and ``tests/test_simulation.py`` (the same scenarios under pytest with
the repo fixtures). Nothing here reaches the network or an LLM.

Each scenario is a short Chinese posting built on the structure of
``tests/fixtures/jds/hangzhou_ai_app.txt`` plus extraction overrides applied to
``tests/fixtures/extracted/hangzhou_ai_app.json``. Every source span in the resulting extraction,
base or override, must be a verbatim substring of the scenario's posting; ``Scenario.extraction``
raises otherwise. Each scenario has its own company so that the shared database of a scripted run
never trips the company + title + city duplicate check.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from internship_os.capture import (
    MIN_USEFUL_CHARS,
    POST_CONFIRM_NEXT_ACTION,
    CaptureNeedsPaste,
    DuplicateCaptureNeedsDecision,
    apply_confirmation,
    attach_to_existing,
    capture,
    create_company_from_extraction,
    fetch_url_text,
    find_company_matches,
    find_duplicate_ids,
    refresh_display_fields,
)
from internship_os.cli import app as cli_app
from internship_os.config import USER_FACTS_EXAMPLE_FILE, USER_FACTS_FILE, AppConfig
from internship_os.eligibility import HARD_FAIL_CODES
from internship_os.models import Company, Job, utcnow
from internship_os.pipeline import (
    finalize_confirmation,
    recompute_all,
    recompute_job,
    set_agreed_dates,
    set_fit,
    set_quality,
    transition,
)
from internship_os.schemas import ALWAYS_CONFIRM_FIELDS, ExtractedJob
from internship_os.services import review as review_service
from internship_os.tiering import sort_jobs

TODAY = date(2026, 10, 1)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
BASE_EXTRACTION_FILE = FIXTURES_DIR / "extracted" / "hangzhou_ai_app.json"
BASE_JD_FILE = FIXTURES_DIR / "jds" / "hangzhou_ai_app.txt"
HTML_DIR = FIXTURES_DIR / "html"
SHIXISENG_FIXTURE = HTML_DIR / "shixiseng_detail.html"
YES_FIXTURE = HTML_DIR / "yes_posting.html"

BASE_EXTRACTION: dict[str, Any] = json.loads(BASE_EXTRACTION_FILE.read_text(encoding="utf-8"))

# Where each part's behaviour comes from, printed next to a failing row.
WHERE_ELIGIBILITY = "internship_os/eligibility.py run_eligibility"
WHERE_PROGRAMME = "internship_os/programme.py duration_and_dates"
WHERE_PIPELINE = "internship_os/pipeline.py finalize_confirmation"
WHERE_ADDED_FIELDS = "internship_os/schemas.py ExtractedJob._added_fields_default_to_not_captured"
WHERE_AGREED = "internship_os/pipeline.py set_agreed_dates / recompute_all"
WHERE_SORT = "internship_os/tiering.py sort_jobs"
WHERE_JOB_LIST = "internship_os/cli.py job_list"
WHERE_FETCH = "internship_os/capture.py fetch_url_text"
WHERE_DUPLICATES = "internship_os/capture.py find_duplicate_ids / normalise_source_url"
WHERE_ATTACH = "internship_os/capture.py attach_to_existing"
WHERE_CLI = "internship_os/cli.py"
WHERE_RECOMPUTE = "internship_os/cli.py recompute / internship_os/pipeline.py recompute_all"
WHERE_WEB = "internship_os/web/routes.py"
WHERE_WEB_SECURITY = "internship_os/web/app.py same_origin_writes"


# --------------------------------------------------------------------------------------
# The simulation's user facts
# --------------------------------------------------------------------------------------

USER_FACTS_OVERRIDES: dict[str, Any] = {
    "graduation_cohort": "2028届",
    "expected_graduation": "2028-05",
    "mandarin_level": "professional_working_non_native",
    "internship": {
        "intended_start": date(2027, 2, 15),
        "latest_end": date(2027, 8, 31),
        "min_months": 4,
        "max_months": 6,
        "host_type_preference": ["startup", "subsidiary", "large", "mnc", "unknown"],
        "track_preference": ["AI", "AUTO", "SWE", "other"],
        "offer_deadline_personal": date(2026, 12, 4),
    },
}


def write_user_facts(cfg_dir: Path) -> Path:
    """Write ``<cfg_dir>/user_facts.yaml``: the example file with the simulation's overrides."""
    data = yaml.safe_load((cfg_dir / USER_FACTS_EXAMPLE_FILE).read_text(encoding="utf-8"))
    for key, value in USER_FACTS_OVERRIDES.items():
        data[key] = {**data[key], **value} if isinstance(value, dict) else value
    target = cfg_dir / USER_FACTS_FILE
    target.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return target


# --------------------------------------------------------------------------------------
# Postings: the hangzhou fixture's structure with replaceable lines
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Role:
    """The role-specific lines of a posting and the extraction values they support."""

    duties: tuple[str, ...]
    skills_line: str
    required_skills: tuple[str, ...]
    bonus_line: str  # the 加分项 line, always the last requirement, without its full stop
    preferred_skills: tuple[str, ...]


ROLE_AI = Role(
    duties=(
        "参与基于大语言模型的企业知识问答产品开发，负责RAG检索链路与Prompt工程",
        "使用Python与FastAPI开发后端服务和内部工具，编写单元测试并参与代码评审",
        "与算法同学协作完成模型评测与效果分析，输出评测报告",
        "参与需求讨论，推动功能从原型到上线",
    ),
    skills_line="熟悉Python，了解LLM应用开发（LangChain/LlamaIndex等）",
    required_skills=("Python", "LLM应用开发（LangChain/LlamaIndex等）", "FastAPI", "RAG检索链路与Prompt工程", "单元测试"),
    bonus_line="加分项：有RAG或Agent项目经验，熟悉PyTorch",
    preferred_skills=("RAG或Agent项目经验", "PyTorch"),
)
ROLE_BACKEND = Role(
    duties=(
        "参与SaaS平台后端服务的开发，使用Go或Java编写业务接口",
        "参与MySQL与Redis相关的数据模型设计与性能优化",
        "编写单元测试与接口文档，配合测试同学完成上线",
    ),
    skills_line="熟悉Go或Java中的一种，了解HTTP、RESTful API与常见数据结构",
    required_skills=("Go或Java", "HTTP", "RESTful API", "数据结构"),
    bonus_line="加分项：了解Docker与Kubernetes",
    preferred_skills=("Docker", "Kubernetes"),
)
ROLE_PYTHON_BACKEND = Role(
    duties=(
        "参与数据平台后端服务的开发，使用Python与FastAPI编写接口",
        "参与任务调度与数据同步模块的维护",
        "编写单元测试并参与代码评审",
    ),
    skills_line="熟悉Python，了解FastAPI或Django",
    required_skills=("Python", "FastAPI或Django"),
    bonus_line="加分项：了解PostgreSQL与消息队列",
    preferred_skills=("PostgreSQL", "消息队列"),
)
ROLE_SALES = Role(
    duties=(
        "负责AI产品的电话销售与客户拓展，完成月度销售指标",
        "整理客户需求并跟进商机，维护客户关系",
        "协助市场活动执行与产品演示",
    ),
    skills_line="沟通表达能力强，有销售或客户服务经验优先",
    required_skills=("沟通表达能力",),
    bonus_line="加分项：了解SaaS产品或AI行业",
    preferred_skills=("SaaS产品或AI行业",),
)
ROLE_FRONTEND = Role(
    duties=(
        "参与企业管理后台前端页面的开发与维护",
        "与设计和后端同学协作完成需求，保证页面性能与兼容性",
        "编写组件文档与前端单元测试",
    ),
    skills_line="熟悉JavaScript与React，了解TypeScript",
    required_skills=("JavaScript", "React", "TypeScript"),
    bonus_line="加分项：有开源项目或个人作品",
    preferred_skills=("开源项目或个人作品",),
)
ROLE_AUTO = Role(
    duties=(
        "参与自动驾驶感知模块的开发，负责激光雷达与摄像头的3D目标检测算法",
        "使用PyTorch训练与评测感知模型，并在车载平台上部署",
        "参与路测数据的分析与问题定位",
    ),
    skills_line="熟悉Python与C++，了解PyTorch与3D目标检测",
    required_skills=("Python", "C++", "PyTorch", "3D目标检测"),
    bonus_line="加分项：有自动驾驶或机器人项目经验",
    preferred_skills=("自动驾驶或机器人项目经验",),
)
ROLE_CHASSIS = Role(
    duties=(
        "参与汽车底盘结构件的设计与图纸绘制",
        "使用CATIA完成零部件建模与装配校核",
        "配合试验部门完成结构强度验证",
    ),
    skills_line="熟悉CATIA或CAD制图，了解汽车底盘结构基础",
    required_skills=("CATIA", "CAD制图", "汽车底盘结构基础"),
    bonus_line="加分项：有整车或零部件企业实习经历",
    preferred_skills=("整车或零部件企业实习经历",),
)

COHORT_LINE = "2027届/2028届本科及以上在校生，计算机、软件工程等相关专业"
SCHEDULE_LINE = "每周4天以上，实习4至6个月，2027年3月起可入职"
SALARY_LINE = "薪资：300-400元/天"
BASE_COMPANY = "杭州星河智能科技有限公司"
BASE_EMAIL = "hr@xinghe-example.com"


def _numbered(items: tuple[str, ...]) -> str:
    lines = []
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item}{'。' if index == len(items) else '；'}")
    return "\n".join(lines)


def posting(
    company: str,
    title: str,
    *,
    kind: str = "日常实习",
    location: str = "杭州市 西湖区",
    role: Role = ROLE_AI,
    cohort_line: str = COHORT_LINE,
    schedule_line: str = SCHEDULE_LINE,
    extra_lines: tuple[str, ...] = (),
    salary_line: str = SALARY_LINE,
    email: str = BASE_EMAIL,
    tail: tuple[str, ...] = (),
) -> str:
    """A posting in the hangzhou fixture's layout; with the defaults it is that fixture."""
    requirements = (cohort_line, role.skills_line, schedule_line, *extra_lines, role.bonus_line)
    body = [
        company,
        f"{title}（{kind}）",
        "",
        f"工作地点：{location}",
        "",
        "岗位职责：",
        _numbered(role.duties),
        "",
        "任职要求：",
        _numbered(requirements),
        "",
        salary_line,
        f"投递方式：通过实习僧投递，或发送简历至 {email}",
        *tail,
    ]
    return "\n".join(body) + "\n"


# --------------------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------------------

Overrides = dict[str, tuple[Any, str | None]]  # field -> (value, verbatim source span)


@dataclass
class Expected:
    eligibility: tuple[str, ...] = ()  # accepted values; empty = not checked
    not_ineligible: bool = False
    evaluated: bool = False  # eligibility must not be NOT_RUN
    no_hard_fail: bool = False
    codes_include: tuple[str, ...] = ()
    codes_exclude: tuple[str, ...] = ()
    status: str | None = None
    tier: str | None = None
    track: str | None = None
    next_action_contains: str | None = None
    dimensions: dict[str, str] = field(default_factory=dict)  # programme dimension -> status
    note_contains: dict[str, str] = field(default_factory=dict)  # programme dimension -> text
    confirmed_nulls: tuple[str, ...] = ()  # extracted fields that must load as confirmed None

    def describe(self) -> str:
        parts: list[str] = []
        if self.eligibility:
            parts.append("eligibility " + " or ".join(self.eligibility))
        if self.not_ineligible:
            parts.append("not INELIGIBLE")
        if self.evaluated:
            parts.append("eligibility evaluated")
        if self.no_hard_fail:
            parts.append("no hard-fail code")
        if self.codes_include:
            parts.append("codes include " + ", ".join(self.codes_include))
        if self.codes_exclude:
            parts.append("codes exclude " + ", ".join(self.codes_exclude))
        if self.status:
            parts.append(f"status {self.status}")
        if self.tier:
            parts.append(f"tier {self.tier}")
        if self.track:
            parts.append(f"track {self.track}")
        if self.next_action_contains:
            parts.append(f"next_action contains '{self.next_action_contains}'")
        for name, status in self.dimensions.items():
            parts.append(f"{name} {status}")
        for name, text in self.note_contains.items():
            parts.append(f"{name} note names {text}")
        if self.confirmed_nulls:
            parts.append("confirmed null: " + ", ".join(self.confirmed_nulls))
        return "; ".join(parts)


@dataclass
class Scenario:
    id: str
    summary: str
    jd: str
    overrides: Overrides
    expected: Expected
    where: str
    source: str = "shixiseng"
    stored_row: bool = False  # S22: inserted as a row stored before the added fields existed
    # A mismatch the product produces today against the spec's literal expectation: the scripted
    # run reports the row as FAIL with the diagnosis, and pytest tolerates exactly that mismatch.
    known_failure: str | None = None
    diagnosis: str | None = None  # for a FAIL row: whether the code or the expectation is wrong

    def extraction(self) -> dict[str, Any]:
        """The base extraction with this scenario's overrides, every span checked against the JD."""
        data = copy.deepcopy(BASE_EXTRACTION)
        for name, (value, span) in self.overrides.items():
            if name not in data:
                raise KeyError(f"{self.id}: unknown extracted field {name}")
            data[name] = {"value": value, "confirmed": False, "source_span": span}
        for name, fld in data.items():
            span = fld.get("source_span")
            if span is not None and span not in self.jd:
                raise ValueError(f"{self.id}: the source span of {name} is not verbatim in the posting: {span!r}")
        return data

    @property
    def company(self) -> str:
        return self.overrides["company_name_zh"][0]

    @property
    def title(self) -> str:
        return self.overrides["title_zh"][0]


def _standard_overrides(
    company: str, title: str, title_en: str, *, kind: str, track: str, email: str, city: str, district: str, location: str
) -> Overrides:
    head = f"{title}（{kind}）"
    location_line = f"工作地点：{location}"
    return {
        "company_name_zh": (company, company),
        "title_zh": (title, head),
        "title_en": (title_en, head),
        "internship_type": (kind, head),
        "track_guess": (track, head),
        "city_zh": (city, location_line),
        "district": (district, location_line),
        "work_mode": ("onsite", location_line),
        "application_method": (
            f"通过实习僧投递，或发送简历至 {email}",
            f"投递方式：通过实习僧投递，或发送简历至 {email}",
        ),
    }


def _role_overrides(role: Role) -> Overrides:
    return {
        "responsibilities_summary": ("。".join(role.duties) + "。", "岗位职责：\n" + _numbered(role.duties)),
        "required_skills": (list(role.required_skills), role.skills_line),
        "preferred_skills": (list(role.preferred_skills), role.bonus_line + "。"),
    }


def scenario(
    id: str,
    summary: str,
    *,
    company: str,
    title: str,
    title_en: str,
    email: str,
    expected: Expected,
    where: str,
    kind: str = "日常实习",
    track: str = "AI",
    city: str = "杭州",
    district: str = "西湖区",
    location: str | None = None,
    role: Role = ROLE_AI,
    cohort_line: str = COHORT_LINE,
    schedule_line: str = SCHEDULE_LINE,
    extra_lines: tuple[str, ...] = (),
    salary_line: str = SALARY_LINE,
    tail: tuple[str, ...] = (),
    extra: Overrides | None = None,
    source: str = "shixiseng",
    stored_row: bool = False,
    known_failure: str | None = None,
    diagnosis: str | None = None,
) -> Scenario:
    location = location or f"{city}市 {district}"
    jd = posting(
        company, title, kind=kind, location=location, role=role, cohort_line=cohort_line,
        schedule_line=schedule_line, extra_lines=extra_lines, salary_line=salary_line, email=email, tail=tail,
    )
    overrides = _standard_overrides(
        company, title, title_en, kind=kind, track=track, email=email, city=city, district=district, location=location
    )
    if role is not ROLE_AI:
        overrides.update(_role_overrides(role))
    overrides.update(extra or {})
    return Scenario(
        id, summary, jd, overrides, expected, where, source=source, stored_row=stored_row,
        known_failure=known_failure, diagnosis=diagnosis,
    )


STUDENT_STATUS_CODES = (
    "EXPLICIT_STUDENT_STATUS_RESTRICTION",
    "STUDENT_STATUS_REVIEW",
    "EXPLICIT_NATIONALITY_RESTRICTION",
    "EXPLICIT_WORK_AUTHORIZATION_RESTRICTION",
)
# Every code run_eligibility derives from nationality_or_work_auth_restriction: the spec's
# "no restriction code" for S16 read literally.
RESTRICTION_CODES = (*STUDENT_STATUS_CODES, "RESTRICTION_TEXT_PRESENT_REVIEW")
COHORT_CODES = (
    "GRADUATION_COHORT_INELIGIBLE",
    "GRADUATION_COHORT_PREFERRED",
    "COHORT_TEXT_UNPARSEABLE",
    "USER_COHORT_UNPARSEABLE",
)
ADDED_FIELD_CODES = ("FEE_REQUIRED", "NOT_ENGINEERING_WORK", "UNPAID", "REMOTE_ONLY")
STORED_ROW_MISSING = ("work_mode", "pays_fee", "mostly_annotation", "mostly_sales")
ASK_HR = "ask HR whether a 2027-02-15 start works"

# Part A: eligibility and flags; part B (P01-P03): programme dates.
SCENARIOS: list[Scenario] = [
    scenario(
        "S01", "clean AI role in 杭州: 大模型应用开发实习生, 本科, 5天/周, 6个月, 250元/天, 2027年2月到岗, onsite",
        company=BASE_COMPANY, title="大模型应用开发实习生", title_en="LLM Application Development Intern",
        email=BASE_EMAIL, location="杭州市 西湖区，需到公司坐班",
        schedule_line="每周5天，实习6个月，2027年2月到岗", salary_line="薪资：250元/天",
        tail=("投递截止：2026年11月1日",),
        extra={
            "work_mode": ("onsite", "需到公司坐班"),
            "days_per_week_min": (5, "每周5天"),
            "duration_min_months": (6, "实习6个月"),
            "duration_max_months": (6, "实习6个月"),
            "start_date_text": ("2027年2月到岗", "2027年2月到岗"),
            "start_date": ("2027-02-01", "2027年2月到岗"),
            "start_timing": ("named_month", "2027年2月到岗"),
            "salary_text": ("250元/天", "薪资：250元/天"),
            "deadline": ("2026-11-01", "投递截止：2026年11月1日"),
        },
        expected=Expected(eligibility=("LIKELY_ELIGIBLE", "ELIGIBLE"), no_hard_fail=True, track="AI"),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S02", "仅限国内高校在读",
        company="杭州云脉数据有限公司", title="AI算法实习生", title_en="AI Algorithm Intern", email="hr@yunmai-example.com",
        extra_lines=("仅限国内高校在读",),
        extra={"nationality_or_work_auth_restriction": ("仅限国内高校在读", "仅限国内高校在读")},
        expected=Expected(
            eligibility=("INELIGIBLE",), codes_include=("EXPLICIT_STUDENT_STATUS_RESTRICTION",),
            status="INELIGIBLE", tier="HOLD",
        ),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S03", "需学信网可查",
        company="上海观澜信息技术有限公司", title="NLP算法实习生", title_en="NLP Algorithm Intern", email="hr@guanlan-example.com",
        city="上海", district="浦东新区", extra_lines=("在校生需学信网可查",),
        extra={"nationality_or_work_auth_restriction": ("需学信网可查", "需学信网可查")},
        expected=Expected(eligibility=("UNCERTAIN",), codes_include=("STUDENT_STATUS_REVIEW",)),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S04", "中国国籍优先",
        company="宁波启明视觉科技有限公司", title="计算机视觉实习生", title_en="Computer Vision Intern", email="hr@qiming-example.com",
        city="宁波", district="鄞州区", extra_lines=("中国国籍优先",),
        extra={"nationality_or_work_auth_restriction": ("中国国籍优先", "中国国籍优先")},
        expected=Expected(not_ineligible=True, codes_include=("RESTRICTION_TEXT_PRESENT_REVIEW",)),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S05", "仅限中国籍",
        company="南京长风智能有限公司", title="机器学习实习生", title_en="Machine Learning Intern", email="hr@changfeng-example.com",
        city="南京", district="江宁区", extra_lines=("仅限中国籍",),
        extra={"nationality_or_work_auth_restriction": ("仅限中国籍", "仅限中国籍")},
        expected=Expected(eligibility=("INELIGIBLE",), codes_include=("EXPLICIT_NATIONALITY_RESTRICTION",)),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S06", "不提供工作签证",
        company="苏州清泉软件有限公司", title="后端开发实习生", title_en="Backend Development Intern", email="hr@qingquan-example.com",
        city="苏州", district="工业园区", track="SWE", role=ROLE_BACKEND, extra_lines=("本岗位不提供工作签证",),
        extra={"nationality_or_work_auth_restriction": ("不提供工作签证", "不提供工作签证")},
        expected=Expected(eligibility=("INELIGIBLE",), codes_include=("EXPLICIT_WORK_AUTHORIZATION_RESTRICTION",)),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S07", "硕士及以上",
        company="上海鹿鸣算法有限公司", title="大模型算法实习生", title_en="LLM Algorithm Intern", email="hr@luming-example.com",
        city="上海", district="徐汇区", cohort_line="2027届/2028届硕士及以上学历在读，计算机、人工智能等相关专业",
        extra={
            "graduation_cohort_text": ("2027届/2028届硕士及以上学历在读", "2027届/2028届硕士及以上学历在读，计算机、人工智能等相关专业"),
            "cohort_years": ([2027, 2028], "2027届/2028届硕士及以上学历在读"),
            "degree_required": ("master", "硕士及以上学历在读"),
            "major_requirement": ("计算机、人工智能等相关专业", "计算机、人工智能等相关专业"),
            "research_signals": (["master_required"], "硕士及以上学历在读"),
        },
        expected=Expected(eligibility=("INELIGIBLE",), codes_include=("DEGREE_INELIGIBLE",)),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S08", "仅限2027届",
        company="杭州墨白网络科技有限公司", title="推荐算法实习生", title_en="Recommendation Algorithm Intern", email="hr@mobai-example.com",
        district="滨江区", cohort_line="仅限2027届本科及以上在校生，计算机相关专业",
        extra={
            "graduation_cohort_text": ("仅限2027届本科及以上在校生", "仅限2027届本科及以上在校生，计算机相关专业"),
            "cohort_years": ([2027], "仅限2027届"),
            "degree_required": ("bachelor", "本科及以上在校生"),
            "major_requirement": ("计算机相关专业", "计算机相关专业"),
        },
        expected=Expected(eligibility=("INELIGIBLE",), codes_include=("GRADUATION_COHORT_INELIGIBLE",)),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S09", "2027届及以后",
        company="杭州潮汐智联有限公司", title="数据挖掘实习生", title_en="Data Mining Intern", email="hr@chaoxi-example.com",
        district="余杭区", cohort_line="2027届及以后本科及以上在校生，计算机相关专业",
        extra={
            "graduation_cohort_text": ("2027届及以后本科及以上在校生", "2027届及以后本科及以上在校生，计算机相关专业"),
            "cohort_years": ([2027], "2027届及以后"),
            "degree_required": ("bachelor", "本科及以上在校生"),
            "major_requirement": ("计算机相关专业", "计算机相关专业"),
        },
        expected=Expected(not_ineligible=True, codes_exclude=COHORT_CODES),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S10", "2027届优先",
        company="无锡听澜语音科技有限公司", title="语音算法实习生", title_en="Speech Algorithm Intern", email="hr@tinglan-example.com",
        city="无锡", district="新吴区", cohort_line="2027届优先，本科及以上在校生，计算机相关专业",
        extra={
            "graduation_cohort_text": ("2027届优先", "2027届优先，本科及以上在校生，计算机相关专业"),
            "cohort_years": ([2027], "2027届优先"),
            "degree_required": ("bachelor", "本科及以上在校生"),
            "major_requirement": ("计算机相关专业", "计算机相关专业"),
        },
        expected=Expected(not_ineligible=True, codes_include=("GRADUATION_COHORT_PREFERRED",)),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S11", "需缴纳培训费 (pays_fee true)",
        company="杭州飞跃人才服务有限公司", title="AI训练师实习生", title_en="AI Trainer Intern", email="hr@feiyue-example.com",
        district="拱墅区", extra_lines=("培训期需缴纳培训费，考核通过后退还",),
        extra={"pays_fee": (True, "需缴纳培训费")},
        expected=Expected(eligibility=("INELIGIBLE",), codes_include=("FEE_REQUIRED",)),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S12", "mostly sales (mostly_sales true)",
        company="杭州拓客智能科技有限公司", title="AI产品销售实习生", title_en="AI Product Sales Intern", email="hr@tuoke-example.com",
        district="上城区", track="other", role=ROLE_SALES, tail=("投递截止：2026年11月15日",),
        extra={
            "mostly_sales": (True, "负责AI产品的电话销售与客户拓展，完成月度销售指标"),
            "deadline": ("2026-11-15", "投递截止：2026年11月15日"),
        },
        expected=Expected(not_ineligible=True, codes_include=("NOT_ENGINEERING_WORK",)),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S13", "无薪实习",
        company="上海初光科技有限公司", title="智能体开发实习生", title_en="Agent Development Intern", email="hr@chuguang-example.com",
        city="上海", district="杨浦区", salary_line="薪资：无薪实习，可开具实习证明", tail=("投递截止：2026年10月20日",),
        extra={
            "salary_text": ("无薪实习，可开具实习证明", "薪资：无薪实习，可开具实习证明"),
            "deadline": ("2026-10-20", "投递截止：2026年10月20日"),  # closes before S01 and S12: see run_ranking
        },
        expected=Expected(not_ineligible=True, codes_include=("UNPAID",)),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S14", "远程实习 (work_mode remote)",
        company="上海栖云软件有限公司", title="前端开发实习生", title_en="Frontend Development Intern", email="hr@qiyun-example.com",
        city="上海", district="徐汇区", location="上海市 徐汇区（远程实习，无需到岗）", track="SWE", role=ROLE_FRONTEND,
        tail=("投递截止：2026年10月25日",),
        extra={
            "work_mode": ("remote", "远程实习，无需到岗"),
            "deadline": ("2026-10-25", "投递截止：2026年10月25日"),  # closes before S01 and S12: see run_ranking
        },
        expected=Expected(not_ineligible=True, codes_include=("REMOTE_ONLY",)),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S15", "薪资面议",
        company="南京寻迹搜索技术有限公司", title="搜索算法实习生", title_en="Search Algorithm Intern", email="hr@xunji-example.com",
        city="南京", district="雨花台区", salary_line="薪资面议，具体按能力定级",
        extra={"salary_text": ("薪资面议", "薪资面议")},
        expected=Expected(not_ineligible=True, codes_exclude=("UNPAID",)),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S16", "全日制在校生",
        company="杭州知远图谱科技有限公司", title="知识图谱实习生", title_en="Knowledge Graph Intern", email="hr@zhiyuan-example.com",
        district="西湖区", extra_lines=("全日制在校生，能保证实习时间",),
        extra={"nationality_or_work_auth_restriction": ("全日制在校生", "全日制在校生")},
        expected=Expected(not_ineligible=True, codes_exclude=RESTRICTION_CODES),
        where=WHERE_ELIGIBILITY,
        known_failure="unexpected code RESTRICTION_TEXT_PRESENT_REVIEW",
        diagnosis=(
            "expectation wrong, not the code: run_eligibility reviews any nationality_or_work_auth_restriction text "
            "that matches no deterministic pattern (RESTRICTION_TEXT_PRESENT_REVIEW, UNCERTAIN) by design, so "
            "全日制在校生 in that field is always reviewed and never INELIGIBLE; the row passes only under the reading "
            "'no student-status, nationality or work-authorisation code' (the assertion of tests/test_eligibility.py "
            "test_full_time_student_wording_matches_no_student_pattern) or with the wording kept out of the "
            "restriction field; user decision"
        ),
    ),
    scenario(
        "S17", "暑期实习 (internship_type summer)",
        company="嘉兴鹏程影像科技有限公司", title="视觉算法实习生", title_en="Vision Algorithm Intern", email="hr@pengcheng-example.com",
        city="嘉兴", district="南湖区", kind="暑期实习", schedule_line="每周5天，实习2至3个月，2027年7月初到岗",
        extra={
            "days_per_week_min": (5, "每周5天"),
            "duration_min_months": (2, "实习2至3个月"),
            "duration_max_months": (3, "实习2至3个月"),
            "start_date_text": ("2027年7月初到岗", "2027年7月初到岗"),
            "start_date": ("2027-07-01", "2027年7月初到岗"),
            "start_timing": ("named_month", "2027年7月初到岗"),
        },
        expected=Expected(codes_include=("SUMMER_PROGRAMME_TIMING",)),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S18", "尽快到岗 (start_timing asap)",
        company="苏州快马软件有限公司", title="Python后端实习生", title_en="Python Backend Intern", email="hr@kuaima-example.com",
        city="苏州", district="高新区", track="SWE", role=ROLE_PYTHON_BACKEND,
        schedule_line="每周4天以上，实习4至6个月，尽快到岗",
        extra={
            "start_date_text": ("尽快到岗", "尽快到岗"),
            "start_date": (None, None),
            "start_timing": ("asap", "尽快到岗"),
        },
        expected=Expected(not_ineligible=True, next_action_contains=ASK_HR),
        where=WHERE_PIPELINE,
    ),
    scenario(
        "S19", "deadline 2026-09-20 (before today 2026-10-01)",
        company="宁波多维感知科技有限公司", title="多模态算法实习生", title_en="Multimodal Algorithm Intern", email="hr@duowei-example.com",
        city="宁波", district="海曙区", tail=("投递截止：2026年9月20日",),
        extra={"deadline": ("2026-09-20", "投递截止：2026年9月20日")},
        expected=Expected(eligibility=("INELIGIBLE",), codes_include=("DEADLINE_PASSED",)),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S20", "自动驾驶感知算法实习 (track_guess AUTO)",
        company="上海领航智驾科技有限公司", title="自动驾驶感知算法实习生", title_en="Autonomous Driving Perception Intern",
        email="hr@linghang-example.com", city="上海", district="嘉定区", track="AUTO", role=ROLE_AUTO,
        expected=Expected(not_ineligible=True, track="AUTO"),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S21", "底盘结构设计实习, CAD (track_guess other)",
        company="杭州创驰汽车零部件有限公司", title="底盘结构设计实习生", title_en="Chassis Structure Design Intern",
        email="hr@chuangchi-example.com", district="萧山区", track="other", role=ROLE_CHASSIS,
        expected=Expected(track="other"),
        where=WHERE_ELIGIBILITY,
    ),
    scenario(
        "S22", "row stored before the added fields existed (no work_mode/pays_fee/mostly_annotation/mostly_sales keys)",
        company="杭州北辰算法有限公司", title="算法工程实习生", title_en="Algorithm Engineering Intern", email="hr@beichen-example.com",
        district="西湖区", stored_row=True,
        expected=Expected(evaluated=True, confirmed_nulls=STORED_ROW_MISSING, codes_exclude=ADDED_FIELD_CODES),
        where=WHERE_ADDED_FIELDS,
    ),
    scenario(
        "P01", "JD minimum 8 months",
        company="上海千帆大模型科技有限公司", title="大模型训练实习生", title_en="LLM Training Intern", email="hr@qianfan-example.com",
        city="上海", district="闵行区", schedule_line="每周4天以上，实习8个月以上，2027年3月起可入职",
        extra={"duration_min_months": (8, "实习8个月以上"), "duration_max_months": (None, None)},
        expected=Expected(dimensions={"DURATION_AND_DATES": "AT_RISK"}, note_contains={"DURATION_AND_DATES": "YES_MAX_DURATION"}),
        where=WHERE_PROGRAMME,
    ),
    scenario(
        "P02", "JD start 2027-04-01, minimum 5 months (ends after latest_end 2027-08-31)",
        company="杭州云梯平台软件有限公司", title="AI平台开发实习生", title_en="AI Platform Development Intern", email="hr@yunti-example.com",
        district="滨江区", schedule_line="每周4天以上，实习5至6个月，2027年4月起可入职",
        extra={
            "duration_min_months": (5, "实习5至6个月"),
            "duration_max_months": (6, "实习5至6个月"),
            "start_date_text": ("2027年4月起可入职", "2027年4月起可入职"),
            "start_date": ("2027-04-01", "2027年4月起可入职"),
            "start_timing": ("named_month", "2027年4月起可入职"),
        },
        expected=Expected(dimensions={"DURATION_AND_DATES": "AT_RISK"}, note_contains={"DURATION_AND_DATES": "latest_end"}),
        where=WHERE_PROGRAMME,
    ),
    scenario(
        "P03", "no JD start, minimum 6 months",
        company="嘉兴磐石机器学习有限公司", title="机器学习平台实习生", title_en="ML Platform Intern", email="hr@panshi-example.com",
        city="嘉兴", district="秀洲区", schedule_line="每周4天以上，实习6个月以上，到岗时间可协商",
        extra={
            "duration_min_months": (6, "实习6个月以上"),
            "duration_max_months": (None, None),
            "start_date_text": ("到岗时间可协商", "到岗时间可协商"),
            "start_date": (None, None),
            "start_timing": ("flexible", "到岗时间可协商"),
        },
        expected=Expected(dimensions={"DURATION_AND_DATES": "LIKELY"}),
        where=WHERE_PROGRAMME,
    ),
]

# Postings used by the duplicate and web parts; they carry no expectation of their own.
AUX_SCENARIOS: list[Scenario] = [
    scenario(
        "D01", "shixiseng tracking link, then the bare URL",
        company="苏州数澜信息技术有限公司", title="数据开发实习生", title_en="Data Development Intern", email="hr@shulan-example.com",
        city="苏州", district="工业园区", track="SWE", role=ROLE_PYTHON_BACKEND,
        expected=Expected(), where=WHERE_DUPLICATES,
    ),
    scenario(
        "D02", "YES URL with and without the trailing slash",
        company="上海联汇智能科技有限公司", title="人工智能实习生", title_en="Artificial Intelligence Intern", email="hr@lianhui-example.com",
        city="上海", district="静安区", source="yes_portal",
        expected=Expected(), where=WHERE_DUPLICATES,
    ),
    scenario(
        "W01", "fresh capture shown on the review page",
        company="无锡灵犀评测科技有限公司", title="算法评测实习生", title_en="Algorithm Evaluation Intern", email="hr@lingxi-example.com",
        city="无锡", district="滨湖区",
        expected=Expected(), where=WHERE_WEB,
    ),
    scenario(
        "W02", "posted through the web capture form and confirmed on the review page",
        company="南京云图应用软件有限公司", title="AI应用工程实习生", title_en="AI Application Engineering Intern", email="hr@yuntu-example.com",
        city="南京", district="鼓楼区", source="boss",
        expected=Expected(), where=WHERE_WEB,
    ),
]

ALL_SCENARIOS: list[Scenario] = SCENARIOS + AUX_SCENARIOS
SCENARIO_BY_ID: dict[str, Scenario] = {s.id: s for s in ALL_SCENARIOS}


# --------------------------------------------------------------------------------------
# Fake extraction: the current scenario's extraction, for whichever provider hook is installed
# --------------------------------------------------------------------------------------

_current: Scenario | None = None


def set_current(scenario: Scenario | None) -> None:
    global _current
    _current = scenario


def fake_extract_job(prompt: str) -> str:
    """The ``extract_job`` answer: the selected scenario's extraction as JSON."""
    if _current is None:
        raise RuntimeError("simulation: no scenario is selected for the fake extractor")
    if _current.jd.strip() not in prompt:
        raise RuntimeError(f"simulation: the extraction prompt does not contain scenario {_current.id}'s posting")
    return json.dumps(_current.extraction(), ensure_ascii=False)


def fake_provider(prompt_name: str, prompt: str) -> str:
    """A provider for ``llm.set_fake_provider``: extraction only; every other prompt raises."""
    if prompt_name == "extract_job":
        return fake_extract_job(prompt)
    raise RuntimeError(f"simulation: no fake response for prompt {prompt_name!r}")


class FakeWeb:
    """Stands in for ``httpx.get``: answers 200 with ``body``, or refuses when no body is set."""

    def __init__(self) -> None:
        self.body: str | None = None
        self.calls: list[str] = []

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append(url)
        if self.body is None:
            raise RuntimeError(f"simulation: network access attempted: {url}")
        return httpx.Response(200, request=httpx.Request("GET", url), text=self.body)


# --------------------------------------------------------------------------------------
# Outcomes, rows and checks
# --------------------------------------------------------------------------------------


@dataclass
class Outcome:
    job_id: int
    status: str
    eligibility: str
    codes: list[str]
    programme: dict[str, dict[str, Any]]
    programme_overall: str
    tier: str
    track: str
    next_action: str | None
    extracted: ExtractedJob

    def describe(self) -> str:
        duration = self.programme.get("DURATION_AND_DATES", {}).get("status")
        return (
            f"{self.eligibility} [{', '.join(self.codes) or '-'}]; status {self.status}; tier {self.tier}; "
            f"track {self.track}; DURATION_AND_DATES {duration}; next_action {self.next_action or '-'}"
        )


@dataclass
class Row:
    id: str
    expected: str
    actual: str
    result: str  # PASS | FAIL | SKIP
    mismatches: list[str] = field(default_factory=list)
    where: str = ""
    diagnosis: str = ""  # for a FAIL row: whether the code or the expectation is wrong

    @property
    def passed(self) -> bool:
        return self.result == "PASS"


def _row(
    id: str, expected: str, actual: str, ok: bool, where: str, mismatches: list[str] | None = None, diagnosis: str = ""
) -> Row:
    return Row(id, expected, actual, "PASS" if ok else "FAIL", list(mismatches or ([] if ok else [actual])), where, diagnosis)


def outcome_of(job: Job) -> Outcome:
    return Outcome(
        job_id=job.id,
        status=job.status,
        eligibility=job.eligibility,
        codes=[r["code"] for r in (job.eligibility_reasons or [])],
        programme=dict(job.programme or {}),
        programme_overall=job.programme_overall,
        tier=job.tier,
        track=job.track,
        next_action=job.next_action,
        extracted=ExtractedJob.model_validate(job.extracted),
    )


def check(expected: Expected, outcome: Outcome) -> list[str]:
    """Every way ``outcome`` departs from ``expected``; empty means the row passes."""
    problems: list[str] = []
    codes = set(outcome.codes)
    if expected.eligibility and outcome.eligibility not in expected.eligibility:
        problems.append(f"eligibility is {outcome.eligibility}, expected {' or '.join(expected.eligibility)}")
    if expected.not_ineligible and outcome.eligibility == "INELIGIBLE":
        problems.append("eligibility is INELIGIBLE")
    if expected.evaluated and outcome.eligibility == "NOT_RUN":
        problems.append("eligibility is NOT_RUN")
    hard = sorted(codes & HARD_FAIL_CODES)
    if expected.no_hard_fail and hard:
        problems.append("hard-fail code(s) present: " + ", ".join(hard))
    for code in expected.codes_include:
        if code not in codes:
            problems.append(f"missing code {code}")
    for code in expected.codes_exclude:
        if code in codes:
            problems.append(f"unexpected code {code}")
    if expected.status and outcome.status != expected.status:
        problems.append(f"status is {outcome.status}, expected {expected.status}")
    if expected.tier and outcome.tier != expected.tier:
        problems.append(f"tier is {outcome.tier}, expected {expected.tier}")
    if expected.track and outcome.track != expected.track:
        problems.append(f"track is {outcome.track}, expected {expected.track}")
    if expected.next_action_contains and expected.next_action_contains not in (outcome.next_action or ""):
        problems.append(f"next_action {outcome.next_action!r} lacks {expected.next_action_contains!r}")
    for name, status in expected.dimensions.items():
        actual = outcome.programme.get(name, {}).get("status")
        if actual != status:
            problems.append(f"{name} is {actual}, expected {status}")
    for name, text in expected.note_contains.items():
        note = outcome.programme.get(name, {}).get("note") or ""
        if text not in note:
            problems.append(f"{name} note lacks {text!r}: {note!r}")
    for name in expected.confirmed_nulls:
        fld = outcome.extracted.get(name)
        if not (fld.confirmed and fld.value is None):
            problems.append(f"{name} loaded as value={fld.value!r} confirmed={fld.confirmed}, expected a confirmed null")
    return problems


def scenario_row(scenario: Scenario, outcome: Outcome) -> Row:
    mismatches = check(scenario.expected, outcome)
    return Row(
        scenario.id,
        f"{scenario.summary} -> {scenario.expected.describe()}",
        outcome.describe(),
        "PASS" if not mismatches else "FAIL",
        mismatches,
        scenario.where,
        scenario.diagnosis or "",
    )


# --------------------------------------------------------------------------------------
# The shared runner: capture -> confirm like `ios confirm` with 'a' -> company -> finalize
# --------------------------------------------------------------------------------------


def confirm_like_cli(session: Session, config: AppConfig, today: date, job: Job) -> Outcome:
    """What ``ios confirm`` does when the user answers 'a' at every prompt.

    'a' at the first field accepts every remaining field except the must-check fields, which
    are still asked one by one and answered 'a' here too.
    """
    asked: list[str] = []

    def decide(name: str, fld: Any, error: str | None) -> str:
        asked.append(name)
        return "a"

    confirmed, overrides = apply_confirmation(ExtractedJob.model_validate(job.extracted), decide)
    not_asked = [name for name in ALWAYS_CONFIRM_FIELDS if name not in asked]
    if not_asked:
        raise AssertionError(f"must-check fields were not asked: {', '.join(not_asked)}")
    exact, _near = find_company_matches(session, confirmed.company_name_zh.value, confirmed.company_name_en.value)
    company = exact if exact is not None else create_company_from_extraction(session, confirmed)
    result = finalize_confirmation(session, job, confirmed, company, overrides, config, today=today)
    return outcome_of(result.job)


def run_captured(session: Session, config: AppConfig, today: date, scenario: Scenario) -> Outcome:
    set_current(scenario)
    job = capture(scenario.jd, None, scenario.source, session=session, config=config, today=today)
    return confirm_like_cli(session, config, today, job)


def run_stored_row(session: Session, config: AppConfig, today: date, scenario: Scenario) -> Outcome:
    """A job confirmed before the added fields existed: its stored JSON lacks their keys."""
    data = scenario.extraction()
    for name in STORED_ROW_MISSING:
        del data[name]
    for fld in data.values():
        fld["confirmed"] = True
    extracted = ExtractedJob.model_validate(data)
    job = Job(
        source_channel=scenario.source,
        raw_text=scenario.jd,
        extracted=data,
        confirmed_at=utcnow(),
        next_action=POST_CONFIRM_NEXT_ACTION,
        next_action_date=today,
    )
    refresh_display_fields(job, extracted)
    job.company = Company(
        name_zh=extracted.company_name_zh.value, name_en=extracted.company_name_en.value, city_zh=job.city_zh
    )
    session.add(job)
    session.commit()
    recompute_job(job, config, today)
    session.commit()
    return outcome_of(job)


def run_scenario(session: Session, config: AppConfig, today: date, scenario: Scenario) -> Outcome:
    if scenario.stored_row:
        return run_stored_row(session, config, today, scenario)
    return run_captured(session, config, today, scenario)


# --------------------------------------------------------------------------------------
# Part B: agreed dates (P04-P06) on S01's job
# --------------------------------------------------------------------------------------

AGREED_ROW_IDS = ("P04", "P05", "P06")


def run_agreed_dates(session: Session, config: AppConfig, today: date, job: Job) -> list[Row]:
    def duration_status() -> str:
        return job.programme["DURATION_AND_DATES"]["status"]

    rows: list[Row] = []
    set_agreed_dates(session, job, date(2027, 3, 1), 6, config, today)
    p04 = duration_status()
    rows.append(_row("P04", "S01 with agreed dates 2027-03-01 for 6 months -> DURATION_AND_DATES AT_RISK (ends 2027-09-01, after latest_end 2027-08-31)", f"DURATION_AND_DATES {p04}: {job.programme['DURATION_AND_DATES']['note']}", p04 == "AT_RISK", WHERE_PROGRAMME))
    recompute_all(session, config, today)
    p04_after = duration_status()
    p04_dates = (job.agreed_start_date, job.agreed_duration_months)

    set_agreed_dates(session, job, date(2027, 2, 15), 6, config, today)
    p05 = duration_status()
    rows.append(_row("P05", "S01 with agreed dates 2027-02-15 for 6 months -> DURATION_AND_DATES CONFIRMED (ends 2027-08-15)", f"DURATION_AND_DATES {p05}: {job.programme['DURATION_AND_DATES']['note']}", p05 == "CONFIRMED", WHERE_PROGRAMME))
    recompute_all(session, config, today)
    p05_after = duration_status()
    p05_dates = (job.agreed_start_date, job.agreed_duration_months)

    ok = (
        p04_after == p04 == "AT_RISK"
        and p05_after == p05 == "CONFIRMED"
        and p04_dates == (date(2027, 3, 1), 6)
        and p05_dates == (date(2027, 2, 15), 6)
    )
    rows.append(_row(
        "P06",
        "agreed dates and their DURATION_AND_DATES status survive recompute_all (P04 stays AT_RISK, P05 stays CONFIRMED)",
        f"after recompute: P04 {p04} -> {p04_after} with agreed {p04_dates[0]}/{p04_dates[1]}; P05 {p05} -> {p05_after} with agreed {p05_dates[0]}/{p05_dates[1]}",
        ok,
        WHERE_AGREED,
    ))
    return rows


# --------------------------------------------------------------------------------------
# Part C: ranking
# --------------------------------------------------------------------------------------

RANKED_IDS = ("S01", "S12", "S13", "S14")
RANKING_ROW_IDS = ("C-SORT", "C-LIST-AUTO")
CLI_ENV = {"COLUMNS": "200"}  # Rich truncates table cells at its 80-column fallback under CliRunner


def invoke_cli(args: list[str]) -> Any:
    """Run ``ios <args>`` in-process. The caller pins ``internship_os.cli.today_value``."""
    return CliRunner().invoke(cli_app, args, env=CLI_ENV)


def cli_ok(result: Any) -> bool:
    return result.exit_code == 0 and result.exception is None and "Traceback" not in result.output


def run_ranking(session: Session, config: AppConfig, today: date, jobs: dict[str, Job]) -> list[Row]:
    """``jobs`` maps scenario id -> its confirmed Job; needs S01, S12, S13, S14 and S20."""
    for sid in RANKED_IDS:
        set_fit(session, jobs[sid], "strong", config)
        set_quality(session, jobs[sid], "ok", config)
    tiers = {sid: jobs[sid].tier for sid in RANKED_IDS}
    deadlines = {sid: jobs[sid].deadline for sid in RANKED_IDS}
    by_job_id = {jobs[sid].id: sid for sid in RANKED_IDS}
    order = [by_job_id[j.id] for j in sort_jobs([jobs[sid] for sid in RANKED_IDS], config.user_facts)]
    # S13 and S14 must close before S01 and S12: then only the sort-last key (UNPAID / REMOTE_ONLY)
    # can put them behind S01 and S12, and dropping that key from tiering.sort_key fails this row.
    kept = (deadlines["S01"], deadlines["S12"])
    close_first = None not in kept and all(
        deadlines[sid] is not None and deadlines[sid] < min(kept) for sid in ("S13", "S14")
    )
    ok = (
        len(set(tiers.values())) == 1
        and close_first
        and order[:2] == ["S01", "S12"]
        and set(order[2:]) == {"S13", "S14"}
    )
    shown = {sid: (d.isoformat() if d else None) for sid, d in deadlines.items()}
    rows = [_row(
        "C-SORT",
        "same fit and quality -> one tier; S13 and S14 close before S01 and S12 yet sort last (UNPAID / REMOTE_ONLY); "
        "sort_jobs order S01, S12 (by deadline 2026-11-01 < 2026-11-15), then S13 and S14",
        f"tiers {tiers}; deadlines {shown}; order {order}",
        ok,
        WHERE_SORT,
    )]
    result = invoke_cli(["job", "list", "--track", "AUTO"])
    title = jobs["S20"].display_title
    shown = title[:8] in result.output  # a cell may end in an ellipsis; the prefix is enough
    ok = cli_ok(result) and "1 job(s)" in result.output and shown
    rows.append(_row(
        "C-LIST-AUTO",
        "ios job list --track AUTO shows S20 only",
        f"exit {result.exit_code}; '1 job(s)' shown: {'1 job(s)' in result.output}; S20 title shown: {shown}",
        ok,
        WHERE_JOB_LIST,
    ))
    return rows


# --------------------------------------------------------------------------------------
# Part D: capture paths and duplicates
# --------------------------------------------------------------------------------------

URL_SCENARIO_IDS = ("U01", "U02", "U03", "U04")
NUMBER_CHECKS = {
    "pay": re.compile(r"\d+\s*(?:元|RMB|￥|¥|[kK]\b)"),
    "days": re.compile(r"\d\s*天"),
    "months": re.compile(r"\d+\s*个?月"),
}
U04_REASON = "skipped by design: checkpoint 1 added no font-hidden check (trafilatura strips private-use characters)"


def _relative(path: Path) -> str:
    return str(path.relative_to(FIXTURES_DIR.parents[1]))


def run_url_scenario(web: FakeWeb, scenario_id: str) -> Row:
    expected_login = "the page appears to require login"
    try:
        if scenario_id == "U01":
            expected = "fetch_url_text on shixiseng_detail.html -> text with digits in pay, days and months"
            if not SHIXISENG_FIXTURE.exists():
                actual = f"fixture missing: {_relative(SHIXISENG_FIXTURE)} could not be downloaded (host unreachable)"
                diagnosis = "neither the code nor the expectation is wrong: save the page under that name to run the row"
                return _row("U01", expected, actual, False, WHERE_FETCH, diagnosis=diagnosis)
            web.body = SHIXISENG_FIXTURE.read_text(encoding="utf-8")
            text = fetch_url_text("https://www.shixiseng.com/intern/inn_qa5talgymf0o")
            missing = [name for name, pattern in NUMBER_CHECKS.items() if not pattern.search(text)]
            return _row("U01", expected, f"{len(text)} chars; digits missing for: {missing or 'none'}", not missing, WHERE_FETCH)
        if scenario_id == "U02":
            expected = "fetch_url_text on yes_posting.html -> returns the posting text"
            web.body = YES_FIXTURE.read_text(encoding="utf-8")
            text = fetch_url_text("https://yes.businesschina.org.sg/internship/artificial-intelligence-intern/")
            ok = len(text) >= MIN_USEFUL_CHARS and "<html" not in text.lower()
            return _row("U02", expected, f"{len(text)} chars of text", ok, WHERE_FETCH)
        if scenario_id == "U03":
            expected = f"short '请登录后查看' page -> CaptureNeedsPaste '{expected_login}'"
            web.body = "<html><body><p>请登录后查看</p></body></html>"
            try:
                text = fetch_url_text("https://example.com/j")
            except CaptureNeedsPaste as exc:
                return _row("U03", expected, f"CaptureNeedsPaste: {exc.reason}", exc.reason == expected_login, WHERE_FETCH)
            return _row("U03", expected, f"returned {len(text)} chars instead of raising", False, WHERE_FETCH)
        if scenario_id == "U04":
            return Row("U04", "full JD with 3 private-use characters -> CaptureNeedsPaste custom-font message", U04_REASON, "SKIP", [], WHERE_FETCH)
        raise KeyError(scenario_id)
    finally:
        web.body = None


def run_url_paths(web: FakeWeb) -> list[Row]:
    return [run_url_scenario(web, scenario_id) for scenario_id in URL_SCENARIO_IDS]


TRACKING_URL = "https://www.shixiseng.com/intern/inn_sim01?pcm=pc_SearchList"
BARE_URL = "https://www.shixiseng.com/intern/inn_sim01"
YES_URL = "https://yes.businesschina.org.sg/internship/artificial-intelligence-intern"
DUPLICATE_ROW_IDS = ("D01", "D02", "D03")


def count_jobs(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Job)) or 0


def run_duplicates(session: Session, config: AppConfig, today: date) -> list[Row]:
    rows: list[Row] = []
    d01 = SCENARIO_BY_ID["D01"]
    set_current(d01)
    first = capture(d01.jd, TRACKING_URL, d01.source, session=session, config=config, today=today)
    transition(
        session, first, "CLOSED", next_action=None, due=None, stage=None,
        note="simulation: closed before the second capture", config=config, today=today,
    )
    before = count_jobs(session)
    expected = f"capture with {TRACKING_URL}, close it, capture again with {BARE_URL} -> DuplicateCaptureNeedsDecision naming the first job"
    try:
        second = capture(d01.jd, BARE_URL, d01.source, session=session, config=config, today=today)
        rows.append(_row("D01", expected, f"no duplicate raised; a second job {second.id} was created", False, WHERE_DUPLICATES))
    except DuplicateCaptureNeedsDecision as dup:
        ok = dup.candidate_ids == [first.id] and count_jobs(session) == before
        rows.append(_row(
            "D01", expected,
            f"DuplicateCaptureNeedsDecision candidate_ids={dup.candidate_ids}; first job {first.id} is {first.status} with stored url {first.source_url}",
            ok, WHERE_DUPLICATES,
        ))

    d02 = SCENARIO_BY_ID["D02"]
    set_current(d02)
    yes_first = capture(d02.jd, YES_URL + "/", d02.source, session=session, config=config, today=today)
    by_url = find_duplicate_ids(session, YES_URL, set())
    expected = f"capture with {YES_URL}/ then with {YES_URL} -> duplicate detected by the normalised URL"
    try:
        second = capture(d02.jd, YES_URL, d02.source, session=session, config=config, today=today)
        rows.append(_row("D02", expected, f"no duplicate raised; a second job {second.id} was created", False, WHERE_DUPLICATES))
    except DuplicateCaptureNeedsDecision as dup:
        ok = yes_first.id in dup.candidate_ids and by_url == [yes_first.id]
        rows.append(_row(
            "D02", expected,
            f"DuplicateCaptureNeedsDecision candidate_ids={dup.candidate_ids}; stored url {yes_first.source_url}; find_duplicate_ids by URL alone -> {by_url}",
            ok, WHERE_DUPLICATES,
        ))

    before = count_jobs(session)
    event = attach_to_existing(session, first.id, text=d01.jd, url=TRACKING_URL, source_channel=d01.source)
    session.refresh(first)
    after = count_jobs(session)
    last = first.events[-1]
    ok = after == before and last.id == event.id and last.kind == "note" and last.detail.get("source_url") == BARE_URL
    rows.append(_row(
        "D03",
        f"attach_to_existing on D01 with the tracking URL -> no new Job row; a note event whose source_url is {BARE_URL}",
        f"jobs {before} -> {after}; last event {last.kind} with source_url {last.detail.get('source_url')}",
        ok, WHERE_ATTACH,
    ))
    return rows


# --------------------------------------------------------------------------------------
# Part E: CLI and web
# --------------------------------------------------------------------------------------

CLI_COMMANDS: tuple[tuple[str, list[str]], ...] = (
    ("E-CLI-CONSTRAINTS", ["constraints"]),
    ("E-CLI-TIMELINE", ["timeline"]),
    ("E-CLI-DIGEST", ["digest"]),
    ("E-CLI-JOB-LIST", ["job", "list"]),
)
CLI_ROW_IDS = tuple(row_id for row_id, _ in CLI_COMMANDS) + ("E-CLI-RECOMPUTE",)


def _cli_actual(result: Any) -> str:
    text = f"exit {result.exit_code}"
    if result.exception is not None:
        text += f"; {type(result.exception).__name__}: {result.exception}"
    if "Traceback" in result.output:
        text += "; traceback in output"
    return text


def _changed_lines(result: Any) -> list[str]:
    return [line for line in result.output.splitlines() if line.startswith("job ") and not line.rstrip().endswith("no change")]


def run_cli() -> list[Row]:
    """``ios`` commands in-process against the current IOS_ROOT / IOS_DB_URL."""
    rows: list[Row] = []
    for row_id, args in CLI_COMMANDS:
        result = invoke_cli(args)
        rows.append(_row(row_id, f"ios {' '.join(args)}: exit code 0, no traceback", _cli_actual(result), cli_ok(result), f"{WHERE_CLI} {args[-1]}"))
    first = invoke_cli(["recompute"])
    second = invoke_cli(["recompute"])
    job_lines = [line for line in second.output.splitlines() if line.startswith("job ")]
    changed = _changed_lines(second)
    ok = cli_ok(first) and cli_ok(second) and not changed
    rows.append(_row(
        "E-CLI-RECOMPUTE",
        "ios recompute twice: the second run prints no changed lines",
        f"run 1: {_cli_actual(first)}, {len(_changed_lines(first))} changed of {len([l for l in first.output.splitlines() if l.startswith('job ')])} job lines; "
        f"run 2: {_cli_actual(second)}, {len(changed)} changed of {len(job_lines)} job lines" + (f": {changed}" if changed else ""),
        ok, WHERE_RECOMPUTE,
    ))
    return rows


WEB_ROW_IDS = (
    "E-WEB-HOME", "E-WEB-JOBS", "E-WEB-JOB-S02", "E-WEB-JOB-S13", "E-WEB-REVIEW",
    "E-WEB-CAPTURE", "E-WEB-CONFIRM", "E-WEB-CROSS-ORIGIN",
)


def review_form(job: Job) -> dict[str, str]:
    """The review form as the browser submits it, every must-check field ticked."""
    extracted = ExtractedJob.model_validate(job.extracted)
    form = {f"field__{f.name}": f.value for f in review_service.review_fields(extracted)}
    form.update({f"confirm__{name}": "on" for name in review_service.ALWAYS_CONFIRM})
    return form


def run_web(client: Any, session: Session, config: AppConfig, today: date, s02: Job, s13: Job) -> list[Row]:
    """``client`` is a TestClient of the web app with ``deps.today`` pinned and redirects not followed."""
    rows: list[Row] = []
    for row_id, path in (("E-WEB-HOME", "/"), ("E-WEB-JOBS", "/jobs")):
        response = client.get(path)
        rows.append(_row(row_id, f"GET {path} -> 200", f"GET {path} -> {response.status_code}", response.status_code == 200, f"{WHERE_WEB} {'today_page' if path == '/' else 'jobs_page'}"))
    for row_id, job, code in (("E-WEB-JOB-S02", s02, "EXPLICIT_STUDENT_STATUS_RESTRICTION"), ("E-WEB-JOB-S13", s13, "UNPAID")):
        response = client.get(f"/jobs/{job.id}")
        shown = code in response.text
        rows.append(_row(row_id, f"GET /jobs/{job.id} -> 200 showing {code}", f"-> {response.status_code}; {code} shown: {shown}", response.status_code == 200 and shown, f"{WHERE_WEB} job_page"))

    w01 = SCENARIO_BY_ID["W01"]
    set_current(w01)
    fresh = capture(w01.jd, None, w01.source, session=session, config=config, today=today)
    response = client.get(f"/jobs/{fresh.id}/review")
    has_work_mode = 'name="field__work_mode"' in response.text
    has_fee_tick = 'name="confirm__pays_fee"' in response.text
    rows.append(_row(
        "E-WEB-REVIEW",
        f"GET /jobs/{fresh.id}/review for a fresh capture -> 200 listing work_mode and giving pays_fee its own tick",
        f"-> {response.status_code}; field__work_mode: {has_work_mode}; confirm__pays_fee: {has_fee_tick}",
        response.status_code == 200 and has_work_mode and has_fee_tick, f"{WHERE_WEB} review_page",
    ))

    w02 = SCENARIO_BY_ID["W02"]
    set_current(w02)
    response = client.post("/capture", data={"text": w02.jd, "source": w02.source, "url": ""})
    location = response.headers.get("location", "")
    match = re.fullmatch(r"/jobs/(\d+)/review", location)
    rows.append(_row(
        "E-WEB-CAPTURE",
        "POST /capture with a JD (fake LLM) -> 303 to the review page",
        f"-> {response.status_code} location {location or '-'}",
        response.status_code == 303 and match is not None, f"{WHERE_WEB} capture_create",
    ))
    expected = "POST the review form with every must-check field ticked -> 303 to the job page; the job is confirmed"
    if match is None:
        rows.append(_row("E-WEB-CONFIRM", expected, "not run: the capture POST did not redirect to a review page", False, f"{WHERE_WEB} review_confirm"))
    else:
        job_id = int(match.group(1))
        session.expire_all()
        job = session.get(Job, job_id)
        response = client.post(f"/jobs/{job_id}/review", data=review_form(job))
        location = response.headers.get("location", "")
        session.expire_all()
        job = session.get(Job, job_id)
        confirmed = job.confirmed_at is not None
        ok = response.status_code == 303 and location.startswith(f"/jobs/{job_id}?msg=") and confirmed
        rows.append(_row(
            "E-WEB-CONFIRM", expected,
            f"-> {response.status_code} location {location or '-'}; confirmed_at {'set' if confirmed else 'unset'}; eligibility {job.eligibility}; status {job.status}",
            ok, f"{WHERE_WEB} review_confirm",
        ))

    response = client.post("/", headers={"Origin": "https://evil.example"})
    rows.append(_row(
        "E-WEB-CROSS-ORIGIN", "POST / with Origin https://evil.example -> 403",
        f"-> {response.status_code}", response.status_code == 403, WHERE_WEB_SECURITY,
    ))
    return rows
