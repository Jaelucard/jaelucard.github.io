"""LLM access. The only module that talks to an LLM provider.

Providers:

* ``claude_code``: runs the official Claude Code CLI in print mode (``claude -p``) as a
  subprocess. It uses the user's logged-in Claude subscription; no API key is involved and the
  ``ANTHROPIC_API_KEY`` / ``ANTHROPIC_AUTH_TOKEN`` variables are stripped from the subprocess
  environment so a stray key can never switch it to pay-per-token billing (``TYPESAFE_API_KEY``
  is stripped too: the Jev key never leaves this process). Tools, hooks, MCP
  servers, project settings and session persistence are all disabled, so each call is a plain
  completion.
* ``ollama``: POST to a local Ollama server.

The LLM is used for extraction, translation, quality-signal extraction, drafting and interview
question generation. It never decides eligibility, programme compatibility, tier, pipeline
state, deadlines, deduplication or timing.

Logging records prompt name, provider, model, token counts and success/failure only. Prompt
content and generated content are never logged.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from internship_os.config import AppConfig, load_config, prompts_dir
from internship_os.schemas import LLMProvider

log = logging.getLogger("internship_os.llm")

OLLAMA_URL = "http://localhost:11434/api/generate"
RESUME_VARIABLE = "resume_text"

# Which configured model each prompt uses: user_facts.llm.models.<role>.
PROMPT_ROLES: dict[str, str] = {
    "extract_job": "extraction",
    "quality_checklist": "extraction",
    "recruiter_message": "drafting",
    "yes_explanation": "drafting",
    "tailor_bullets": "drafting",
    "interview_prep": "drafting",
}
DEFAULT_ROLE = "drafting"

CLAUDE_CODE_SYSTEM_PROMPT = (
    "You are a structured-data extraction and drafting engine used by a local command-line "
    "tool. Follow the instructions in the user message exactly and output only what they ask "
    "for. Never add commentary and never ask questions. Do not use any tool except "
    "StructuredOutput when it is offered; when it is offered, answer by calling it."
)
CLAUDE_CODE_TIMEOUT_SECONDS = 900
# Variables that would make the CLI bill an API account instead of using the subscription.
STRIPPED_ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "TYPESAFE_API_KEY")
# The CLI words subscription limits as "You've hit your <session|weekly|Opus|Sonnet|Fable|usage
# credit> limit · resets <time>"; overloads as "<model> is experiencing high load".
RATE_LIMIT_PATTERN = re.compile(
    r"hit your [^.\n]{0,40}limit|\blimit\b[^.\n]{0,40}\bresets?\b|(usage|session|rate|weekly|daily)\s+limit|"
    r"allowance|resets? at|too many requests|rate.?limited|overloaded|experiencing high load|\b429\b|\b529\b",
    re.IGNORECASE,
)
RATE_LIMIT_HTTP_STATUSES = (429, 529)
STRUCTURED_OUTPUT_RETRY_SUBTYPE = "error_max_structured_output_retries"
RETRY_DELAYS_SECONDS = (60, 120, 300)  # then the last value repeats
_sleep = time.sleep  # patched by tests


class LLMError(Exception):
    """Base class for LLM failures."""


class LLMConfigError(LLMError):
    """Provider or template configuration problem."""


class LLMResponseError(LLMError):
    """The model did not return valid structured output after one retry."""


class ResumeUploadBlocked(LLMError):
    """A resume would have been sent to a hosted model without explicit permission."""


@dataclass
class ProviderResult:
    text: str
    structured: Any | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


# Test hook. A fake provider receives (prompt_name, rendered_prompt) and returns raw text.
FakeProvider = Callable[[str, str], str]
_fake_provider: FakeProvider | None = None


def set_fake_provider(fn: FakeProvider | None) -> None:
    """Install (or clear with None) a fake provider. Tests use this; production never does."""
    global _fake_provider
    _fake_provider = fn


@contextmanager
def fake_provider(fn: FakeProvider) -> Iterator[None]:
    previous = _fake_provider
    set_fake_provider(fn)
    try:
        yield
    finally:
        set_fake_provider(previous)


# --------------------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------------------

_VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
SCHEMA_VARIABLE = "json_schema"


def load_template(prompt_name: str, root: Path | None = None) -> str:
    path = prompts_dir(root) / f"{prompt_name}.md"
    if not path.exists():
        raise LLMConfigError(f"prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def render_template(template: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            raise LLMConfigError(f"prompt template variable {{{{{key}}}}} was not supplied")
        value = variables[key]
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return "" if value is None else str(value)

    return _VAR.sub(replace, template)


def build_prompt(
    prompt_name: str,
    variables: dict[str, Any],
    json_schema: type[BaseModel] | None,
    root: Path | None = None,
) -> str:
    template = load_template(prompt_name, root)
    supplied = dict(variables)
    schema_block = ""
    if json_schema is not None:
        schema_text = json.dumps(json_schema.model_json_schema(), ensure_ascii=False, indent=2)
        schema_block = (
            "Respond with a single JSON object and nothing else. It must validate against this "
            "JSON Schema:\n```json\n" + schema_text + "\n```"
        )
        supplied.setdefault(SCHEMA_VARIABLE, schema_block)
    prompt = render_template(template, supplied)
    if json_schema is not None and SCHEMA_VARIABLE not in _template_variables(template):
        prompt = prompt.rstrip() + "\n\n" + schema_block
    return prompt


def _template_variables(template: str) -> set[str]:
    return set(_VAR.findall(template))


# --------------------------------------------------------------------------------------
# Model routing
# --------------------------------------------------------------------------------------


def role_for(prompt_name: str) -> str:
    return PROMPT_ROLES.get(prompt_name, DEFAULT_ROLE)


def model_for(prompt_name: str, config: AppConfig) -> str:
    """The configured model for this prompt: user_facts.llm.models.<extraction|drafting>."""
    return getattr(config.user_facts.llm.models, role_for(prompt_name))


# --------------------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------------------


def claude_code_command(
    executable: str, model: str, json_schema: dict[str, Any] | None
) -> list[str]:
    """The exact ``claude -p`` invocation: a plain completion with everything else off."""
    cmd = [
        executable,
        "-p",
        "--output-format", "json",
        "--tools", "",
        "--no-session-persistence",
        "--setting-sources", "",
        "--strict-mcp-config",
        "--model", model,
        "--system-prompt", CLAUDE_CODE_SYSTEM_PROMPT,
    ]
    if json_schema is not None:
        cmd += ["--json-schema", json.dumps(json_schema, ensure_ascii=False)]
    return cmd


def subscription_env() -> dict[str, str]:
    """The subprocess environment with API-key variables removed."""
    return {k: v for k, v in os.environ.items() if k not in STRIPPED_ENV_VARS}


def looks_like_rate_limit(message: str) -> bool:
    return bool(RATE_LIMIT_PATTERN.search(message or ""))


def _parse_cli_json(stdout: str) -> dict[str, Any]:
    """The result object from the CLI's stdout, tolerating stray lines before or after it."""
    text = stdout.strip()
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            obj, _ = decoder.raw_decode(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            candidates.append(obj)
    if not candidates:
        # Pretty-printed multi-line JSON: try the whole text from its first brace.
        start = text.find("{")
        if start == -1:
            raise json.JSONDecodeError("no JSON object", text, 0)
        obj, _ = decoder.raw_decode(text[start:])
        if not isinstance(obj, dict):
            raise json.JSONDecodeError("expected a JSON object", text, 0)
        return obj
    results = [c for c in candidates if c.get("type") == "result"]
    return (results or candidates)[-1]


def cli_error_message(data: dict[str, Any]) -> str:
    """Error text from either CLI result shape: ``result`` (success subtype) or ``errors``."""
    errors = data.get("errors")
    if isinstance(errors, list) and errors:
        return "; ".join(str(e) for e in errors)
    return str(data.get("result") or data.get("error") or f"subtype={data.get('subtype')}")


def _claude_code_call(
    prompt: str, model: str, json_schema: dict[str, Any] | None, config: AppConfig
) -> ProviderResult:
    executable = config.user_facts.llm.claude_command
    cmd = claude_code_command(executable, model, json_schema)
    env = subscription_env()
    max_wait = config.user_facts.llm.max_wait_minutes
    waited = 0
    attempt = 0
    while True:
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=CLAUDE_CODE_TIMEOUT_SECONDS,
                env=env,
                cwd=config.root,
            )
        except FileNotFoundError:
            raise LLMConfigError(
                f"the Claude Code CLI ({executable!r}) was not found on PATH. Install it with "
                "'npm install -g @anthropic-ai/claude-code', run 'claude auth login', or set "
                "user_facts.llm.claude_command to its full path."
            ) from None
        except OSError as exc:
            raise LLMConfigError(f"could not run the Claude Code CLI ({executable!r}): {exc}") from None
        except subprocess.TimeoutExpired:
            raise LLMError(
                f"the Claude Code CLI did not answer within {CLAUDE_CODE_TIMEOUT_SECONDS} seconds"
            ) from None
        try:
            data = _parse_cli_json(proc.stdout)
        except json.JSONDecodeError:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            tail = detail[-1][:300] if detail else "no output"
            raise LLMError(
                f"the Claude Code CLI returned no JSON result (exit code {proc.returncode}): {tail}. "
                "Check that you are logged in: run 'claude auth status'."
            ) from None
        if proc.returncode != 0 and not data.get("is_error") and not data.get("result"):
            tail = (proc.stderr or "").strip().splitlines()
            raise LLMError(
                f"the Claude Code CLI exited with code {proc.returncode} without a result"
                + (f": {tail[-1][:300]}" if tail else "")
                + ". Check that you are logged in: run 'claude auth status'."
            )
        if data.get("is_error"):
            message = cli_error_message(data)
            subtype = str(data.get("subtype") or "")
            if subtype == STRUCTURED_OUTPUT_RETRY_SUBTYPE and data.get("result"):
                # The model answered in text instead of the StructuredOutput tool; let the
                # text parser and the one validation retry in complete() handle it.
                break
            status = data.get("api_error_status")
            if looks_like_rate_limit(message) or status in RATE_LIMIT_HTTP_STATUSES:
                delay = RETRY_DELAYS_SECONDS[min(attempt, len(RETRY_DELAYS_SECONDS) - 1)]
                if max_wait is not None:
                    remaining = max_wait * 60 - waited
                    if remaining <= 0:
                        raise LLMError(
                            f"Claude subscription limit reached and user_facts.llm.max_wait_minutes "
                            f"({max_wait}) exhausted: {message}"
                        )
                    delay = min(delay, remaining)
                log.warning(
                    "claude_code rate limit hit; waiting %s s before retry %s (%s)",
                    delay,
                    attempt + 1,
                    message[:160],
                )
                _sleep(delay)
                waited += delay
                attempt += 1
                continue
            raise LLMError(f"Claude Code returned an error ({subtype or 'error'}): {message}")
        break
    usage = data.get("usage") or {}
    input_tokens = None
    if isinstance(usage, dict) and "input_tokens" in usage:
        input_tokens = (
            int(usage.get("input_tokens") or 0)
            + int(usage.get("cache_creation_input_tokens") or 0)
            + int(usage.get("cache_read_input_tokens") or 0)
        )
    return ProviderResult(
        text=str(data.get("result") or ""),
        structured=data.get("structured_output"),
        input_tokens=input_tokens,
        output_tokens=usage.get("output_tokens") if isinstance(usage, dict) else None,
    )


