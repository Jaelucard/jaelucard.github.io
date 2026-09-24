"""The Jev (TypeSafe) decision provider: configuration, key handling and answer mapping."""

from __future__ import annotations

import json
import logging
import os

import httpx2
import pytest

from internship_os import decision_provider as dp
from internship_os.config import ConfigError


def _write_decisions(project_root, text: str) -> None:
    (project_root / "config" / "decisions.yaml").write_text(text, encoding="utf-8")


def test_provider_is_off_without_a_decisions_file(config):
    provider = dp.get_provider(config)
    assert isinstance(provider, dp.NullProvider) and "provider: none" in provider.reason


def test_provider_is_off_without_a_key(config, project_root):
    _write_decisions(project_root, "provider: typesafe\n")
    provider = dp.get_provider(config)
    assert isinstance(provider, dp.NullProvider) and "TYPESAFE_API_KEY" in provider.reason


def test_key_is_read_from_dotenv_without_touching_the_environment(project_root):
    (project_root / ".env").write_text(
        "# local secrets\nOLLAMA_MODEL=qwen\nexport TYPESAFE_API_KEY='apikey_test'\n", encoding="utf-8"
    )
    assert dp.read_api_key(project_root) == "apikey_test"
    assert "TYPESAFE_API_KEY" not in os.environ


def test_environment_key_takes_precedence(project_root, monkeypatch):
    (project_root / ".env").write_text("TYPESAFE_API_KEY=from_file\n", encoding="utf-8")
    monkeypatch.setenv("TYPESAFE_API_KEY", "from_env")
    assert dp.read_api_key(project_root) == "from_env"


def test_provider_is_on_with_config_and_key(config, project_root):
    _write_decisions(project_root, "provider: typesafe\nmodel: jev-1.13.0\n")
    (project_root / ".env").write_text("TYPESAFE_API_KEY=apikey_test\n", encoding="utf-8")
    provider = dp.get_provider(config)
    assert isinstance(provider, dp.TypeSafeProvider) and provider.model == "jev-1.13.0"


def test_force_turns_the_provider_on_despite_provider_none(config, project_root):
    _write_decisions(project_root, "provider: none\n")
    (project_root / ".env").write_text("TYPESAFE_API_KEY=apikey_test\n", encoding="utf-8")
    assert isinstance(dp.get_provider(config, force=True), dp.TypeSafeProvider)


def test_invalid_decisions_file_is_a_config_error(config, project_root):
    _write_decisions(project_root, "provider: sometimes\n")
    with pytest.raises(ConfigError):
        dp.load_decisions(project_root)


def _mock(handler):
    return dp.TypeSafeProvider(api_key="apikey_test", model="jev-1.13.0", timeout=8, connect_timeout=3,
                               transport=httpx2.MockTransport(handler))


def test_typesafe_provider_maps_choice_and_noul_answers():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json={
            "model": "jev-1.13.0",
            "usage": {"input_tokens": 50},
            "answers": {
                "track": {"type": "choice", "choice": "AI", "confidence": 0.81, "probabilities": {"AI": 0.9, "SWE": 0.1}},
                "pays_fee": {"type": "noul", "noul": 0.04},
            },
        })

    questions = {
        "track": {"type": "choice", "instructions": "Which role", "criteria": {"AI": "ml", "SWE": "sw"}},
        "pays_fee": {"type": "noul", "instructions": "Asks for a fee"},
        "missing": {"type": "noul", "instructions": "Not answered"},
    }
    batch = _mock(handler).ask({"source_text": "岗位"}, questions)
    assert seen["body"]["model"] == "jev-1.13.0" and seen["body"]["state"] == {"source_text": "岗位"}
    assert batch.model == "jev-1.13.0"
    assert batch.decisions["track"] == dp.Decision("choice", "AI", 0.81, {"AI": 0.9, "SWE": 0.1})
    assert batch.decisions["pays_fee"] == dp.Decision("noul", 0.04, None, {})
    assert "missing" not in batch.decisions


def test_typesafe_provider_does_not_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(503, json={"error": "busy"})

    with pytest.raises(Exception):
        _mock(handler).ask("text", {"q": {"type": "noul", "instructions": "x"}})
    assert len(calls) == 1


def test_sdk_debug_logging_is_capped():
    _mock(lambda request: httpx2.Response(200, json={"model": "m", "answers": {}}))
    assert logging.getLogger("typesafe_sdk").getEffectiveLevel() >= logging.INFO


def test_ask_safely_reports_the_error_class_instead_of_raising():
    provider = dp.FakeDecisionProvider({}, raises=TimeoutError("slow"))
    batch, error = dp.ask_safely(provider, "text", {"q": {"type": "noul", "instructions": "x"}})
    assert batch is None and error == "TimeoutError"


def test_fake_provider_returns_only_requested_keys():
    canned = {"a": dp.Decision("noul", 0.9, None, {}), "b": dp.Decision("noul", 0.1, None, {})}
    batch = dp.FakeDecisionProvider(canned).ask("text", {"a": {"type": "noul"}})
    assert set(batch.decisions) == {"a"}
