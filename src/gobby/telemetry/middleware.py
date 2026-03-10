"""
OpenTelemetry middleware for FastAPI.
Automatically tracks HTTP request counts, durations, and errors.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from gobby.telemetry.instruments import get_telemetry_metrics

if TYPE_CHECKING:
    from starlette.types import ASGIApp


class TelemetryMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for automated metrics and tracing.

    Replaces manual http_requests_total, http_request_duration_seconds,
    and http_requests_errors_total tracking across all routes.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.metrics = get_telemetry_metrics()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start_time = time.perf_counter()

        # Extract attributes for labeling
        method = request.method
        path = request.url.path

        # Try to get route path from scope (FastAPI sets this)
        route_path = path
        if "route" in request.scope:
            route_path = request.scope["route"].path

        attributes = {
            "http.method": method,
            "http.target": route_path,
        }

        # Add project/session context if available in headers/query
        session_id = request.headers.get("X-Session-ID") or request.query_params.get("session_id")
        if session_id:
            attributes["session_id"] = str(session_id)

        project_id = request.headers.get("X-Project-ID") or request.query_params.get("project_id")
        if project_id:
            attributes["project_id"] = str(project_id)

        try:
            response = await call_next(request)

            # Record metrics
            duration = time.perf_counter() - start_time
            status_code = response.status_code
            attributes["http.status_code"] = str(status_code)

            self.metrics.inc_counter("http_requests_total", attributes=attributes)
            self.metrics.observe_histogram(
                "http_request_duration_seconds", duration, attributes=attributes
            )

            if status_code >= 400:
                self.metrics.inc_counter("http_requests_errors_total", attributes=attributes)

            return response

        except Exception:
            # Record error
            duration = time.perf_counter() - start_time
            attributes["http.status_code"] = "500"

            self.metrics.inc_counter("http_requests_total", attributes=attributes)
            self.metrics.observe_histogram(
                "http_request_duration_seconds", duration, attributes=attributes
            )
            self.metrics.inc_counter("http_requests_errors_total", attributes=attributes)

            raise
