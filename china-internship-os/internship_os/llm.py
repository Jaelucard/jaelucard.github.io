"""LLM access. The only module that talks to an LLM provider.

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
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from collections.abc import Callable, Iterator

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from internship_os.config import AppConfig, load_config, prompts_dir
from internship_os.schemas import LLMProvider

log = logging.getLogger("internship_os.llm")

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL_ENV = "OLLAMA_MODEL"
ANTHROPIC_KEY_ENV = "ANTHROPIC_API_KEY"
MAX_OUTPUT_TOKENS = 16000
RESUME_VARIABLE = "resume_text"
HOSTED_MODEL_PREFIXES = ("claude", "anthropic/", "gpt-", "o1", "o3", "o4", "openai/", "gemini", "google/")


class LLMError(Exception):
    """Base class for LLM failures."""


class LLMConfigError(LLMError):
    """Provider or template configuration problem."""


class LLMResponseError(LLMError):
    """The model did not return valid structured output after one retry."""


class ResumeUploadBlocked(LLMError):
    """A resume would have been sent to a hosted API without explicit permission."""


@dataclass
class ProviderResult:
    text: str
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
# Providers
# --------------------------------------------------------------------------------------


def _anthropic_call(prompt: str, model: str, root: Path) -> ProviderResult:
    load_dotenv(root / ".env")
    api_key = os.environ.get(ANTHROPIC_KEY_ENV)
    if not api_key:
        raise LLMConfigError(
            f"{ANTHROPIC_KEY_ENV} is not set. Put it in .env (see .env.example) or switch "
            "user_facts.llm.provider to ollama."
        )
    import anthropic  # imported lazily so tests never need the SDK configured

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(getattr(block, "text", "") for block in response.content)
    if getattr(response, "stop_reason", None) == "max_tokens":
        raise LLMResponseError(
            f"the model reply was cut off at {MAX_OUTPUT_TOKENS} output tokens; shorten the input"
        )
    if getattr(response, "stop_reason", None) == "refusal":
        raise LLMResponseError("the model declined this request (stop_reason=refusal)")
    usage = getattr(response, "usage", None)
    return ProviderResult(
        text=text,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    )


def ollama_model_name(config: AppConfig) -> str:
    load_dotenv(config.root / ".env")
    env_model = os.environ.get(OLLAMA_MODEL_ENV)
    if env_model:
        return env_model
    configured = config.user_facts.llm.model
    # A hosted-API model name is not intended for Ollama.
    if configured.lower().startswith(HOSTED_MODEL_PREFIXES):
        raise LLMConfigError(
            f"{OLLAMA_MODEL_ENV} is not set and user_facts.llm.model ({configured}) is a hosted "
            "API model name. Set OLLAMA_MODEL in .env to the Ollama model to use."
        )
    return configured


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
    prompt_name: str, prompt: str, config: AppConfig, want_json: bool
) -> ProviderResult:
    provider = config.user_facts.llm.provider
    if _fake_provider is not None:
        result = ProviderResult(text=_fake_provider(prompt_name, prompt))
        model = "fake"
        provider_name = "fake"
    elif provider == LLMProvider.anthropic:
        model = config.user_facts.llm.model
        provider_name = "anthropic"
        result = _anthropic_call(prompt, model, config.root)
    elif provider == LLMProvider.ollama:
        model = ollama_model_name(config)
        provider_name = "ollama"
        result = _ollama_call(prompt, model, want_json)
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
    try:
        return json_schema.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            ".".join(str(p) for p in err["loc"]) + ": " + err["msg"] for err in exc.errors()
        )
        raise ValueError(f"response did not match the schema: {problems}") from exc


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
    if (
        cfg.user_facts.llm.provider == LLMProvider.anthropic
        and RESUME_VARIABLE in variables
        and not cfg.user_facts.llm.allow_resume_upload_to_api
    ):
        raise ResumeUploadBlocked(
            "This command would send resume text to the Anthropic API. Either run it with "
            "user_facts.llm.provider set to ollama, or explicitly set "
            "user_facts.llm.allow_resume_upload_to_api: true."
        )

    prompt = build_prompt(prompt_name, variables, json_schema, cfg.root)
    want_json = json_schema is not None
    try:
        first = _call_provider(prompt_name, prompt, cfg, want_json)
    except LLMError:
        log.info("llm call prompt=%s status=failure", prompt_name)
        raise

    if json_schema is None:
        return first.text

    try:
        return parse_structured(first.text, json_schema)
    except ValueError as first_error:
        retry_prompt = (
            prompt
            + "\n\nYour previous response was rejected: "
            + str(first_error)
            + "\nRespond again with a single JSON object that matches the schema exactly."
        )
        try:
            second = _call_provider(prompt_name, retry_prompt, cfg, want_json)
            return parse_structured(second.text, json_schema)
        except (ValueError, LLMError) as second_error:
            log.info("llm call prompt=%s status=failure", prompt_name)
            raise LLMResponseError(
                f"{prompt_name}: model output failed validation twice. "
                f"First: {first_error}. Second: {second_error}"
            ) from second_error
