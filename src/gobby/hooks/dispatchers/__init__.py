"""Hook event dispatchers for webhooks and MCP calls.

Extracted from HookManager to keep the coordinator under 800 lines.
"""

from gobby.hooks.dispatchers.mcp import (
    dispatch_mcp_calls,
    format_discovery_result,
    proxy_self_call,
    run_coro_blocking,
)
from gobby.hooks.dispatchers.webhook import (
    dispatch_webhooks_async,
    dispatch_webhooks_sync,
    evaluate_blocking_webhooks,
)

__all__ = [
    "dispatch_mcp_calls",
    "dispatch_webhooks_async",
    "dispatch_webhooks_sync",
    "evaluate_blocking_webhooks",
    "format_discovery_result",
    "proxy_self_call",
    "run_coro_blocking",
]
