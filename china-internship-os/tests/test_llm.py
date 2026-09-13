"""Claude Code CLI provider: command shape, subscription-only environment, rate-limit waiting,
structured output, validation retry, the resume guard and llm-check. No test runs the real CLI;
the autouse guard in conftest blocks subprocess.run unless a test stubs it."""

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
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd[cmd.index("--system-prompt") + 1] == llm.CLAUDE_CODE_SYSTEM_PROMPT
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
    assert seen["kwargs"]["cwd"] == config.root and seen["kwargs"]["capture_output"] is True
    assert seen["kwargs"]["timeout"] == llm.CLAUDE_CODE_TIMEOUT_SECONDS
    assert "the prompt" not in " ".join(seen["cmd"])


def test_rate_limit_waits_and_retries_until_success(config, monkeypatch):
    calls = []
    sleeps = []
    responses = [
        _payload(is_error=True, result="You've hit your session limit · resets 8:50am (UTC)"),
        _payload(is_error=True, result="You've hit your Opus limit · resets Sep 20, 3pm (Asia/Shanghai)"),
        _payload(is_error=True, result="Opus is experiencing high load, please use /model to switch to Sonnet"),
        {"type": "result", "subtype": "error_during_execution", "is_error": True, "errors": ["Rate limited, please try again later"]},
        _payload(is_error=True, result="Internal error", api_error_status=529),
        _payload(result="done"),
    ]

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(responses[len(calls) - 1]), stderr="")

    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    monkeypatch.setattr(llm, "_sleep", lambda s: sleeps.append(s) if len(sleeps) < 10 else pytest.fail("runaway"))
    result = ORIGINAL_CLAUDE_CODE_CALL("p", "sonnet", None, config)
    assert result.text == "done"
    assert len(calls) == 6 and sleeps == [60, 120, 300, 300, 300]  # no cap: keeps waiting at the last delay


def test_rate_limit_respects_max_wait_minutes(config, monkeypatch):
    def cfg_with(minutes):
        facts = config.user_facts.model_copy(deep=True)
        facts.llm.max_wait_minutes = minutes
        return AppConfig(root=config.root, user_facts=facts, constraints=config.constraints, evidence=config.evidence, cities=config.cities)

    monkeypatch.setattr(llm.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(
        cmd, 1, stdout=json.dumps(_payload(is_error=True, result="usage limit reached; resets at 6pm")), stderr=""))
    sleeps = []
    monkeypatch.setattr(llm, "_sleep", lambda s: sleeps.append(s) if len(sleeps) < 10 else pytest.fail("runaway"))
    with pytest.raises(llm.LLMError, match="max_wait_minutes"):
        ORIGINAL_CLAUDE_CODE_CALL("p", "sonnet", None, cfg_with(3))
    assert sleeps == [60, 120]  # the whole 3-minute budget is used, then it gives up
    sleeps.clear()
    with pytest.raises(llm.LLMError, match="max_wait_minutes"):
        ORIGINAL_CLAUDE_CODE_CALL("p", "sonnet", None, cfg_with(2))
    assert sleeps == [60, 60]  # the second delay is clamped to the remaining budget
    sleeps.clear()
    with pytest.raises(llm.LLMError, match="max_wait_minutes"):
        ORIGINAL_CLAUDE_CODE_CALL("p", "sonnet", None, cfg_with(0))
    assert sleeps == []


def test_non_rate_limit_error_is_not_retried(config, monkeypatch):
    calls = []
    monkeypatch.setattr(llm.subprocess, "run", lambda cmd, **k: (calls.append(cmd), subprocess.CompletedProcess(
        cmd, 1, stdout=json.dumps(_payload(is_error=True, result="Invalid request: prompt too long")), stderr=""))[1])
    monkeypatch.setattr(llm, "_sleep", lambda s: pytest.fail("must not sleep"))
    with pytest.raises(llm.LLMError, match="prompt too long"):
        ORIGINAL_CLAUDE_CODE_CALL("p", "sonnet", None, config)
    assert len(calls) == 1


