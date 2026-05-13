"""Lightweight HTTP middlewares for the single API.

Kept intentionally minimal — heavy lifting (rate limits, IP allowlists) belongs
at the reverse proxy / load balancer layer (see design doc §7.3).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject requests whose ``Content-Length`` exceeds a configured limit.

    Honoured before any route dependency runs, so large uploads are truncated
    at the edge instead of buffering into memory. Requests without a
    ``Content-Length`` header (e.g. chunked uploads) are passed through — the
    per-endpoint upload handlers already enforce their own caps.
    """

    def __init__(self, app, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                size = int(cl)
            except ValueError:
                size = 0
            if size > self.max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"request body {size} bytes exceeds {self.max_bytes}-byte limit"
                        ),
                    },
                )
        return await call_next(request)
