"""MP17 hardening: security headers, a same-origin check on writes (CSRF), and one JSON log line per request.

- Headers on every response: no MIME sniffing, no framing, a strict referrer, no browser features we do not use, and
  HSTS when cookies are secure (HTTPS). The built web app (served by the API in the hosted demo) also gets a Content
  Security Policy that allows only this origin's scripts.
- CSRF: the session cookies are SameSite (lax / strict); on top of that, a browser write (POST / PUT / PATCH / DELETE)
  whose Origin is neither this server nor an allowed origin is refused with 403. Requests without an Origin header
  (curl, server-to-server, the test client) pass: they carry no ambient browser credentials from another site.
- Logs: one JSON line per request (method, path, status, duration, correlation id), never the body or cookies.
"""

import json
import logging
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.context import current_correlation_id

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
WEB_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data:; connect-src 'self'; font-src 'self' data: https://fonts.gstatic.com; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
log = logging.getLogger("aaharos.request")


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


class HardeningMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, allowed_origins: list[str], secure: bool, connect_extra: str = "") -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.allowed = {_origin(o) for o in allowed_origins if o}
        self.secure = secure
        # the browser also talks to Supabase Auth when it is the sign-in server
        self.csp = WEB_CSP.replace("connect-src 'self'", f"connect-src 'self' {connect_extra}".rstrip())

    def _same_site(self, request: Request, origin: str) -> bool:
        if origin.lower() in self.allowed:
            return True
        proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
        return origin.lower() == f"{proto}://{host}".lower()

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        started = time.perf_counter()
        origin = request.headers.get("origin")
        if request.method in WRITE_METHODS and origin and origin != "null" and not self._same_site(request, origin):
            response: Response = JSONResponse(
                {
                    "error": {
                        "code": "cross_site_request",
                        "message": "this request came from another site",
                        "details": {},
                    }
                },
                status_code=403,
            )
        elif request.method in WRITE_METHODS and origin == "null":
            response = JSONResponse(
                {
                    "error": {
                        "code": "cross_site_request",
                        "message": "this request came from another site",
                        "details": {},
                    }
                },
                status_code=403,
            )
        else:
            response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()")
        if self.secure:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if not request.url.path.startswith("/api/") and h.get("content-type", "").startswith("text/html"):
            h.setdefault("Content-Security-Policy", self.csp)
        log.info(
            json.dumps(
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                    "correlation_id": str(current_correlation_id() or ""),
                }
            )
        )
        return response
