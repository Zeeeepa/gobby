"""
Logging utilities for request tracking and structured logging.

DEPRECATED: This module is deprecated in favor of gobby.telemetry.logging.
Components here will be removed in Phase 7.
"""

import contextvars
import uuid

# Context variable for tracking request IDs across async operations
# DEPRECATED: Use opentelemetry.trace.get_current_span()
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return str(uuid.uuid4())


def get_request_id() -> str | None:
    """Get the current request ID from context."""
    return request_id_var.get()


def clear_request_id() -> None:
    """Clear the request ID from context."""
    request_id_var.set(None)
