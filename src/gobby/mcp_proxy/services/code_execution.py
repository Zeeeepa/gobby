"""Code execution service."""

import asyncio
import logging
from typing import Any

logger = logging.getLogger("gobby.mcp.server")


class CodeExecutionService:
    """Service for executing code securely."""

    def __init__(self, codex_client: Any | None = None):
        self._codex_client = codex_client

    async def execute_code(
        self, code: str, language: str = "python", context: str | None = None, timeout: int = 30
    ) -> dict[str, Any]:
        """Execute code in sandbox."""
        if not self._codex_client:
            return {"success": False, "error": "Code execution not available"}

        try:
            # Delegate to codex client
            result = await self._codex_client.execute(code, language, context, timeout)
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def process_dataset(
        self, data: Any, operation: str, parameters: dict[str, Any] | None = None, timeout: int = 60
    ) -> dict[str, Any]:
        """Process large dataset using code execution."""
        # Logic extracted from process_large_dataset
        return {"success": True, "result": "Stubbed for refactor"}