def claude_code_status(config: AppConfig) -> dict[str, Any]:
    """Version and login state of the CLI, for ``ios llm-check``. Never raises on CLI errors."""
    executable = config.user_facts.llm.claude_command
    info: dict[str, Any] = {"executable": executable, "found": False}
    try:
        version = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=30, env=subscription_env()
        )
        info["found"] = True
        info["version"] = version.stdout.strip() or version.stderr.strip()
        status = subprocess.run(
            [executable, "auth", "status"], capture_output=True, text=True, timeout=30, env=subscription_env()
        )
        try:
            info.update(_parse_cli_json(status.stdout))
        except json.JSONDecodeError:
            info["auth_raw"] = (status.stdout or status.stderr).strip()[:300]
    except FileNotFoundError:
        info["error"] = f"{executable!r} not found on PATH"
    except OSError as exc:
        info["error"] = f"could not run {executable!r}: {exc}"
    except subprocess.TimeoutExpired:
        info["error"] = "the CLI did not respond"
    return info


def _ollama_call(prompt: str, model: str, want_json: bool) -> ProviderResult:
    payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
    if want_json:
        payload["format"] = "json"
    try:
        response = httpx.post(OLLAMA_URL, json=payload, timeout=180.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LLMError(f"Ollama request failed: {exc}") from exc
    data = response.json()
    return ProviderResult(
        text=str(data.get("response", "")),
        input_tokens=data.get("prompt_eval_count"),
        output_tokens=data.get("eval_count"),
    )


def _call_provider(
    prompt_name: str, prompt: str, config: AppConfig, json_schema: type[BaseModel] | None
) -> ProviderResult:
    provider = config.user_facts.llm.provider
    model = model_for(prompt_name, config)
    if _fake_provider is not None:
        result = ProviderResult(text=_fake_provider(prompt_name, prompt))
        provider_name = "fake"
    elif provider == LLMProvider.claude_code:
        provider_name = "claude_code"
        schema = json_schema.model_json_schema() if json_schema is not None else None
        result = _claude_code_call(prompt, model, schema, config)
    elif provider == LLMProvider.ollama:
        provider_name = "ollama"
        result = _ollama_call(prompt, model, json_schema is not None)
    else:  # pragma: no cover - config validation prevents this
        raise LLMConfigError(f"unknown provider {provider}")
    log.info(
        "llm call prompt=%s provider=%s model=%s input_tokens=%s output_tokens=%s status=success",
        prompt_name,
        provider_name,
        model,
        result.input_tokens,
        result.output_tokens,
    )
    return result


# --------------------------------------------------------------------------------------
# Structured output parsing
# --------------------------------------------------------------------------------------

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def strip_code_fences(text: str) -> str:
    match = _FENCE.match(text)
    if match:
        return match.group(1)
    return text.strip()


def parse_json_object(text: str) -> Any:
    cleaned = strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def parse_structured(text: str, json_schema: type[BaseModel]) -> BaseModel:
    """Strip fences, parse JSON, validate. Raises ValueError with a readable message."""
    try:
        data = parse_json_object(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"response was not valid JSON: {exc}") from exc
    return validate_data(data, json_schema)


def validate_data(data: Any, json_schema: type[BaseModel]) -> BaseModel:
    try:
        return json_schema.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            ".".join(str(p) for p in err["loc"]) + ": " + err["msg"] for err in exc.errors()
        )
        raise ValueError(f"response did not match the schema: {problems}") from exc


