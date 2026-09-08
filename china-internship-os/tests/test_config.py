from pathlib import Path

import pytest

from internship_os.config import ConfigError, load_config
from internship_os.schemas import CityClass


def test_user_facts_is_created_from_example_and_never_overwritten(project_root: Path):
    target = project_root / "config" / "user_facts.yaml"
    assert not target.exists()
    notice = project_root / "notice.log"
    with notice.open("w") as fh:
        load_config(project_root, notice_stream=fh)
    assert target.exists()
    assert "user_facts.example.yaml" in notice.read_text()

    target.write_text(target.read_text().replace("name: Jarrod Low", "name: Someone Else"))
    with notice.open("w") as fh:
        cfg = load_config(project_root, notice_stream=fh)
    assert cfg.user_facts.name == "Someone Else"
    assert notice.read_text() == ""


def test_seeded_config_loads_and_parses(config):
    assert config.user_facts.cohort_year == 2028
    assert config.user_facts.citizenship == "Singapore"
    assert config.constraints.require("YES_MAX_DURATION").value_months == 6
    assert config.constraints.require("SUTD_MIN_DURATION").value_months == 4
    assert config.constraints.require("LOC_LEAD_TIME").placeholder_days == 14
    assert config.constraints.require("LOC_LEAD_TIME").value_days is None
    assert config.evidence.get("EV_MINDEF_DB") is not None
    assert config.evidence.get("EV_KAGGLE_GENAI_DETECTION").period == "2025"


def test_unknown_key_is_rejected_with_file_key_problem(project_root: Path):
    path = project_root / "config" / "cities.yaml"
    path.write_text(path.read_text() + "\nunexpected_key: 1\n")
    with pytest.raises(ConfigError) as excinfo:
        load_config(project_root, notice_stream=open(project_root / "n.log", "w"))
    problems = excinfo.value.problems
    assert len(problems) == 1
    assert problems[0].file.endswith("cities.yaml")
    assert problems[0].path == "unexpected_key"
    assert "extra" in problems[0].problem.lower()


def test_invalid_constraint_status_is_rejected(project_root: Path):
    path = project_root / "config" / "programme_constraints.yaml"
    path.write_text(path.read_text().replace("status: VERIFIED\n", "status: TRUE\n", 1))
    with pytest.raises(ConfigError) as excinfo:
        load_config(project_root, notice_stream=open(project_root / "n.log", "w"))
    assert excinfo.value.problems[0].path == "0.status"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("杭州", CityClass.primary),
        ("杭州市", CityClass.primary),
        ("Hangzhou", CityClass.primary),
        ("hangzhou city", CityClass.primary),
        ("Shanghai City", CityClass.primary),
        ("苏州市", CityClass.secondary),
        ("Ningbo", CityClass.expanded),
        ("北京", CityClass.out),
        ("Shenzhen", CityClass.out),
        ("", CityClass.unknown),
        (None, CityClass.unknown),
    ],
)
def test_city_classification(config, name, expected):
    assert config.cities.classify(name) == expected
