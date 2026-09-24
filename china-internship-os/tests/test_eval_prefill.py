"""scripts/eval_prefill.py: measures Jev against hand-labelled postings (fake provider here)."""

from __future__ import annotations

import importlib.util
import json

import pytest

from internship_os import decision_provider as dp
from tests.conftest import PROJECT_DIR

SCRIPT = PROJECT_DIR / "scripts" / "eval_prefill.py"


def _load():
    spec = importlib.util.spec_from_file_location("eval_prefill", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows(path, rows):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def test_example_file_is_valid_and_synthetic():
    example = PROJECT_DIR / "data" / "labelled_postings.example.jsonl"
    rows = [json.loads(line) for line in example.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows and all(_load().validate_row(r) is None for r in rows)


def test_real_labelled_data_is_gitignored():
    gitignore = (PROJECT_DIR / ".gitignore").read_text(encoding="utf-8")
    assert "data/labelled_postings.jsonl" in gitignore


def test_eval_reports_accuracy_per_question(config, project_root, monkeypatch, capsys):
    module = _load()
    data = project_root / "labelled.jsonl"
    _rows(data, [
        {"lang": "zh", "text": "岗位A", "labels": {"degree": "bachelor", "pays_fee": False}},
        {"lang": "en", "text": "Job B", "labels": {"degree": "master", "pays_fee": True}},
    ])
    canned = {"degree": dp.Decision("choice", "bachelor", 0.9, {}), "pays_fee": dp.Decision("noul", 0.1, None, {})}
    monkeypatch.setattr(module, "get_provider", lambda config, force=False: dp.FakeDecisionProvider(canned, model="jev-test"))
    assert module.main(["--data", str(data)]) == 0
    out = capsys.readouterr().out
    assert "model jev-test" in out
    assert "degree" in out and "1/2" in out  # right on the zh row, wrong on the en row


def test_eval_rejects_bad_labels_before_calling_jev(config, project_root, monkeypatch):
    module = _load()
    data = project_root / "labelled.jsonl"
    _rows(data, [{"lang": "zh", "text": "岗位", "labels": {"degree": "doctorate"}}])
    monkeypatch.setattr(module, "get_provider", lambda config, force=False: pytest.fail("Jev was called"))
    with pytest.raises(SystemExit) as exc:
        module.main(["--data", str(data)])
    assert "row 1" in str(exc.value)


def test_eval_without_a_key_exits_with_one_line(config, project_root):
    module = _load()
    data = project_root / "labelled.jsonl"
    _rows(data, [{"lang": "zh", "text": "岗位", "labels": {"degree": "bachelor"}}])
    with pytest.raises(SystemExit) as exc:
        module.main(["--data", str(data)])
    assert "TYPESAFE_API_KEY" in str(exc.value)


@pytest.mark.parametrize("labels", [{"track": ["AI"]}, {"track": {"a": 1}}, {"restricted": 1}])
def test_malformed_labels_are_reported_not_crashed_on(labels):
    problem = _load().validate_row({"lang": "zh", "text": "岗位", "labels": labels})
    assert problem is not None
