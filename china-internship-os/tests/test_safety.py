"""Static safety: nothing in this tool submits, sends, posts or automates a browser."""

import re
import tomllib
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
PACKAGE = PROJECT / "internship_os"
MODULES = sorted(PACKAGE.rglob("*.py"))
LLM_MODULE = PACKAGE / "llm.py"
CAPTURE_MODULE = PACKAGE / "capture.py"
WEB_PACKAGE = PACKAGE / "web"
# The web UI's own form handlers are POST routes; that decorator is the only allowed ".post(".
ROUTE_DECORATOR = re.compile(r"^@router\.post\(.*$", re.MULTILINE)

FORBIDDEN_IMPORTS = ("smtplib", "selenium", "playwright", "requests", "webbrowser", "pyautogui", "imaplib", "email.mime", "anthropic", "dotenv")
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
        if WEB_PACKAGE in path.parents:
            src = ROUTE_DECORATOR.sub("", src)
        if path != LLM_MODULE:
            assert "httpx.post" not in src and ".post(" not in src, f"{path.name} performs a POST"
        if path != CAPTURE_MODULE:
            assert "httpx.get" not in src, f"{path.name} performs a GET"
    capture_src = _source(PROJECT / "internship_os" / "capture.py")
    assert capture_src.count("httpx.get(") == 1
    assert "follow_redirects=False" in capture_src and "MAX_REDIRECTS" in capture_src
    llm_src = _source(PROJECT / "internship_os" / "llm.py")
    assert llm_src.count("httpx.post(") == 1
    # The only subprocess use is the Claude Code CLI in llm.py, as a plain completion with tools off.
    for path in MODULES:
        if path != LLM_MODULE:
            assert not re.search(r"^\s*(import|from)\s+subprocess\b", _source(path), re.MULTILINE), f"{path.name} uses subprocess"
    assert '"--tools", ""' in llm_src and '"--no-session-persistence"' in llm_src
    assert 'STRIPPED_ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")' in llm_src
    assert 'OLLAMA_URL = "http://localhost:11434/api/generate"' in llm_src
    assert "httpx.post(OLLAMA_URL" in llm_src

    # No browser automation or messaging dependencies declared.
    pyproject = tomllib.loads(_source(PROJECT / "pyproject.toml"))
    deps = " ".join(pyproject["project"]["dependencies"]).casefold()
    for name in ("selenium", "playwright", "smtplib", "celery", "redis", "alembic", "psycopg", "anthropic", "dotenv"):
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
    loggers = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "getLogger"]
    assert len(loggers) == 1, "llm.py must use exactly one logger so this test sees every log call"
    allowed_names = {"prompt_name", "provider_name", "model"}
    for call in calls:
        fmt = call.args[0]
        assert isinstance(fmt, ast.Constant) and isinstance(fmt.value, str)
        if call.func.attr == "warning":
            assert "rate limit" in fmt.value
            # Only the delay, the attempt counter and a slice of the CLI's own error line.
            for arg in call.args[1:]:
                if isinstance(arg, ast.Name):
                    assert arg.id in ("delay", "attempt"), ast.dump(arg)
                elif isinstance(arg, ast.BinOp):
                    assert isinstance(arg.left, ast.Name) and arg.left.id == "attempt", ast.dump(arg)
                elif isinstance(arg, ast.Subscript):
                    assert isinstance(arg.value, ast.Name) and arg.value.id == "message", ast.dump(arg)
                else:
                    raise AssertionError(ast.dump(arg))
            continue
        assert "prompt=%s" in fmt.value and "status=" in fmt.value
        for arg in call.args[1:]:
            if isinstance(arg, ast.Name):
                assert arg.id in allowed_names, ast.dump(arg)
            elif isinstance(arg, ast.Attribute):
                assert arg.attr in ("input_tokens", "output_tokens"), ast.dump(arg)
            else:
                raise AssertionError(ast.dump(arg))


def test_web_ui_is_local_and_script_free():
    """The web UI binds to this machine only and serves no JavaScript or third-party assets."""
    cli_src = _source(PACKAGE / "cli.py")
    assert 'host="127.0.0.1"' in cli_src
    for path in MODULES:
        assert "0.0.0.0" not in _source(path), f"{path.name} mentions 0.0.0.0"
    templates = sorted((WEB_PACKAGE / "templates").glob("*.html"))
    assert templates
    for path in templates + sorted((WEB_PACKAGE / "static").glob("*")):
        src = _source(path).casefold()
        assert "<script" not in src and "javascript:" not in src, f"{path.name} contains script"
        assert "http://" not in src and "https://" not in src, f"{path.name} loads a remote asset"
