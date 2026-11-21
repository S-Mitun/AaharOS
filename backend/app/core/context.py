"""Per-request context: the correlation id that ties logs, audit rows and responses together."""

import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_HEADER = "X-Correlation-Id"

correlation_id: ContextVar[uuid.UUID | None] = ContextVar("correlation_id", default=None)


def current_correlation_id() -> uuid.UUID | None:
    return correlation_id.get()


def _parse(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Accept a client's X-Correlation-Id (if it is a UUID) or mint one; echo it on the response."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        cid = _parse(request.headers.get(CORRELATION_HEADER)) or uuid.uuid4()
        token = correlation_id.set(cid)
        try:
            response = await call_next(request)
        finally:
            correlation_id.reset(token)
        response.headers[CORRELATION_HEADER] = str(cid)
        return response
