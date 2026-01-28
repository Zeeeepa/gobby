"""
Codex adapter implementation package.

This package contains the decomposed implementation of the Codex adapter,
extracted from the monolithic codex.py using the Strangler Fig pattern.

Modules:
- types.py: Type definitions and data classes
- protocol.py: Protocol/interface definitions
- client.py: CodexAppServerClient implementation
- adapter.py: CodexAdapter and CodexNotifyAdapter implementations

Importer analysis (from codex.py):
- src/gobby/servers/http.py: imports CodexAdapter
- src/gobby/servers/routes/mcp/hooks.py: imports CodexNotifyAdapter
- src/gobby/adapters/__init__.py: imports CodexAdapter, CodexAppServerClient, CodexNotifyAdapter
- tests/adapters/test_codex.py: imports various items for testing

Migration strategy:
1. Extract types/dataclasses to types.py
2. Extract protocol definitions to protocol.py
3. Extract CodexAppServerClient to client.py
4. Extract adapters to adapter.py
5. Update codex.py to re-export from submodules
"""

# Phase 3: Placeholders - exports will be added as code is migrated
__all__: list[str] = []
