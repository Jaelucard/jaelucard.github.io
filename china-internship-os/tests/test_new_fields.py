"""The four fields added for Jev: start_timing, pays_fee, mostly_annotation, mostly_sales."""

from __future__ import annotations

import json

from internship_os.capture import apply_confirmation
from internship_os.config import CONFIG_DIRNAME, PROMPTS_DIRNAME
from internship_os.schemas import ALWAYS_CONFIRM_FIELDS, ADDED_FIELDS, ExtractedJob
from tests.conftest import PROJECT_DIR, load_extracted_json


def test_old_extraction_without_the_new_fields_stays_fully_confirmed():
    data = json.loads(load_extracted_json("hangzhou_ai_app"))
    for name in ADDED_FIELDS:
        data.pop(name, None)
    for field in data.values():
        field["confirmed"] = True
    extracted = ExtractedJob.model_validate(data)
    assert extracted.all_confirmed
    for name in ADDED_FIELDS:
        assert extracted.get(name).value is None and extracted.get(name).confirmed


def test_a_new_capture_leaves_the_new_fields_unconfirmed(capture_fixture):
    job = capture_fixture("hangzhou_ai_app")
    extracted = ExtractedJob.model_validate(job.extracted)
    assert not any(extracted.get(name).confirmed for name in ADDED_FIELDS)
    assert extracted.start_timing.value == "named_month"


def test_accept_all_still_asks_every_must_check_field(capture_fixture):
    job = capture_fixture("hangzhou_ai_app")
    asked: list[str] = []

    def decide(name, field, error):
        asked.append(name)
        return "a"

    confirmed, _ = apply_confirmation(ExtractedJob.model_validate(job.extracted), decide)
    assert confirmed.all_confirmed
    order = ExtractedJob.field_names()
    assert asked == [order[0]] + [n for n in order if n in ALWAYS_CONFIRM_FIELDS]


def test_start_timing_is_a_must_check_field():
    assert "start_timing" in ALWAYS_CONFIRM_FIELDS


def test_extraction_prompt_covers_every_field():
    prompt = (PROJECT_DIR / CONFIG_DIRNAME / PROMPTS_DIRNAME / "extract_job.md").read_text(encoding="utf-8")
    for name in ExtractedJob.field_names():
        assert name in prompt, name
    assert f"all {len(ExtractedJob.field_names())} keys" in prompt


# Reason codes that read the added fields. A job stored before the fields existed must get none of them.
NEW_REASON_CODES = {"FEE_REQUIRED", "NOT_ENGINEERING_WORK", "UNPAID"}


def test_a_job_confirmed_before_the_new_fields_recomputes_without_new_reasons(config, today):
    from internship_os.models import Job
    from internship_os.pipeline import recompute_job
    from tests.conftest import load_jd

    data = json.loads(load_extracted_json("hangzhou_ai_app"))
    for name in ADDED_FIELDS:
        data.pop(name, None)
    for field in data.values():
        field["confirmed"] = True
    job = Job(source_channel="shixiseng", raw_text=load_jd("hangzhou_ai_app"), extracted=data,
              next_action="assess fit", next_action_date=today)
    recompute_job(job, config, today)
    assert job.eligibility != "NOT_RUN"
    assert not NEW_REASON_CODES & {r["code"] for r in job.eligibility_reasons}
    assert ExtractedJob.model_validate(job.extracted).get("pays_fee").confirmed


def test_pays_fee_is_a_must_check_field():
    assert "pays_fee" in ALWAYS_CONFIRM_FIELDS