def test_structured_output_is_used_directly_and_text_is_the_fallback(config, monkeypatch):
    payloads = [
        _payload(result="ignored", structured_output={"signals": [{"signal": "APIs", "present": True, "note": None}]}),
        _payload(result='```json\n{"signals": []}\n```'),
        {"type": "result", "subtype": "error_max_structured_output_retries", "is_error": True,
         "result": '{"signals": [{"signal": "RAG", "present": null, "note": null}]}', "errors": ["max retries"]},
    ]
    cmds = []

    def fake_run(cmd, **k):
        cmds.append(cmd)
        if not payloads:
            pytest.fail("more CLI calls than expected")
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payloads.pop(0)), stderr="")

    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    monkeypatch.setattr(llm, "_claude_code_call", ORIGINAL_CLAUDE_CODE_CALL)
    variables = {"responsibilities": "x", "required_skills": [], "title": "t"}
    first = llm.complete("quality_checklist", variables, QualityChecklist, config=config)
    assert isinstance(first, QualityChecklist) and first.signals[0].signal == "APIs"
    second = llm.complete("quality_checklist", variables, QualityChecklist, config=config)
    assert isinstance(second, QualityChecklist) and second.signals == []
    # The CLI gave up on the StructuredOutput tool but the text still parses.
    third = llm.complete("quality_checklist", variables, QualityChecklist, config=config)
    assert isinstance(third, QualityChecklist) and third.signals[0].signal == "RAG"
    # Per-prompt routing and the schema reach the actual command line.
    cmd = cmds[0]
    assert cmd[cmd.index("--model") + 1] == config.user_facts.llm.models.extraction
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == QualityChecklist.model_json_schema()


def test_validation_failure_retries_exactly_once_with_the_error(config, monkeypatch):
    from internship_os.drafts import BulletsOutput

    prompts = []
    payloads = [_payload(result='{"bullets": "not a list"}'), _payload(result='{"bullets": ["ok [EV_F1_DASHBOARD]"]}')]

    def fake_run(cmd, **k):
        prompts.append((cmd, k["input"]))
        if not payloads:
            pytest.fail("a third CLI call was made")
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payloads.pop(0)), stderr="")

    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    monkeypatch.setattr(llm, "_claude_code_call", ORIGINAL_CLAUDE_CODE_CALL)
    variables = {"title": "t", "company": "c", "required_skills": [], "preferred_skills": [], "responsibilities": "", "evidence_json": "[]", "min_bullets": 4, "max_bullets": 6}
    result = llm.complete("tailor_bullets", variables, BulletsOutput, config=config)
    assert result.bullets == ["ok [EV_F1_DASHBOARD]"]
    assert len(prompts) == 2
    first_cmd, first_prompt = prompts[0]
    second_cmd, second_prompt = prompts[1]
    assert first_cmd[first_cmd.index("--model") + 1] == config.user_facts.llm.models.drafting
    assert second_prompt.startswith(first_prompt) and "previous response was rejected" in second_prompt
    assert "bullets" in second_prompt.split("previous response was rejected")[1]

    # Two bad answers -> LLMResponseError, still only two calls.
    payloads[:] = [_payload(result="nope"), _payload(result="still nope")]
    prompts.clear()
    with pytest.raises(llm.LLMResponseError, match="twice"):
        llm.complete("tailor_bullets", variables, BulletsOutput, config=config)
    assert len(prompts) == 2


def test_cli_error_shapes_and_parsing(config, monkeypatch):
    # errors[] variant carries the real reason and the subtype.
    monkeypatch.setattr(llm.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, stdout=json.dumps(
        {"type": "result", "subtype": "error_during_execution", "is_error": True, "errors": ["boom happened"]}), stderr=""))
    with pytest.raises(llm.LLMError, match="error_during_execution.*boom happened"):
        ORIGINAL_CLAUDE_CODE_CALL("p", "sonnet", None, config)
    # Stray lines before and after the result object are ignored.
    noisy = "warning: something\n" + json.dumps(_payload(result="clean")) + "\nanother line\n"
    monkeypatch.setattr(llm.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, stdout=noisy, stderr=""))
    assert ORIGINAL_CLAUDE_CODE_CALL("p", "sonnet", None, config).text == "clean"
    # A non-executable claude_command is a configuration error, not a traceback.
    def denied(*a, **k):
        raise PermissionError("not executable")
    monkeypatch.setattr(llm.subprocess, "run", denied)
    with pytest.raises(llm.LLMConfigError, match="could not run"):
        ORIGINAL_CLAUDE_CODE_CALL("p", "sonnet", None, config)
    # Empty stdout and a timeout each give a clear error.
    monkeypatch.setattr(llm.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="Not logged in"))
    with pytest.raises(llm.LLMError, match="no JSON result"):
        ORIGINAL_CLAUDE_CODE_CALL("p", "sonnet", None, config)
    def slow(*a, **k):
        raise subprocess.TimeoutExpired(a[0], 900)
    monkeypatch.setattr(llm.subprocess, "run", slow)
    with pytest.raises(llm.LLMError, match="did not answer"):
        ORIGINAL_CLAUDE_CODE_CALL("p", "sonnet", None, config)
    # Fence stripping and brace slicing.
    assert llm.strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert llm.strip_code_fences('```\n[1]\n```') == '[1]'
    assert llm.parse_json_object('Here you go:\n```json\n{"a": 1}\n```\nDone.') == {"a": 1}


