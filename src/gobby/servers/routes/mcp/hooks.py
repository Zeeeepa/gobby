"""
Hooks management routes for Gobby HTTP server.

Provides hook execution endpoint for CLI adapters.
Extracted from base.py as part of Strangler Fig decomposition.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request

from gobby.utils.metrics import get_metrics_collector

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


def create_hooks_router(server: "HTTPServer") -> APIRouter:
    """
    Create hooks router with endpoints bound to server instance.

    Args:
        server: HTTPServer instance for accessing state and dependencies

    Returns:
        Configured APIRouter with hooks endpoints
    """
    router = APIRouter(prefix="/hooks", tags=["hooks"])
    metrics = get_metrics_collector()

    @router.post("/execute")
    async def execute_hook(request: Request) -> dict[str, Any]:
        """
        Execute CLI hook via adapter pattern.

        Request body:
            {
                "hook_type": "session-start",
                "input_data": {...},
                "source": "claude"
            }

        Returns:
            Hook execution result with status
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")
        metrics.inc_counter("hooks_total")

        try:
            # Parse request
            payload = await request.json()
            hook_type = payload.get("hook_type")
            source = payload.get("source")

            if not hook_type:
                raise HTTPException(status_code=400, detail="hook_type required")

            if not source:
                raise HTTPException(status_code=400, detail="source required")

            # Get HookManager from app.state
            if not hasattr(request.app.state, "hook_manager"):
                raise HTTPException(status_code=503, detail="HookManager not initialized")

            hook_manager = request.app.state.hook_manager

            # Select adapter based on source
            from gobby.adapters.base import BaseAdapter
            from gobby.adapters.claude_code import ClaudeCodeAdapter
            from gobby.adapters.codex import CodexNotifyAdapter
            from gobby.adapters.gemini import GeminiAdapter

            if source == "claude":
                adapter: BaseAdapter = ClaudeCodeAdapter(hook_manager=hook_manager)
            elif source == "antigravity":
                adapter = ClaudeCodeAdapter(hook_manager=hook_manager)  # Same format as Claude
            elif source == "gemini":
                adapter = GeminiAdapter(hook_manager=hook_manager)
            elif source == "codex":
                adapter = CodexNotifyAdapter(hook_manager=hook_manager)
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported source: {source}. Supported: claude, antigravity, gemini, codex",
                )

            # Execute hook via adapter
            try:
                result = await asyncio.to_thread(adapter.handle_native, payload, hook_manager)

                response_time_ms = (time.perf_counter() - start_time) * 1000
                metrics.inc_counter("hooks_succeeded_total")

                logger.debug(
                    f"Hook executed: {hook_type}",
                    extra={
                        "hook_type": hook_type,
                        "continue": result.get("continue"),
                        "response_time_ms": response_time_ms,
                    },
                )

                return result

            except ValueError as e:
                metrics.inc_counter("hooks_failed_total")
                logger.warning(
                    f"Invalid hook request: {hook_type}",
                    extra={"hook_type": hook_type, "error": str(e)},
                )
                raise HTTPException(status_code=400, detail=str(e)) from e

            except Exception as e:
                metrics.inc_counter("hooks_failed_total")
                logger.error(
                    f"Hook execution failed: {hook_type}",
                    exc_info=True,
                    extra={"hook_type": hook_type},
                )
                raise HTTPException(status_code=500, detail=str(e)) from e

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("hooks_failed_total")
            logger.error("Hook endpoint error", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e)) from e

    return router
