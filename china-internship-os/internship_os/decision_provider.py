"""Jev decision provider: the only module that talks to TypeSafe.

Jev (TypeSafe System One) answers typed questions (Choice, Noul) about the pasted posting text.
Its answers are suggestions shown on the review page; no gate reads them. The API key lives only
on the user's machine: ``TYPESAFE_API_KEY`` in the environment, else in the project's gitignored
``.env``. It is passed to the client directly and never written into ``os.environ``.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from internship_os.config import AppConfig, ConfigError, ConfigProblem, config_dir

KEY_VAR = "TYPESAFE_API_KEY"
DECISIONS_FILE = "decisions.yaml"
ENV_FILE = ".env"
_ENV_LINE = re.compile(rf"^\s*(?:export\s+)?{KEY_VAR}\s*=\s*(.*)$")


class DecisionsConfig(BaseModel):
    """``config/decisions.yaml``. Without the file the provider is off."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["typesafe", "none"] = "none"
    model: str = "jev-1.13.0"
    timeout_seconds: float = Field(default=8.0, gt=0)
    connect_timeout_seconds: float = Field(default=3.0, gt=0)
    noul_flag_p: float = Field(default=0.7, ge=0, le=1)
    choice_min_confidence: float = Field(default=0.6, ge=0, le=1)


def load_decisions(root: Path | str) -> DecisionsConfig:
    path = config_dir(root) / DECISIONS_FILE
    if not path.exists():
        return DecisionsConfig()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return DecisionsConfig.model_validate(data)
    except yaml.YAMLError as exc:
        raise ConfigError([ConfigProblem(str(path), "", f"YAML parse error: {exc}")]) from exc
    except ValidationError as exc:
        raise ConfigError(
            [ConfigProblem(str(path), ".".join(str(p) for p in e["loc"]), e["msg"]) for e in exc.errors()]
        ) from exc


def _env_value(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        return raw[1:-1]
    return raw.split(" #", 1)[0].split("\t#", 1)[0].strip()  # an unquoted value may end in a comment


def read_api_key(root: Path | str) -> str | None:
    """``TYPESAFE_API_KEY`` from the environment, else from ``<root>/.env``. Never logged.

    In ``.env`` the last non-empty assignment wins, as with dotenv; an unreadable file means no key.
    """
    value = (os.environ.get(KEY_VAR) or "").strip()
    if value:
        return value
    path = Path(root) / ENV_FILE
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    found = None
    for line in text.splitlines():
        match = _ENV_LINE.match(line)
        if match and _env_value(match.group(1)):
            found = _env_value(match.group(1))
    return found


# --------------------------------------------------------------------------------------
# Answers
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    kind: str  # "choice" | "noul"
    value: Any  # the chosen label, or P(true) for a noul
    confidence: float | None  # None for a noul
    probabilities: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionBatch:
    model: str
    decisions: dict[str, Decision]


class DecisionProvider(Protocol):
    model: str

    def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> DecisionBatch: ...


class NullProvider:
    """No Jev. ``reason`` says why, for the review page and ``ios llm-check``."""

    model = "none"

    def __init__(self, reason: str):
        self.reason = reason

    def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> DecisionBatch:
        return DecisionBatch(self.model, {})


class FakeDecisionProvider:
    """Canned decisions for tests."""

    def __init__(self, canned: dict[str, Decision], model: str = "fake-0", raises: Exception | None = None):
        self.canned, self.model, self.raises = canned, model, raises
        self.calls: list[tuple[Any, list[str]]] = []

    def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> DecisionBatch:
        self.calls.append((state, list(questions)))
        if self.raises is not None:
            raise self.raises
        return DecisionBatch(self.model, {k: v for k, v in self.canned.items() if k in questions})


def _transport() -> Any:
    """The HTTP transport for the client; None means the SDK's own network transport.

    Tests replace this so no test can reach api.typesafe.ai.
    """
    return None


class TypeSafeProvider:
    """One short attempt per call: capture must never wait long on Jev."""

    def __init__(self, *, api_key: str, model: str, timeout: float, connect_timeout: float, transport: Any = None):
        import httpx2
        from typesafe_sdk import RetryPolicy, TypeSafeClient

        # At DEBUG the SDK logs full request and response bodies; keep posting text out of logs.
        sdk_logger = logging.getLogger("typesafe_sdk")
        if sdk_logger.getEffectiveLevel() < logging.INFO:
            sdk_logger.setLevel(logging.INFO)
        self.model = model
        self._client = TypeSafeClient(
            api_key=api_key,
            model=model,
            retry=RetryPolicy(max_retries=0, timeout=timeout + connect_timeout),
            timeout=httpx2.Timeout(timeout, connect=connect_timeout),
            transport=transport if transport is not None else _transport(),
            base_url="https://api.typesafe.ai",  # pinned: an environment override must not redirect the key
        )

    def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> DecisionBatch:
        response = self._client.system_one(state, questions)
        decisions: dict[str, Decision] = {}
        for key, answer in response.answers.items():
            if key not in questions or answer.type != questions[key].get("type"):
                continue  # an answer to no question, or of the wrong kind, is not an answer
            if answer.type == "noul":
                decisions[key] = Decision("noul", float(answer.noul), None, {})
            elif answer.type == "choice":
                probabilities = {str(k): float(v) for k, v in (answer.probabilities or {}).items()}
                decisions[key] = Decision("choice", answer.choice, float(answer.confidence), probabilities)
        return DecisionBatch(response.model or self.model, decisions)


def get_provider(config: AppConfig, *, force: bool = False) -> DecisionProvider:
    """TypeSafe when decisions.yaml says so (or ``force``) and a key is on this machine, else Null."""
    decisions = load_decisions(config.root)
    if decisions.provider != "typesafe" and not force:
        return NullProvider("provider: none in config/decisions.yaml")
    key = read_api_key(config.root)
    if not key:
        return NullProvider(f"no {KEY_VAR} in the environment or .env")
    return TypeSafeProvider(
        api_key=key,
        model=decisions.model,
        timeout=decisions.timeout_seconds,
        connect_timeout=decisions.connect_timeout_seconds,
    )


def ask_safely(provider: DecisionProvider, state: Any, questions: dict[str, dict[str, Any]]) -> tuple[DecisionBatch | None, str | None]:
    """``(batch, None)``, or ``(None, error class name)``: a Jev failure never stops the caller."""
    try:
        return provider.ask(state, questions), None
    except Exception as exc:  # noqa: BLE001 - network, API and SDK errors all mean "no suggestions"
        return None, type(exc).__name__
