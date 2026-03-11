"""
Tracing utilities for Gobby.

Provides @traced decorator and span helpers for OpenTelemetry integration.
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

if TYPE_CHECKING:
    from opentelemetry.trace import Span

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _is_tracing_enabled() -> bool:
    """Check if tracing is enabled in global config."""
    from gobby.app_context import get_app_context

    ctx = get_app_context()
    if ctx and hasattr(ctx, "config") and ctx.config:
        return getattr(ctx.config.telemetry, "traces_enabled", False)
    return False


def traced(
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
    capture_args: bool = False,
) -> Callable[[F], F]:
    """
    Decorator to trace a function call.

    Args:
        name: Optional name for the span. Defaults to function name.
        attributes: Optional attributes to add to the span.
        capture_args: If True, capture function arguments as span attributes.

    Returns:
        Decorated function.
    """

    def decorator(func: F) -> F:
        span_name = name or func.__name__

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _is_tracing_enabled():
                return func(*args, **kwargs)

            tracer = trace.get_tracer(func.__module__)
            attrs = attributes.copy() if attributes else {}
            if capture_args:
                # Basic arg capturing, avoiding potentially large or sensitive data
                # In a real implementation we might want to be more selective
                for i, arg in enumerate(args):
                    attrs[f"arg.{i}"] = str(arg)[:1024]
                for k, v in kwargs.items():
                    attrs[f"arg.{k}"] = str(v)[:1024]

            with tracer.start_as_current_span(
                span_name, attributes=attrs, kind=SpanKind.INTERNAL, record_exception=False
            ) as span:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _is_tracing_enabled():
                return await func(*args, **kwargs)

            tracer = trace.get_tracer(func.__module__)
            attrs = attributes.copy() if attributes else {}
            if capture_args:
                for i, arg in enumerate(args):
                    attrs[f"arg.{i}"] = str(arg)[:1024]
                for k, v in kwargs.items():
                    attrs[f"arg.{k}"] = str(v)[:1024]

            with tracer.start_as_current_span(
                span_name, attributes=attrs, kind=SpanKind.INTERNAL, record_exception=False
            ) as span:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def create_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
) -> Any:
    """
    Context manager to create a manual span.

    Usage:
        with create_span("my-operation", attributes={"key": "value"}):
            do_something()
    """
    if not _is_tracing_enabled():
        return trace.use_span(trace.INVALID_SPAN)

    tracer = trace.get_tracer(__name__)
    return tracer.start_as_current_span(name, attributes=attributes, kind=kind)


def current_span() -> Span | None:
    """
    Get the currently active span.

    Returns None if no span is active or if the active span is invalid.
    """
    span = trace.get_current_span()
    if span is trace.INVALID_SPAN:
        return None
    return span


def add_span_attributes(**kwargs: Any) -> None:
    """
    Add attributes to the current span.
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes(kwargs)


def record_exception(exception: Exception) -> None:
    """
    Record an exception on the current span and set status to ERROR.
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.record_exception(exception)
        span.set_status(Status(StatusCode.ERROR, str(exception)))
