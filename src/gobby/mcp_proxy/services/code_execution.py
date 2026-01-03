"""Code execution service."""

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.config.app import DaemonConfig
    from gobby.llm.service import LLMService

logger = logging.getLogger("gobby.mcp.server")


class CodeExecutionService:
    """Service for executing code securely using LLM providers."""

    def __init__(
        self,
        llm_service: "LLMService | None" = None,
        config: "DaemonConfig | None" = None,
    ):
        self._llm_service = llm_service
        self._config = config

    async def execute_code(
        self, code: str, language: str = "python", context: str | None = None, timeout: int = 30
    ) -> dict[str, Any]:
        """Execute code in sandbox.

        Args:
            code: Code to execute
            language: Programming language (default: python)
            context: Optional context for the execution
            timeout: Execution timeout in seconds

        Returns:
            Result dict with success status and output or error
        """
        if not self._llm_service or not self._config:
            return {
                "success": False,
                "error": "Code execution not available - LLM service not configured",
            }

        if not self._config.code_execution.enabled:
            return {"success": False, "error": "Code execution is disabled in configuration"}

        try:
            # Get provider for code execution feature
            provider, model, prompt_template = self._llm_service.get_provider_for_feature(
                self._config.code_execution
            )

            # Check if provider supports code execution
            if not provider.supports_code_execution:
                return {
                    "success": False,
                    "error": f"Provider '{provider.provider_name}' does not support code execution",
                }

            # Execute code using the provider
            result = await provider.execute_code(
                code=code,
                language=language,
                context=context,
                timeout=timeout,
                prompt_template=prompt_template,
            )

            return result

        except Exception as e:
            logger.error(f"Code execution failed: {e}")
            return {"success": False, "error": str(e)}

    async def process_dataset(
        self, data: Any, operation: str, parameters: dict[str, Any] | None = None, timeout: int = 60
    ) -> dict[str, Any]:
        """Process large dataset using code execution.

        Uses the LLM to generate and execute appropriate Python code for the operation.

        Args:
            data: Dataset to process (will be serialized to JSON for the code)
            operation: Natural language description of the operation to perform
            parameters: Optional parameters for the operation
            timeout: Execution timeout in seconds

        Returns:
            Result dict with processed data or error
        """
        if not self._llm_service or not self._config:
            return {
                "success": False,
                "error": "Code execution not available - LLM service not configured",
            }

        if not self._config.code_execution.enabled:
            return {"success": False, "error": "Code execution is disabled in configuration"}

        try:
            # Serialize data - include full data for small datasets, preview for large
            max_preview = getattr(self._config.code_execution, "max_dataset_preview", 3)
            if isinstance(data, list):
                original_size = len(data)
                if original_size <= max_preview:
                    json.dumps(data, indent=2, default=str)
                else:
                    preview = data[:max_preview]
                    json.dumps(preview, indent=2, default=str)
            else:
                original_size = 1
                json.dumps(data, indent=2, default=str)

            params_str = f"\n\nParameters: {json.dumps(parameters, indent=2)}" if parameters else ""

            # Build code that includes the data and asks for the operation
            code = f"""# Dataset ({original_size} items total):
data = {json.dumps(data, default=str)}

# Operation to perform: {operation}{params_str}

# Write Python code to perform the operation and print the result:
"""
            # Build context for intelligent code generation
            context = f"""Process this dataset by performing: {operation}

The variable 'data' contains the full dataset with {original_size} items.
Write and execute Python code to perform the requested operation.
Return the final result by printing it.

Requirements:
- Use standard Python (no external libraries unless necessary)
- The result should be printed as the output
- Be efficient and handle edge cases"""

            # Execute - the LLM will generate and run the appropriate code
            result = await self.execute_code(
                code=code,
                language="python",
                context=context,
                timeout=timeout,
            )

            return result

        except Exception as e:
            logger.error(f"Dataset processing failed: {e}")
            return {"success": False, "error": str(e)}
