"""The FastAPI application: routes, static files, error pages and request checks.

There is no login, so the server refuses what another website could forge: requests whose Host
is not this machine (DNS rebinding) and state-changing requests from another origin (a form on
some other page posting here). Pages cannot be framed, and FastAPI's interactive docs are off.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import PlainTextResponse, Response

from internship_os.config import ConfigError
from internship_os.web import routes
from internship_os.web.render import HERE, page

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}


def is_same_origin(request: Request) -> bool:
    """Origin must match the Host header; without Origin, Sec-Fetch-Site must not be cross-site.

    Requests carrying neither header (curl, the test client) are allowed: a browser always sends
    at least one of them on a cross-site POST.
    """
    origin = request.headers.get("origin")
    if origin is not None:
        parts = urlsplit(origin)
        return parts.scheme in ("http", "https") and parts.netloc == request.headers.get("host", "")
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return site in ("same-origin", "none")
    return True


def create_app() -> FastAPI:
    app = FastAPI(title="China Internship OS", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def same_origin_writes(request: Request, call_next) -> Response:
        if request.method not in SAFE_METHODS and not is_same_origin(request):
            response: Response = PlainTextResponse("Cross-site request refused.", status_code=403)
        else:
            response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    # Added last so it runs first: an unknown Host never reaches the routes.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    app.include_router(routes.router)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        return page(request, "error.html", cli="-", status_code=exc.status_code,
                    title=f"Error {exc.status_code}", message=str(exc.detail), details=None)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError) -> Response:
        details = "\n".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        return page(request, "error.html", cli="-", status_code=400,
                    title="Bad request", message="The request could not be read.", details=details)

    @app.exception_handler(ConfigError)
    async def config_error(request: Request, exc: ConfigError) -> Response:
        return page(request, "error.html", cli="ios init", status_code=500,
                    title="Configuration is invalid", message="Fix these files under config/ and reload.",
                    details=exc.format())

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> Response:
        return page(request, "error.html", cli="-", status_code=500,
                    title="Unexpected error", message=f"{type(exc).__name__}: {exc}", details=None)

    return app


app = create_app()
