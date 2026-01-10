"""
Code execution routes for Gobby HTTP server.

Provides code execution and dataset processing endpoints.
Extracted from base.py as part of Strangler Fig decomposition.
"""

import logging
import time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request

from gobby.mcp_proxy.services.code_execution import CodeExecutionService
from gobby.utils.metrics import get_metrics_collector

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)

# Limits for dataset processing
MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_DATASET_ITEMS = 10000
DEFAULT_MAX_PROCESS_TIMEOUT = 300  # 5 minutes


def create_code_router(server: "HTTPServer") -> APIRouter:
    """
    Create code execution router with endpoints bound to server instance.

    Args:
        server: HTTPServer instance for accessing state and dependencies

    Returns:
        Configured APIRouter with code execution endpoints
    """
    router = APIRouter(prefix="/code", tags=["code"])
    metrics = get_metrics_collector()

    @router.post("/execute")
    async def execute_code(request: Request) -> dict[str, Any]:
        """
        Execute code using LLM-powered code execution.

        Request body:
            {
                "code": "print('hello')",
                "language": "python",
                "context": "optional context",
                "timeout": 30
            }

        Returns:
            Execution result or error
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            body = await request.json()
            code = body.get("code")
            language = body.get("language", "python")
            context = body.get("context")
            timeout = body.get("timeout", 30)

            if not code:
                raise HTTPException(status_code=400, detail="Required field: code")

            code_service = CodeExecutionService(
                llm_service=server.llm_service, config=server.config
            )
            result = await code_service.execute_code(code, language, context, timeout)

            response_time_ms = (time.perf_counter() - start_time) * 1000
            result["response_time_ms"] = response_time_ms
            return result

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Code execution error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error") from e

    @router.post("/process-dataset")
    async def process_dataset(request: Request) -> dict[str, Any]:
        """
        Process large datasets using LLM-powered chunked processing.

        Request body:
            {
                "data": [...],
                "operation": "summarize",
                "parameters": {},
                "timeout": 60
            }

        Returns:
            Processed result or error
        """
        start_time = time.perf_counter()
        metrics.inc_counter("http_requests_total")

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        try:
            data = body.get("data")
            operation = body.get("operation")
            parameters = body.get("parameters")
            timeout = body.get("timeout", 60)

            # Validate required fields
            if data is None:
                raise HTTPException(status_code=400, detail="Required field: data")
            if not operation:
                raise HTTPException(status_code=400, detail="Required field: operation")

            # Validate data type and size
            if not isinstance(data, (list, dict)):
                raise HTTPException(status_code=400, detail="Field 'data' must be a list or dict")
            if isinstance(data, list) and len(data) > MAX_DATASET_ITEMS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Dataset exceeds maximum of {MAX_DATASET_ITEMS} items",
                )

            # Cap timeout to safe maximum
            max_timeout = getattr(server.config, "max_process_timeout", DEFAULT_MAX_PROCESS_TIMEOUT)
            safe_timeout = min(timeout, max_timeout)

            code_service = CodeExecutionService(
                llm_service=server.llm_service, config=server.config
            )
            result = await code_service.process_dataset(data, operation, parameters, safe_timeout)

            response_time_ms = (time.perf_counter() - start_time) * 1000
            result["response_time_ms"] = response_time_ms
            return result

        except HTTPException:
            raise
        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Dataset processing error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error") from e

    return router
