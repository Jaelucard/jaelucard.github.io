"""The TypeSafe key stays on the user's machine: never in a file git could commit.

Failures name files only; they never print the key or the file contents.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from internship_os.decision_provider import read_api_key

PROJECT = Path(__file__).resolve().parents[1]
KEY_SHAPE = re.compile(r"apikey_[0-9A-Za-z_]{12,}")
# Captured at import: the autouse LLM guard in conftest.py replaces subprocess.run during tests.
_RUN = subprocess.run

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _git(*args: str, cwd: Path = PROJECT) -> subprocess.CompletedProcess:
    return _RUN(["git", *args], cwd=cwd, capture_output=True)


def _committable_files() -> list[tuple[str, Path]]:
    top = _git("rev-parse", "--show-toplevel")
    if top.returncode != 0:
        pytest.skip("not a git checkout")
    root = Path(top.stdout.decode().strip())
    listed = _git("ls-files", "-z", "--cached", "--others", "--exclude-standard", cwd=root).stdout.split(b"\0")
    return [(name.decode(), root / name.decode()) for name in listed if name and (root / name.decode()).is_file()]


def _files_containing(match) -> list[str]:
    hits = []
    for name, path in _committable_files():
        if match(path.read_bytes().decode("utf-8", "ignore")):
            hits.append(name)
    return hits


def test_no_committable_file_in_the_repo_contains_a_key_shaped_string():
    hits = _files_containing(lambda text: KEY_SHAPE.search(text) is not None)
    assert not hits, "API-key-shaped text in: " + ", ".join(hits)


def test_the_local_key_appears_in_no_committable_file():
    key = read_api_key(PROJECT)
    if not key:
        pytest.skip("no local TYPESAFE_API_KEY")
    hits = _files_containing(lambda text: key in text)
    assert not hits, "the local TYPESAFE_API_KEY appears in: " + ", ".join(hits)


def test_the_shape_matches_the_real_key_format():
    assert KEY_SHAPE.search("apikey_" + "ab12" * 10 + "_" + "cd34" * 16)


def test_env_files_are_ignored_and_untracked():
    for name in (".env", ".env.bak", ".env.local"):
        assert _git("check-ignore", "-q", "--no-index", name).returncode == 0, name
    assert _git("ls-files", "--error-unmatch", ".env").returncode != 0
