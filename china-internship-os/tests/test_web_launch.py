"""`ios ui` starts the local server on 127.0.0.1 only."""

from __future__ import annotations

from typer.testing import CliRunner

from internship_os.cli import app


def test_ui_command_serves_on_localhost(project_root, engine, monkeypatch):
    import uvicorn

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda target, **kwargs: calls.append((target, kwargs)))
    result = CliRunner().invoke(app, ["ui", "--port", "8799"])
    assert result.exit_code == 0, result.output
    (target, kwargs), = calls
    assert target == "internship_os.web.app:app"
    assert kwargs["host"] == "127.0.0.1" and kwargs["port"] == 8799
    assert "http://127.0.0.1:8799" in result.output


def test_ui_command_creates_missing_tables(project_root, monkeypatch):
    import uvicorn
    from sqlalchemy import inspect

    from internship_os.db import get_engine

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    result = CliRunner().invoke(app, ["ui"])
    assert result.exit_code == 0, result.output
    assert "jobs" in inspect(get_engine()).get_table_names()


def test_streamlit_dashboard_is_retired():
    import tomllib
    from pathlib import Path

    project = Path(__file__).resolve().parents[1]
    assert not (project / "app.py").exists()
    deps = " ".join(tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"])
    assert "streamlit" not in deps.casefold()
    for path in (project / "internship_os").rglob("*.py"):
        assert "streamlit" not in path.read_text(encoding="utf-8").casefold(), path.name
