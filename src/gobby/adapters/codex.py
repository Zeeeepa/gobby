"""Codex CLI integration for gobby-daemon.

This module provides two integration modes for Codex CLI:

1. App-Server Mode (programmatic control):
   - CodexAppServerClient: Spawns `codex app-server` subprocess
   - CodexAdapter: Translates app-server events to HookEvent
   - Full control over threads, turns, and streaming events

2. Notify Mode (installed hooks via `gobby install --codex`):
   - CodexNotifyAdapter: Handles HTTP webhooks from Codex notify config
   - Fire-and-forget events on agent-turn-complete

Architecture:
    App-Server Mode:
        gobby-daemon
        └── CodexAppServerClient
            ├── Spawns: `codex app-server` (stdio subprocess)
            ├── Protocol: JSON-RPC 2.0 over stdin/stdout
            └── CodexAdapter (translates events to HookEvent)

    Notify Mode:
        Codex CLI
        └── notify script (installed by `gobby install --codex`)
            └── HTTP POST to /hooks/execute
                └── CodexNotifyAdapter (translates to HookEvent)

See: https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md

This module acts as a facade, re-exporting all public types from the
codex_impl subpackage for backward compatibility.
"""

from __future__ import annotations

# Re-export adapters from codex_impl.adapter
from gobby.adapters.codex_impl.adapter import (
    CodexAdapter,
    CodexNotifyAdapter,
    _get_machine_id,
)

# Re-export client from codex_impl.client
from gobby.adapters.codex_impl.client import (
    CODEX_SESSIONS_DIR,
    CodexAppServerClient,
)

# Re-export types from codex_impl.types
from gobby.adapters.codex_impl.types import (
    CodexConnectionState,
    CodexItem,
    CodexThread,
    CodexTurn,
    NotificationHandler,
)

# Public API - all exports for backward compatibility
__all__ = [
    # Types
    "CodexConnectionState",
    "CodexThread",
    "CodexTurn",
    "CodexItem",
    "NotificationHandler",
    # Client
    "CodexAppServerClient",
    "CODEX_SESSIONS_DIR",
    # Adapters
    "CodexAdapter",
    "CodexNotifyAdapter",
    # Utilities (internal, but re-exported for compatibility)
    "_get_machine_id",
]
