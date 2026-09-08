"""Configuration loading and validation.

All YAML under ``config/`` is loaded and validated here. Every CLI command validates the
configuration before doing work; validation problems are reported as ``file / key path /
problem`` triples via :class:`ConfigError` and the CLI exits non-zero.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from internship_os.schemas import (
    CitiesConfig,
    ProgrammeConstraints,
    SkillEvidenceSet,
    UserFacts,
)

CONFIG_DIRNAME = "config"
USER_FACTS_FILE = "user_facts.yaml"
USER_FACTS_EXAMPLE_FILE = "user_facts.example.yaml"
PROGRAMME_CONSTRAINTS_FILE = "programme_constraints.yaml"
SKILL_EVIDENCE_FILE = "skill_evidence.yaml"
CITIES_FILE = "cities.yaml"
PROMPTS_DIRNAME = "llm_prompts"

ROOT_ENV_VAR = "IOS_ROOT"


class ConfigProblem(NamedTuple):
    file: str
    path: str
    problem: str


class ConfigError(Exception):
    """One or more configuration problems. ``problems`` lists file, key path and message."""

    def __init__(self, problems: list[ConfigProblem]):
        self.problems = problems
        super().__init__(self.format())

    def format(self) -> str:
        lines = ["Configuration is invalid:"]
        for p in self.problems:
            lines.append(f"  file:    {p.file}")
            lines.append(f"  key:     {p.path or '(root)'}")
            lines.append(f"  problem: {p.problem}")
        return "\n".join(lines)


def project_root(root: Path | str | None = None) -> Path:
    """Directory holding ``config/`` and ``db.sqlite``.

    Resolution order: explicit argument, ``IOS_ROOT`` environment variable, current directory.
    """
    if root is not None:
        return Path(root).resolve()
    env = os.environ.get(ROOT_ENV_VAR)
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


def config_dir(root: Path | str | None = None) -> Path:
    return project_root(root) / CONFIG_DIRNAME


def prompts_dir(root: Path | str | None = None) -> Path:
    return config_dir(root) / PROMPTS_DIRNAME


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        raise ConfigError([ConfigProblem(str(path), "", "file not found")])
    try:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigError([ConfigProblem(str(path), "", f"YAML parse error: {exc}")]) from exc


T = TypeVar("T", bound=BaseModel)


def _validate(model: type[T], data: Any, path: Path) -> T:
    if data is None:
        raise ConfigError([ConfigProblem(str(path), "", "file is empty")])
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = [
            ConfigProblem(
                str(path),
                ".".join(str(part) for part in err["loc"]),
                err["msg"],
            )
            for err in exc.errors()
        ]
        raise ConfigError(problems) from exc


def ensure_user_facts(cfg_dir: Path) -> bool:
    """Create ``user_facts.yaml`` from the example when absent. Never overwrites.

    Returns True when a copy was made.
    """
    target = cfg_dir / USER_FACTS_FILE
    if target.exists():
        return False
    example = cfg_dir / USER_FACTS_EXAMPLE_FILE
    if not example.exists():
        raise ConfigError(
            [
                ConfigProblem(
                    str(target),
                    "",
                    f"file not found and {USER_FACTS_EXAMPLE_FILE} is also missing, so it "
                    "cannot be created",
                )
            ]
        )
    shutil.copyfile(example, target)
    return True


@dataclass(frozen=True)
class AppConfig:
    root: Path
    user_facts: UserFacts
    constraints: ProgrammeConstraints
    evidence: SkillEvidenceSet
    cities: CitiesConfig

    @property
    def config_dir(self) -> Path:
        return self.root / CONFIG_DIRNAME


def load_config(root: Path | str | None = None, *, notice_stream=None) -> AppConfig:
    """Load and validate every configuration file.

    If ``config/user_facts.yaml`` is absent it is copied from the example file, one concise
    notice is printed to ``notice_stream`` (default stderr), and loading continues.
    Raises :class:`ConfigError` listing every problem found in a file.
    """
    resolved_root = project_root(root)
    cfg_dir = resolved_root / CONFIG_DIRNAME
    if not cfg_dir.is_dir():
        raise ConfigError([ConfigProblem(str(cfg_dir), "", "config directory not found")])

    if ensure_user_facts(cfg_dir):
        stream = notice_stream if notice_stream is not None else sys.stderr
        print(
            f"Created {cfg_dir / USER_FACTS_FILE} from {USER_FACTS_EXAMPLE_FILE}; "
            "edit it with your own facts.",
            file=stream,
        )

    user_facts_path = cfg_dir / USER_FACTS_FILE
    constraints_path = cfg_dir / PROGRAMME_CONSTRAINTS_FILE
    evidence_path = cfg_dir / SKILL_EVIDENCE_FILE
    cities_path = cfg_dir / CITIES_FILE

    user_facts = _validate(UserFacts, _read_yaml(user_facts_path), user_facts_path)
    constraints = _validate(
        ProgrammeConstraints, _read_yaml(constraints_path), constraints_path
    )
    evidence = _validate(SkillEvidenceSet, _read_yaml(evidence_path), evidence_path)
    cities = _validate(CitiesConfig, _read_yaml(cities_path), cities_path)

    return AppConfig(
        root=resolved_root,
        user_facts=user_facts,
        constraints=constraints,
        evidence=evidence,
        cities=cities,
    )
