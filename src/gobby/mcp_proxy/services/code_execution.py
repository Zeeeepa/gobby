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
            return {"success": False, "error": "Code execution not available - LLM service not configured"}

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

        This generates Python code to perform the specified operation on the dataset,
        then executes it using the configured LLM provider's code execution sandbox.

        Args:
            data: Dataset to process (will be serialized to JSON for the code)
            operation: Operation to perform (e.g., "transform", "filter", "aggregate", "analyze")
            parameters: Optional parameters for the operation
            timeout: Execution timeout in seconds

        Returns:
            Result dict with processed data or error
        """
        if not self._llm_service or not self._config:
            return {"success": False, "error": "Code execution not available - LLM service not configured"}

        if not self._config.code_execution.enabled:
            return {"success": False, "error": "Code execution is disabled in configuration"}

        try:
            # Serialize data for embedding in code
            # Limit preview size to avoid token overflow
            max_preview = getattr(self._config.code_execution, "max_dataset_preview", 3)
            if isinstance(data, list):
                preview = data[:max_preview] if len(data) > max_preview else data
                data_preview = json.dumps(preview, indent=2, default=str)
                if len(data) > max_preview:
                    data_preview += f"\n# ... and {len(data) - max_preview} more items"
            else:
                data_preview = json.dumps(data, indent=2, default=str)

            # Generate code based on operation
            params_str = json.dumps(parameters or {}, indent=2)
            code = self._generate_processing_code(operation, data_preview, params_str)

            # Build context for execution
            context = f"Processing dataset with operation '{operation}'"
            if parameters:
                context += f" and parameters: {params_str}"

            # Execute the generated code
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

    def _generate_processing_code(self, operation: str, data_preview: str, params_str: str) -> str:
        """Generate Python code for dataset processing.

        Args:
            operation: The operation to perform
            data_preview: JSON preview of the data
            params_str: JSON string of parameters

        Returns:
            Generated Python code
        """
        # Map operations to code templates
        operation_lower = operation.lower()

        if operation_lower == "transform":
            return f'''
import json

data = {data_preview}
params = {params_str}

# Apply transformation
def transform(item):
    # Apply parameter-based transformations
    result = item.copy() if isinstance(item, dict) else item
    for key, value in params.items():
        if isinstance(result, dict) and key in result:
            result[key] = value(result[key]) if callable(value) else value
    return result

if isinstance(data, list):
    result = [transform(item) for item in data]
else:
    result = transform(data)

print(json.dumps(result, indent=2, default=str))
'''
        elif operation_lower == "filter":
            return f'''
import json

data = {data_preview}
params = {params_str}

# Apply filter based on parameters
def matches(item):
    for key, value in params.items():
        if isinstance(item, dict) and item.get(key) != value:
            return False
    return True

if isinstance(data, list):
    result = [item for item in data if matches(item)]
else:
    result = data if matches(data) else None

print(json.dumps(result, indent=2, default=str))
'''
        elif operation_lower == "aggregate":
            return f'''
import json
from collections import Counter

data = {data_preview}
params = {params_str}

# Perform aggregation
group_by = params.get("group_by")
agg_func = params.get("function", "count")

if isinstance(data, list) and group_by:
    groups = {{}}
    for item in data:
        key = item.get(group_by) if isinstance(item, dict) else str(item)
        if key not in groups:
            groups[key] = []
        groups[key].append(item)

    if agg_func == "count":
        result = {{k: len(v) for k, v in groups.items()}}
    elif agg_func == "sum" and "field" in params:
        field = params["field"]
        result = {{k: sum(i.get(field, 0) for i in v) for k, v in groups.items()}}
    else:
        result = {{k: len(v) for k, v in groups.items()}}
else:
    result = {{"count": len(data) if isinstance(data, list) else 1}}

print(json.dumps(result, indent=2, default=str))
'''
        elif operation_lower == "analyze":
            return f'''
import json
from collections import Counter

data = {data_preview}
params = {params_str}

# Analyze dataset
analysis = {{
    "type": type(data).__name__,
    "length": len(data) if hasattr(data, "__len__") else 1,
}}

if isinstance(data, list) and data:
    first = data[0]
    if isinstance(first, dict):
        analysis["fields"] = list(first.keys())
        analysis["sample_types"] = {{k: type(v).__name__ for k, v in first.items()}}

print(json.dumps(analysis, indent=2, default=str))
'''
        else:
            # Generic processing - let the LLM figure it out
            return f'''
import json

data = {data_preview}
params = {params_str}
operation = "{operation}"

# Process data based on operation
# The LLM will interpret and execute the appropriate logic
print(f"Processing {{len(data) if isinstance(data, list) else 1}} items with operation: {{operation}}")
print(json.dumps(data, indent=2, default=str))
'''