def test_resume_guard_opt_in_and_ollama_exemption(config, monkeypatch):
    facts = config.user_facts.model_copy(deep=True)
    facts.llm.allow_resume_upload = True
    cfg = AppConfig(root=config.root, user_facts=facts, constraints=config.constraints, evidence=config.evidence, cities=config.cities)
    seen = {}
    monkeypatch.setattr(llm.subprocess, "run", lambda cmd, **k: (seen.update(cmd=cmd, input=k["input"]), subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(_payload(result="ok")), stderr=""))[1])
    monkeypatch.setattr(llm, "_claude_code_call", ORIGINAL_CLAUDE_CODE_CALL)
    monkeypatch.setattr(llm, "load_template", lambda name, root=None: "R: {{resume_text}}")
    assert llm.complete("tailor_bullets", {"resume_text": "secret"}, None, config=cfg) == "ok"
    assert "secret" in seen["input"] and "secret" not in " ".join(seen["cmd"])
    facts2 = config.user_facts.model_copy(deep=True)
    facts2.llm.provider = "ollama"
    cfg2 = AppConfig(root=config.root, user_facts=facts2, constraints=config.constraints, evidence=config.evidence, cities=config.cities)
    monkeypatch.setattr(llm, "_ollama_call", lambda prompt, model, want_json: llm.ProviderResult(text="local"))
    assert llm.complete("tailor_bullets", {"resume_text": "secret"}, None, config=cfg2) == "local"


def test_llm_check_command(project_root, engine, monkeypatch):
    from typer.testing import CliRunner

    from internship_os.cli import app

    def fake_run(cmd, **k):
        if cmd[1:] == ["--version"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="2.0.0 (Claude Code)\n", stderr="")
        assert cmd[1:] == ["auth", "status"]
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(fake_run.status), stderr="")

    fake_run.status = {"loggedIn": True, "authMethod": "oauth_token", "apiProvider": "firstParty"}
    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    result = CliRunner().invoke(app, ["llm-check"])
    assert result.exit_code == 0, result.output
    assert "version 2.0.0" in result.output and "logged in: True" in result.output
    assert "extraction=sonnet" in result.output and "drafting=opus" in result.output
    fake_run.status = {"loggedIn": False}
    result = CliRunner().invoke(app, ["llm-check"])
    assert result.exit_code == 1 and "claude auth login" in result.output
    monkeypatch.setattr(llm.subprocess, "run", lambda cmd, **k: (_ for _ in ()).throw(FileNotFoundError()))
    result = CliRunner().invoke(app, ["llm-check"])
    assert result.exit_code == 1 and "not found" in result.output


def test_legacy_llm_block_gets_a_migration_message(project_root):
    from internship_os.config import ConfigError, load_config

    uf = project_root / "config" / "user_facts.yaml"
    load_config(project_root, notice_stream=open(project_root / "n.log", "w"))
    text = uf.read_text()
    start = text.index("llm:")
    uf.write_text(text[:start] + "llm:\n  provider: anthropic\n  model: claude-sonnet-4-6\n  allow_resume_upload_to_api: false\n")
    with pytest.raises(ConfigError) as excinfo:
        load_config(project_root, notice_stream=open(project_root / "n.log", "w"))
    problems = excinfo.value.problems
    assert problems[0].path == "llm"
    assert "models: {extraction: sonnet, drafting: opus}" in problems[0].problem
    assert "allow_resume_upload" in problems[0].problem and "claude_code" in problems[0].problem


def test_resume_guard_blocks_hosted_model_without_opt_in(config):
    with pytest.raises(llm.ResumeUploadBlocked, match="allow_resume_upload"):
        llm.complete("tailor_bullets", {"resume_text": "secret"}, None, config=config)


def test_rate_limit_detection_wording():
    for text in ("You've hit your session limit. Your allowance resets at 3pm.", "usage limit reached",
                 "Rate limited", "API Error: 429 Too Many Requests", "overloaded_error", "weekly limit",
                 "You've hit your session limit · resets 8:50am (UTC)",
                 "You've hit your Opus limit · resets Sep 20, 3pm (Asia/Shanghai)",
                 "You've hit your Sonnet limit · resets 3pm (Asia/Shanghai)",
                 "You've hit your usage credit limit · resets tomorrow",
                 "Sonnet is experiencing high load, please use /model to switch to Opus"):
        assert llm.looks_like_rate_limit(text), text
    for text in ("There's an issue with the selected model", "prompt too long", ""):
        assert not llm.looks_like_rate_limit(text), text
