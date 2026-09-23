"""Jinja2 templates and the page helper shared by the routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from internship_os.services.review import display

HERE = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=str(HERE / "templates"))
TEMPLATES.env.filters["show"] = lambda value: display(value) or "-"


def page(request: Request, name: str, *, cli: str, status_code: int = 200, **context: Any) -> Response:
    """Render ``name``. Every page names its CLI equivalent in the footer."""
    return TEMPLATES.TemplateResponse(request, name, {"cli": cli, **context}, status_code=status_code)
