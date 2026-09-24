"""The TypeSafe key stays on the user's machine: never in a tracked or committable file."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
KEY_SHAPE = re.compile(r"apikey_[0-9a-f]{16,}")
# Captured at import: the autouse LLM guard in conftest.py replaces subprocess.run during tests.
_RUN = subprocess.run

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not (PROJECT.parent / ".git").exists() and not (PROJECT / ".git").exists(),
    reason="needs a git checkout",
)


def _git(*args: str) -> subprocess.CompletedProcess:
    return _RUN(["git", *args], cwd=PROJECT, capture_output=True)


def test_no_tracked_or_committable_file_contains_an_api_key():
    listed = _git("ls-files", "-z", "--cached", "--others", "--exclude-standard").stdout.split(b"\0")
    for name in filter(None, listed):
        path = PROJECT / name.decode()
        if path.is_file():
            assert not KEY_SHAPE.search(path.read_bytes().decode("utf-8", "ignore")), f"{name.decode()} contains an API key"


def test_env_file_is_ignored_and_untracked():
    assert _git("check-ignore", "-q", ".env").returncode == 0
    assert _git("ls-files", "--error-unmatch", ".env").returncode != 0
