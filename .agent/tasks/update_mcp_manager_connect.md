# Task: Update MCP Proxy Manager Connect Method

## Objective

Update the `connect()` method in `src/mcp_proxy/manager.py` to prevent resource leaks when session initialization fails.

## Changes

Modified `src/mcp_proxy/manager.py`:

- Updated `_HTTPTransportConnection.connect`
- Updated `_StdioTransportConnection.connect`
- Updated `_WebSocketTransportConnection.connect`

## Details

For each transport class, the session initialization logic was wrapped in a `try/except` block.
If session initialization fails (`await self._session.initialize()`):

1. The session context is exited (`await session_context.__aexit__(...)`) if it was entered.
2. The transport context is exited (`await self._transport_context.__aexit__(...)`).
3. `self._session` and `self._transport_context` are set to `None`.
4. Connection state is set to `FAILED`.
5. The original exception is logged and re-raised wrapped in `MCPError`.

The outer `try/except` block in `connect` was updated to re-raise `MCPError` if it was already raised by the inner block, avoiding double wrapping.
