"""Static safety: nothing in this tool submits, sends, posts or automates a browser."""

import re
import tomllib
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
MODULES = sorted((PROJECT / "internship_os").glob("*.py")) + [PROJECT / "app.py"]

FORBIDDEN_IMPORTS = ("smtplib", "selenium", "playwright", "requests", "webbrowser", "pyautogui", "imaplib", "email.mime")
FORBIDDEN_DEF = re.compile(r"^\s*def\s+(send|submit|apply_to|post_to|email|message_send|auto_apply)\w*\s*\(", re.MULTILINE)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_no_command_submits_or_sends_anything():
    for path in MODULES:
        src = _source(path)
        for name in FORBIDDEN_IMPORTS:
            assert not re.search(rf"^\s*(import|from)\s+{re.escape(name)}\b", src, re.MULTILINE), f"{path.name} imports {name}"
        assert not FORBIDDEN_DEF.search(src), f"{path.name} defines a send/submit-style function"
        assert "webdriver" not in src.casefold(), path.name

    # Network use: httpx.post only in the Ollama provider (llm.py); httpx.get only in capture.py.
    for path in MODULES:
        src = _source(path)
        if path.name != "llm.py":
            assert "httpx.post" not in src and ".post(" not in src, f"{path.name} performs a POST"
        if path.name != "capture.py":
            assert "httpx.get" not in src, f"{path.name} performs a GET"
    capture_src = _source(PROJECT / "internship_os" / "capture.py")
    assert capture_src.count("httpx.get(") == 1
    assert "follow_redirects=False" in capture_src and "MAX_REDIRECTS" in capture_src
    llm_src = _source(PROJECT / "internship_os" / "llm.py")
    assert llm_src.count("httpx.post(") == 1
    assert 'OLLAMA_URL = "http://localhost:11434/api/generate"' in llm_src
    assert "httpx.post(OLLAMA_URL" in llm_src

    # No browser automation or messaging dependencies declared.
    pyproject = tomllib.loads(_source(PROJECT / "pyproject.toml"))
    deps = " ".join(pyproject["project"]["dependencies"]).casefold()
    for name in ("selenium", "playwright", "smtplib", "celery", "redis", "alembic", "psycopg"):
        assert name not in deps


def test_llm_logging_never_includes_content():
    """Every log call in llm.py passes only prompt name, provider, model, token counts, status."""
    import ast

    tree = ast.parse(_source(PROJECT / "internship_os" / "llm.py"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name) and node.func.value.id == "log"
    ]
    assert calls, "llm.py should log its calls"
    allowed_names = {"prompt_name", "provider_name", "model"}
    for call in calls:
        fmt = call.args[0]
        assert isinstance(fmt, ast.Constant) and isinstance(fmt.value, str)
        assert "prompt=%s" in fmt.value and "status=" in fmt.value
        for arg in call.args[1:]:
            if isinstance(arg, ast.Name):
                assert arg.id in allowed_names, ast.dump(arg)
            elif isinstance(arg, ast.Attribute):
                assert arg.attr in ("input_tokens", "output_tokens"), ast.dump(arg)
            else:
                raise AssertionError(ast.dump(arg))
