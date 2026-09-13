"""Claude Code CLI provider: command shape, subscription-only environment, rate-limit waiting,
structured output, and the resume guard. No test runs the real CLI."""

import json
import subprocess

import pytest

from internship_os import llm
from internship_os.config import AppConfig
from internship_os.schemas import QualityChecklist
from tests.conftest import ORIGINAL_CLAUDE_CODE_CALL


def _payload(**overrides):
    base = {"type": "result", "subtype": "success", "is_error": False, "result": "OK",
            "structured_output": None, "usage": {"input_tokens": 2, "cache_creation_input_tokens": 10,
            "cache_read_input_tokens": 5, "output_tokens": 3}}
    base.update(overrides)
    return base


def test_claude_code_command_is_a_plain_completion_on_the_subscription(config, monkeypatch):
    cmd = llm.claude_code_command("claude", "sonnet", {"type": "object"})
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[cmd.index("--tools") + 1] == ""
    assert "--no-session-persistence" in cmd and "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert "--json-schema" in cmd and "--max-turns" not in cmd
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    env = llm.subscription_env()
    assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env


def test_claude_code_call_passes_prompt_on_stdin_and_strips_api_key(config, monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(_payload()), stderr="")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    result = ORIGINAL_CLAUDE_CODE_CALL("the prompt", "opus", None, config)
    assert result.text == "OK" and result.input_tokens == 17 and result.output_tokens == 3
    assert seen["kwargs"]["input"] == "the prompt"
    assert "ANTHROPIC_API_KEY" not in seen["kwargs"]["env"]
    assert seen["kwargs"]["timeout"] == llm.CLAUDE_CODE_TIMEOUT_SECONDS
    assert "the prompt" not in " ".join(seen["cmd"])


def test_rate_limit_waits_and_retries_until_success(config, monkeypatch):
    calls = []
    sleeps = []
    responses = [
        _payload(is_error=True, result="You've hit your session limit. Your allowance resets at 3pm."),
        _payload(is_error=True, result="Rate limited, please try again later"),
        _payload(result="done"),
    ]

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(responses[len(calls) - 1]), stderr="")

    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    monkeypatch.setattr(llm, "_sleep", lambda s: sleeps.append(s))
    result = ORIGINAL_CLAUDE_CODE_CALL("p", "sonnet", None, config)
    assert result.text == "done"
    assert len(calls) == 3 and sleeps == [60, 120]


def test_rate_limit_respects_max_wait_minutes(config, monkeypatch):
    facts = config.user_facts.model_copy(deep=True)
    facts.llm.max_wait_minutes = 2
    cfg = AppConfig(root=config.root, user_facts=facts, constraints=config.constraints, evidence=config.evidence, cities=config.cities)
    sleeps = []
    monkeypatch.setattr(llm.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(
        cmd, 1, stdout=json.dumps(_payload(is_error=True, result="usage limit reached; resets at 6pm")), stderr=""))
    monkeypatch.setattr(llm, "_sleep", lambda s: sleeps.append(s))
    with pytest.raises(llm.LLMError, match="max_wait_minutes"):
        ORIGINAL_CLAUDE_CODE_CALL("p", "sonnet", None, cfg)
    assert sleeps == [60]  # 60 s fits in 2 minutes, the next 120 s would not


def test_non_rate_limit_error_is_not_retried(config, monkeypatch):
    calls = []
    monkeypatch.setattr(llm.subprocess, "run", lambda cmd, **k: (calls.append(cmd), subprocess.CompletedProcess(
        cmd, 1, stdout=json.dumps(_payload(is_error=True, result="Invalid request: prompt too long")), stderr=""))[1])
    monkeypatch.setattr(llm, "_sleep", lambda s: pytest.fail("must not sleep"))
    with pytest.raises(llm.LLMError, match="prompt too long"):
        ORIGINAL_CLAUDE_CODE_CALL("p", "sonnet", None, config)
    assert len(calls) == 1


def test_structured_output_is_used_directly_and_text_is_the_fallback(config, monkeypatch):
    payloads = iter([
        _payload(result="ignored", structured_output={"signals": [{"signal": "APIs", "present": True, "note": None}]}),
        _payload(result='```json\n{"signals": []}\n```'),
    ])
    monkeypatch.setattr(llm.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(next(payloads)), stderr=""))
    monkeypatch.setattr(llm, "_claude_code_call", ORIGINAL_CLAUDE_CODE_CALL)
    first = llm.complete("quality_checklist", {"responsibilities": "x", "required_skills": [], "title": "t"}, QualityChecklist, config=config)
    assert isinstance(first, QualityChecklist) and first.signals[0].signal == "APIs"
    second = llm.complete("quality_checklist", {"responsibilities": "x", "required_skills": [], "title": "t"}, QualityChecklist, config=config)
    assert isinstance(second, QualityChecklist) and second.signals == []


def test_resume_guard_blocks_hosted_model_without_opt_in(config):
    with pytest.raises(llm.ResumeUploadBlocked, match="allow_resume_upload"):
        llm.complete("tailor_bullets", {"resume_text": "secret"}, None, config=config)


def test_rate_limit_detection_wording():
    for text in ("You've hit your session limit. Your allowance resets at 3pm.", "usage limit reached",
                 "Rate limited", "API Error: 429 Too Many Requests", "overloaded_error", "weekly limit"):
        assert llm.looks_like_rate_limit(text), text
    for text in ("There's an issue with the selected model", "prompt too long", ""):
        assert not llm.looks_like_rate_limit(text), text
