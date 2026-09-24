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


def test_committed_decisions_file_is_valid_and_pins_a_version():
    import re

    from tests.conftest import PROJECT_DIR

    cfg = dp.load_decisions(PROJECT_DIR)
    assert re.fullmatch(r"jev-\d+\.\d+\.\d+", cfg.model)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"TYPESAFE_API_KEY=apikey_a  # my key\n", "apikey_a"),
        (b'TYPESAFE_API_KEY="apikey_b"\n', "apikey_b"),
        (b"TYPESAFE_API_KEY=old\nTYPESAFE_API_KEY=new\n", "new"),
        (b"TYPESAFE_API_KEY=\nTYPESAFE_API_KEY=real\n", "real"),
        ("﻿TYPESAFE_API_KEY=bom\n".encode("utf-8"), "bom"),
        (b"export\tTYPESAFE_API_KEY=tab\n", "tab"),
        (b"TYPESAFE_API_KEY = spaced\r\n", "spaced"),
        (b"\xe9 latin-1 junk\nTYPESAFE_API_KEY=survives\n", "survives"),
        (b"# TYPESAFE_API_KEY=commented_out\n", None),
    ],
)
def test_env_file_parsing(project_root, content, expected):
    (project_root / ".env").write_bytes(content)
    assert dp.read_api_key(project_root) == expected


def test_whitespace_only_environment_key_is_ignored(project_root, monkeypatch):
    (project_root / ".env").write_text("TYPESAFE_API_KEY=from_file\n", encoding="utf-8")
    monkeypatch.setenv("TYPESAFE_API_KEY", "   ")
    assert dp.read_api_key(project_root) == "from_file"


def test_unreadable_env_file_means_no_key(project_root):
    env = project_root / ".env"
    env.write_text("TYPESAFE_API_KEY=k\n", encoding="utf-8")
    env.chmod(0)
    try:
        assert dp.read_api_key(project_root) is None
    finally:
        env.chmod(0o600)


def test_reading_the_key_never_puts_it_in_the_environment(config, project_root):
    (project_root / "config" / "decisions.yaml").write_text("provider: typesafe\n", encoding="utf-8")
    (project_root / ".env").write_text("TYPESAFE_API_KEY=apikey_test\n", encoding="utf-8")
    dp.get_provider(config)
    assert "TYPESAFE_API_KEY" not in os.environ


def test_requests_always_go_to_api_typesafe_ai(monkeypatch):
    monkeypatch.setenv("TYPESAFE_BASE_URL", "https://elsewhere.invalid")
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        return httpx2.Response(200, json={"model": "m", "usage": {"input_tokens": 1}, "answers": {}})

    _mock(handler).ask("text", {"q": {"type": "noul", "instructions": "x"}})
    assert hosts == ["api.typesafe.ai"]


def test_debug_logging_never_records_the_posting_text(caplog):
    caplog.set_level(logging.DEBUG, logger="typesafe_sdk")

    def handler(request):
        return httpx2.Response(200, json={"model": "m", "usage": {"input_tokens": 1}, "answers": {}})

    _mock(handler).ask({"posting": "MARKER-POSTING-TEXT"}, {"q": {"type": "noul", "instructions": "x"}})
    assert not any("MARKER-POSTING-TEXT" in record.getMessage() for record in caplog.records)


def test_the_claude_subprocess_never_sees_the_typesafe_key(monkeypatch):
    from internship_os import llm

    monkeypatch.setenv("TYPESAFE_API_KEY", "apikey_exported")
    assert "TYPESAFE_API_KEY" not in llm.subscription_env()


def test_the_test_guard_stops_a_real_typesafe_call():
    provider = dp.TypeSafeProvider(api_key="apikey_test", model="jev-1.13.0", timeout=1, connect_timeout=1)
    with pytest.raises(pytest.fail.Exception):
        provider.ask("text", {"q": {"type": "noul", "instructions": "x"}})
