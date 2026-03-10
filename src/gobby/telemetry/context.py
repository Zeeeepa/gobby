"""
Context propagation for distributed tracing.

Provides utilities to inject/extract trace context into/from environment
variables for subprocess propagation.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

if TYPE_CHECKING:
    from opentelemetry.context import Context


def inject_into_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """
    Inject current trace context into environment dictionary.

    Uses W3C traceparent format (via TraceContextTextMapPropagator).
    If env is None, a copy of os.environ is used.

    Returns:
        The environment dictionary with injected trace context.
    """
    if env is None:
        env = dict(os.environ)
    else:
        env = env.copy()

    # TraceContextTextMapPropagator injects "traceparent" and "tracestate"
    TraceContextTextMapPropagator().inject(env)

    return env


def extract_from_env(env: dict[str, str] | None = None) -> Context | None:
    """
    Extract trace context from environment dictionary.

    If env is None, os.environ is used.

    Returns:
        The extracted Context object, or None if no context found.
    """
    if env is None:
        env = dict(os.environ)

    # We'll explicitly use TraceContextTextMapPropagator for W3C traceparent
    context = TraceContextTextMapPropagator().extract(env)

    # Check if the extracted context has a valid span
    span_context = trace.get_current_span(context).get_span_context()
    if not span_context.is_valid:
        return None

    return context


def get_trace_id() -> str | None:
    """
    Get the current active trace ID as a 32-character hex string.

    Returns None if no trace is active.
    """
    span = trace.get_current_span()
    span_context = span.get_span_context()
    if not span_context.is_valid:
        return None

    from opentelemetry.trace import format_trace_id

    return format_trace_id(span_context.trace_id)


def set_trace_context(trace_id: str, span_id: str) -> Context:
    """
    Create a new context with the given trace_id and span_id.

    Note: This returns a context object. To use it, use:
    with opentelemetry.context.attach(ctx): ...
    """
    # Create a span context from trace_id and span_id
    # trace_id and span_id are expected to be hex strings
    span_context = trace.SpanContext(
        trace_id=int(trace_id, 16),
        span_id=int(span_id, 16),
        is_remote=True,
        trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED),
    )

    # Create a non-recording span from this context
    span = trace.NonRecordingSpan(span_context)

    # Inject it into a new context
    return trace.set_span_in_context(span)
