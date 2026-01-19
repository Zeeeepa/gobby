"""
Session routes for Gobby HTTP server.

Provides session registration, listing, lookup, and update endpoints.
"""

import logging
import time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query, Request

from gobby.servers.models import SessionRegisterRequest
from gobby.utils.metrics import get_metrics_collector

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


def create_sessions_router(server: "HTTPServer") -> APIRouter:
    """
    Create sessions router with endpoints bound to server instance.

    Args:
        server: HTTPServer instance for accessing state and dependencies

    Returns:
        Configured APIRouter with session endpoints
    """
    router = APIRouter(prefix="/sessions", tags=["sessions"])
    metrics = get_metrics_collector()

    @router.post("/register")
    async def register_session(request_data: SessionRegisterRequest) -> dict[str, Any]:
        """
        Register session metadata in local storage.

        Args:
            request_data: Session registration parameters

        Returns:
            Registration confirmation with session ID
        """
        metrics.inc_counter("http_requests_total")
        metrics.inc_counter("session_registrations_total")

        try:
            if server.session_manager is None:
                raise HTTPException(status_code=503, detail="Session manager not available")

            # Get machine_id from request or generate
            machine_id = request_data.machine_id
            if not machine_id:
                from gobby.utils.machine_id import get_machine_id

                machine_id = get_machine_id()

            if not machine_id:
                # Should unlikely happen if get_machine_id works, but type safe
                machine_id = "unknown-machine"

            # Extract git branch if project path exists but git_branch not provided
            git_branch = request_data.git_branch
            if request_data.project_path and not git_branch:
                from gobby.utils.git import get_git_metadata

                git_metadata = get_git_metadata(request_data.project_path)
                if git_metadata.get("git_branch"):
                    git_branch = git_metadata.get("git_branch")

            # Resolve project_id from cwd if not provided
            project_id = server._resolve_project_id(request_data.project_id, request_data.cwd)

            # Register session in local storage
            session = server.session_manager.register(
                external_id=request_data.external_id,
                machine_id=machine_id,
                source=request_data.source or "Claude Code",
                project_id=project_id,
                jsonl_path=request_data.jsonl_path,
                title=request_data.title,
                git_branch=git_branch,
                parent_session_id=request_data.parent_session_id,
            )

            return {
                "status": "registered",
                "external_id": request_data.external_id,
                "id": session.id,
                "machine_id": machine_id,
            }

        except HTTPException:
            metrics.inc_counter("http_requests_errors_total")
            raise

        except ValueError as e:
            # ValueError from _resolve_project_id when project not initialized
            metrics.inc_counter("http_requests_errors_total")
            raise HTTPException(status_code=400, detail=str(e)) from e

        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Error registering session: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail="Internal server error while registering session"
            ) from e

    @router.get("")
    async def list_sessions(
        project_id: str | None = None,
        status: str | None = None,
        source: str | None = None,
        limit: int = Query(100, ge=1, le=1000),
    ) -> dict[str, Any]:
        """
        List sessions with optional filtering and message counts.

        Args:
            project_id: Filter by project ID
            status: Filter by status (active, archived, etc)
            source: Filter by source (Claude Code, Gemini, etc)
            limit: Max results (default 100)

        Returns:
            List of session objects with message counts
        """
        metrics.inc_counter("http_requests_total")
        start_time = time.perf_counter()

        try:
            if server.session_manager is None:
                raise HTTPException(status_code=503, detail="Session manager not available")

            sessions = server.session_manager.list(
                project_id=project_id,
                status=status,
                source=source,
                limit=limit,
            )

            # Fetch message counts if message manager is available
            message_counts = {}
            if server.message_manager:
                try:
                    message_counts = await server.message_manager.get_all_counts()
                except Exception as e:
                    logger.warning(f"Failed to fetch message counts: {e}")

            # Enrich sessions with counts
            session_list = []
            for session in sessions:
                session_data = session.to_dict()
                session_data["message_count"] = message_counts.get(session.id, 0)
                session_list.append(session_data)

            response_time_ms = (time.perf_counter() - start_time) * 1000

            return {
                "sessions": session_list,
                "count": len(session_list),
                "response_time_ms": response_time_ms,
            }

        except HTTPException:
            metrics.inc_counter("http_requests_errors_total")
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Error listing sessions: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/{session_id}")
    async def sessions_get(session_id: str) -> dict[str, Any]:
        """
        Get session by ID from local storage.

        Args:
            session_id: Session ID (UUID)

        Returns:
            Session data
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            if server.session_manager is None:
                raise HTTPException(status_code=503, detail="Session manager not available")

            session = server.session_manager.get(session_id)

            if session is None:
                raise HTTPException(status_code=404, detail="Session not found")

            response_time_ms = (time.perf_counter() - start_time) * 1000

            return {
                "status": "success",
                "session": session.to_dict(),
                "response_time_ms": response_time_ms,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Sessions get error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/{session_id}/messages")
    async def sessions_get_messages(
        session_id: str,
        limit: int = 100,
        offset: int = 0,
        role: str | None = None,
    ) -> dict[str, Any]:
        """
        Get messages for a session.

        Args:
            session_id: Session ID
            limit: Max messages to return (default 100)
            offset: Pagination offset
            role: Filter by role (user, assistant, tool)

        Returns:
            List of messages and total count key
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            if server.message_manager is None:
                raise HTTPException(status_code=503, detail="Message manager not available")

            messages = await server.message_manager.get_messages(
                session_id=session_id, limit=limit, offset=offset, role=role
            )

            count = await server.message_manager.count_messages(session_id)
            response_time_ms = (time.perf_counter() - start_time) * 1000

            return {
                "status": "success",
                "messages": messages,
                "total_count": count,
                "response_time_ms": response_time_ms,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Get messages error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/find_current")
    async def find_current_session(request: Request) -> dict[str, Any]:
        """
        Find current active session by composite key.

        Uses composite key: external_id, machine_id, source, project_id
        Accepts either project_id directly or cwd (which is resolved to project_id).
        """
        try:
            if server.session_manager is None:
                raise HTTPException(status_code=503, detail="Session manager not available")

            body = await request.json()
            external_id = body.get("external_id")
            machine_id = body.get("machine_id")
            source = body.get("source")
            project_id = body.get("project_id")
            cwd = body.get("cwd")

            if not external_id or not machine_id or not source:
                raise HTTPException(
                    status_code=400,
                    detail="Required fields: external_id, machine_id, source",
                )

            # Resolve project_id from cwd if not provided
            if not project_id and cwd:
                project_id = server._resolve_project_id(None, cwd)

            if not project_id:
                raise HTTPException(
                    status_code=400,
                    detail="Required: project_id or cwd (to resolve project)",
                )

            session = server.session_manager.find_by_external_id(
                external_id, machine_id, project_id, source
            )

            if session is None:
                return {"session": None}

            return {"session": session.to_dict()}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Find current session error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/find_parent")
    async def find_parent_session(request: Request) -> dict[str, Any]:
        """
        Find parent session for handoff.

        Looks for most recent session in same project with handoff_ready status.
        Accepts either project_id directly or cwd (which is resolved to project_id).
        """
        try:
            if server.session_manager is None:
                raise HTTPException(status_code=503, detail="Session manager not available")

            body = await request.json()
            machine_id = body.get("machine_id")
            source = body.get("source")
            project_id = body.get("project_id")
            cwd = body.get("cwd")

            if not source:
                raise HTTPException(status_code=400, detail="Required field: source")

            if not machine_id:
                from gobby.utils.machine_id import get_machine_id

                machine_id = get_machine_id()

            if not machine_id:
                machine_id = "unknown-machine"

            # Resolve project_id from cwd if not provided
            if not project_id:
                if not cwd:
                    raise HTTPException(
                        status_code=400,
                        detail="Required field: project_id or cwd",
                    )
                project_id = server._resolve_project_id(None, cwd)

            session = server.session_manager.find_parent(
                machine_id=machine_id,
                source=source,
                project_id=project_id,
            )

            if session is None:
                return {"session": None}

            return {"session": session.to_dict()}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Find parent session error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/update_status")
    async def update_session_status(request: Request) -> dict[str, Any]:
        """
        Update session status.
        """
        try:
            if server.session_manager is None:
                raise HTTPException(status_code=503, detail="Session manager not available")

            body = await request.json()
            session_id = body.get("session_id")
            status = body.get("status")

            if not session_id or not status:
                raise HTTPException(status_code=400, detail="Required fields: session_id, status")

            session = server.session_manager.update_status(session_id, status)

            if session is None:
                raise HTTPException(status_code=404, detail="Session not found")

            return {"session": session.to_dict()}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Update session status error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/update_summary")
    async def update_session_summary(request: Request) -> dict[str, Any]:
        """
        Update session summary path.
        """
        try:
            if server.session_manager is None:
                raise HTTPException(status_code=503, detail="Session manager not available")

            body = await request.json()
            session_id = body.get("session_id")
            summary_path = body.get("summary_path")

            if not session_id or not summary_path:
                raise HTTPException(
                    status_code=400, detail="Required fields: session_id, summary_path"
                )

            session = server.session_manager.update_summary(session_id, summary_path)

            if session is None:
                raise HTTPException(status_code=404, detail="Session not found")

            return {"session": session.to_dict()}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Update session summary error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/{session_id}/stop")
    async def stop_session(session_id: str, request: Request) -> dict[str, Any]:
        """
        Signal a session to stop gracefully.

        Allows external systems to request a graceful stop of an autonomous session.
        The session will check for this signal and stop at the next opportunity.

        Args:
            session_id: Session ID to stop
            request: Request body with optional reason and source

        Returns:
            Stop signal confirmation
        """
        metrics.inc_counter("http_requests_total")

        try:
            # Get HookManager from app state
            if not hasattr(request.app.state, "hook_manager"):
                raise HTTPException(status_code=503, detail="Hook manager not available")

            hook_manager = request.app.state.hook_manager
            if not hasattr(hook_manager, "_stop_registry") or not hook_manager._stop_registry:
                raise HTTPException(status_code=503, detail="Stop registry not available")

            stop_registry = hook_manager._stop_registry

            # Parse optional body parameters
            body: dict[str, Any] = {}
            try:
                body = await request.json()
            except Exception:
                pass  # nosec B110 - empty body is fine

            reason = body.get("reason", "External stop request")
            source = body.get("source", "http_api")

            # Signal the stop
            signal = stop_registry.signal_stop(
                session_id=session_id,
                reason=reason,
                source=source,
            )

            logger.info(f"Stop signal sent to session {session_id}: {reason}")

            return {
                "status": "stop_signaled",
                "session_id": session_id,
                "signal_id": signal.signal_id,
                "reason": signal.reason,
                "source": signal.source,
                "signaled_at": signal.signaled_at.isoformat(),
            }

        except HTTPException:
            metrics.inc_counter("http_requests_errors_total")
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Error sending stop signal: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/{session_id}/stop")
    async def get_stop_signal(session_id: str, request: Request) -> dict[str, Any]:
        """
        Check if a session has a pending stop signal.

        Args:
            session_id: Session ID to check

        Returns:
            Stop signal status and details if present
        """
        metrics.inc_counter("http_requests_total")

        try:
            # Get HookManager from app state
            if not hasattr(request.app.state, "hook_manager"):
                raise HTTPException(status_code=503, detail="Hook manager not available")

            hook_manager = request.app.state.hook_manager
            if not hasattr(hook_manager, "_stop_registry") or not hook_manager._stop_registry:
                raise HTTPException(status_code=503, detail="Stop registry not available")

            stop_registry = hook_manager._stop_registry

            signal = stop_registry.get_signal(session_id)

            if signal is None:
                return {
                    "has_signal": False,
                    "session_id": session_id,
                }

            return {
                "has_signal": True,
                "session_id": session_id,
                "signal_id": signal.signal_id,
                "reason": signal.reason,
                "source": signal.source,
                "signaled_at": signal.signaled_at.isoformat(),
                "acknowledged": signal.acknowledged,
                "acknowledged_at": (
                    signal.acknowledged_at.isoformat() if signal.acknowledged_at else None
                ),
            }

        except HTTPException:
            metrics.inc_counter("http_requests_errors_total")
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Error checking stop signal: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.delete("/{session_id}/stop")
    async def clear_stop_signal(session_id: str, request: Request) -> dict[str, Any]:
        """
        Clear a stop signal for a session.

        Useful for resetting a session's stop state after handling.

        Args:
            session_id: Session ID to clear signal for

        Returns:
            Confirmation of signal cleared
        """
        metrics.inc_counter("http_requests_total")

        try:
            # Get HookManager from app state
            if not hasattr(request.app.state, "hook_manager"):
                raise HTTPException(status_code=503, detail="Hook manager not available")

            hook_manager = request.app.state.hook_manager
            if not hasattr(hook_manager, "_stop_registry") or not hook_manager._stop_registry:
                raise HTTPException(status_code=503, detail="Stop registry not available")

            stop_registry = hook_manager._stop_registry

            cleared = stop_registry.clear(session_id)

            return {
                "status": "cleared" if cleared else "no_signal",
                "session_id": session_id,
                "was_present": cleared,
            }

        except HTTPException:
            metrics.inc_counter("http_requests_errors_total")
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Error clearing stop signal: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    return router