def _result_to_model(result: ProviderResult, json_schema: type[BaseModel]) -> BaseModel:
    if result.structured is not None:
        return validate_data(result.structured, json_schema)
    return parse_structured(result.text, json_schema)


# --------------------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------------------


def complete(
    prompt_name: str,
    variables: dict[str, Any],
    json_schema: type[BaseModel] | None = None,
    *,
    config: AppConfig | None = None,
) -> str | BaseModel:
    """Render ``config/llm_prompts/<prompt_name>.md`` with ``variables`` and call the provider.

    With ``json_schema`` the schema is included in the request, the response is parsed and
    validated, and one retry carrying the validation error is attempted before failing.
    """
    cfg = config or load_config()
    llm_cfg = cfg.user_facts.llm
    if (
        llm_cfg.provider == LLMProvider.claude_code
        and RESUME_VARIABLE in variables
        and not llm_cfg.allow_resume_upload
    ):
        raise ResumeUploadBlocked(
            "This command would send resume text to a hosted Claude model. Either run it with "
            "user_facts.llm.provider set to ollama, or explicitly set "
            "user_facts.llm.allow_resume_upload: true."
        )

    prompt = build_prompt(prompt_name, variables, json_schema, cfg.root)
    try:
        first = _call_provider(prompt_name, prompt, cfg, json_schema)
    except LLMError:
        log.info("llm call prompt=%s status=failure", prompt_name)
        raise

    if json_schema is None:
        return first.text

    try:
        return _result_to_model(first, json_schema)
    except ValueError as first_error:
        retry_prompt = (
            prompt
            + "\n\nYour previous response was rejected: "
            + str(first_error)
            + "\nRespond again with a single JSON object that matches the schema exactly."
        )
        try:
            second = _call_provider(prompt_name, retry_prompt, cfg, json_schema)
            return _result_to_model(second, json_schema)
        except (ValueError, LLMError) as second_error:
            log.info("llm call prompt=%s status=failure", prompt_name)
            raise LLMResponseError(
                f"{prompt_name}: model output failed validation twice. "
                f"First: {first_error}. Second: {second_error}"
            ) from second_error
