"""Response transformer service for MCP tool responses.

Applies optional compression to large tool response payloads using LLMLingua.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.compression.compressor import TextCompressor

logger = logging.getLogger(__name__)

# Fields to consider for compression (common response field names)
COMPRESSIBLE_FIELDS = frozenset(
    {
        "output",
        "result",
        "content",
        "data",
        "description",
        "text",
        "body",
        "message",
        "summary",
        "details",
        "response",
        "markdown",
        "html",
        "code",
        "error_details",
        "traceback",
    }
)


class ResponseTransformerService:
    """
    Service for transforming MCP tool responses.

    Applies compression to large string fields in tool responses when
    a TextCompressor is configured and enabled.

    Example:
        compressor = TextCompressor(config)
        transformer = ResponseTransformerService(compressor)
        result = transformer.transform_response(tool_result)
    """

    def __init__(self, compressor: TextCompressor | None = None) -> None:
        """
        Initialize the response transformer.

        Args:
            compressor: Optional TextCompressor for response compression.
                       If None or disabled, responses pass through unchanged.
        """
        self._compressor = compressor

    @property
    def is_enabled(self) -> bool:
        """Check if response transformation is enabled."""
        if self._compressor is None:
            return False
        return self._compressor.config.enabled

    @property
    def min_content_length(self) -> int:
        """Get the minimum content length for compression."""
        if self._compressor is None:
            return 500
        return self._compressor.config.min_content_length

    def transform_response(
        self,
        response: Any,
        context_type: str = "context",
    ) -> Any:
        """
        Transform a tool response, applying compression where appropriate.

        Walks through dict/list structures and compresses large string values
        in known compressible fields. Preserves response structure and metadata.

        Args:
            response: Tool response (dict, list, str, or other)
            context_type: Compression context type (handoff, memory, context)

        Returns:
            Transformed response with compressed content
        """
        if not self.is_enabled:
            return response

        return self._transform(response, context_type)

    def _transform(self, value: Any, context_type: str) -> Any:
        """Recursively transform a value."""
        if isinstance(value, dict):
            return self._transform_dict(value, context_type)
        elif isinstance(value, list):
            return [self._transform(item, context_type) for item in value]
        elif isinstance(value, str):
            # Only compress strings that exceed threshold
            if len(value) >= self.min_content_length:
                return self._compress_string(value, context_type)
            return value
        else:
            # Pass through other types unchanged (int, float, bool, None, etc.)
            return value

    def _transform_dict(self, data: dict[str, Any], context_type: str) -> dict[str, Any]:
        """Transform a dictionary, compressing appropriate fields."""
        result = {}
        for key, value in data.items():
            # Check if this is a field we should compress
            key_lower = key.lower()
            is_compressible_field = key_lower in COMPRESSIBLE_FIELDS

            if is_compressible_field and isinstance(value, str):
                # Directly compress string values in known fields
                if len(value) >= self.min_content_length:
                    result[key] = self._compress_string(value, context_type)
                else:
                    result[key] = value
            else:
                # Recurse into nested structures
                result[key] = self._transform(value, context_type)

        return result

    def _compress_string(self, content: str, context_type: str) -> str:
        """Compress a string using the configured compressor."""
        if self._compressor is None:
            return content

        try:
            # Map context_type string to valid ContextType literal
            valid_types = {"handoff", "memory", "context"}
            effective_type = context_type if context_type in valid_types else "context"

            compressed = self._compressor.compress(content, context_type=effective_type)  # type: ignore
            if compressed != content:
                logger.debug(
                    f"Compressed response field: {len(content)} -> {len(compressed)} chars "
                    f"({len(compressed) / len(content):.1%})"
                )
            return compressed
        except Exception as e:
            logger.warning(f"Response compression failed: {e}")
            return content
