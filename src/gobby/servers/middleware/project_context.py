"""Project context middleware for Gobby HTTP server.

Sets the project_context ContextVar from X-Gobby-Project-Id and
X-Gobby-Session-Id request headers on every request. This ensures all
routes that call get_project_context() — including workflow variable
endpoints, hooks, and any future routes — have project context available
for #N session reference resolution.

Previously, only the hooks route set this ContextVar via a local helper.
Any other route that needed project context (e.g., /api/workflows/variables/set)
would silently get None, causing #N resolution failures.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class ProjectContextMiddleware(BaseHTTPMiddleware):
    """Set project context ContextVar from request headers.

    Reads X-Gobby-Session-Id and X-Gobby-Project-Id headers injected by
    the CLI hook dispatcher and stdio proxy. Resolves project context and
    sets the ContextVar before the request handler runs, then resets it
    after the response completes.

    Resolution priority:
    1. X-Gobby-Session-Id → look up session → get project from session
    2. X-Gobby-Project-Id → look up project in DB → set full context
    3. X-Gobby-Project-Id → set minimal context (id only) if DB lookup fails
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        token = self._set_context(request)
        try:
            return await call_next(request)
        finally:
            if token is not None:
                from gobby.utils.project_context import reset_project_context

                reset_project_context(token)

    def _set_context(self, request: Request) -> contextvars.Token[Any] | None:
        """Set project ContextVar from request headers.

        Returns a ContextVar token for reset, or None if no headers present.
        """
        from gobby.utils.project_context import set_project_context

        # Priority 1: resolve project from session
        session_id = request.headers.get("x-gobby-session-id")
        if session_id:
            try:
                from gobby.utils.project_context import set_project_context_from_session

                session_manager = getattr(request.app.state, "session_manager", None)
                if session_manager:
                    token = set_project_context_from_session(
                        session_id, session_manager, session_manager.db
                    )
                    if token is not None:
                        return token
            except Exception as e:
                logger.debug("Failed to set project context from session %s: %s", session_id, e)

        # Priority 2: resolve project from project_id header
        project_id = request.headers.get("x-gobby-project-id")
        if project_id:
            try:
                from gobby.storage.projects import LocalProjectManager

                session_manager = getattr(request.app.state, "session_manager", None)
                if session_manager:
                    pm = LocalProjectManager(session_manager.db)
                    project = pm.get(project_id)
                    if project:
                        return set_project_context(
                            {
                                "id": project.id,
                                "name": project.name,
                                "project_path": project.repo_path,
                            }
                        )
            except Exception as e:
                logger.debug("Failed to resolve project %s: %s", project_id, e)
            # Fallback: set minimal context with just the id
            return set_project_context({"id": project_id})

        return None
