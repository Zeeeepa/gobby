# Decomposition Targets (Feb 2026)

Based on a codebase scan performed on Feb 2, 2026, the following files have been identified as high-priority candidates for decomposition using the Strangler Fig pattern. These files exceed or near the 1,000-line threshold and exhibit "God Object" characteristics (mixed concerns, high coupling).

## Summary of Candidates

| File Path | Lines | Primary Domain | Priority |
| :--- | :--- | :--- | :--- |
| `src/gobby/servers/websocket.py` | 1135 | Network/Servers | **High** |
| `src/gobby/llm/claude.py` | 1114 | LLM Integration | **High** |
| `src/gobby/cli/skills.py` | 1068 | CLI | **Medium** |
| `src/gobby/storage/sessions.py` | 947 | Storage | **Medium** |
| `src/gobby/hooks/hook_manager.py` | 944 | Event Coordination | **High** |

## Detailed Analysis

### 1. `src/gobby/servers/websocket.py` (1135 lines)

**Current State**:
This file currently handles the entire lifecycle of WebSocket connections, including:

- **Transport Layer**: `WebSocketServer` class handling `accept`, `send`, `close`.
- **Authentication**: `_authenticate` method checking Bearer tokens.
- **Protocol Dispatch**: `_handle_message`, `_handle_tool_call`, `_handle_subscribe`.
- **Connection State**: `WebSocketClient` dataclass and tracking active connections.
- **MCP Routing**: Direct integration with `MCPClientManager`.

**Proposed Decomposition**:
Create a `src/gobby/servers/websocket/` package.

- **`connection.py`**: `WebSocketConnection` (renamed from Client) and `ConnectionManager`.
- **`router.py`**: `MessageRouter` to handle `_handle_message` and dispatching.
- **`auth.py`**: dedicated `WebSocketAuthenticator`.
- **`handlers/`**: Separate modules for `mcp.py` (tool calls) and `events.py` (pub/sub).

### 2. `src/gobby/llm/claude.py` (1114 lines)

**Current State**:
A monolithic provider implementation that mixes:

- **Core LLM Logic**: `generate_text`, `generate_summary`.
- **Subprocess Management**: `_find_cli_path`, `_verify_cli_path` (NPM interaction).
- **Streaming Protocol**: Defines 5+ protocol classes (`ToolCall`, `TextChunk`, `DoneEvent`) inline.
- **SDK Interaction**: Direct calls to `anthropic` or `claude-code` CLI.

**Proposed Decomposition**:
Create a `src/gobby/llm/providers/claude/` package.

- **`protocol.py`**: Extract `ToolCall`, `ChatEvent`, and other data models.
- **`cli.py`**: Extract all `_find_cli_path` and `npm` interaction logic into a `ClaudeCLIWrapper`.
- **`provider.py`**: The main `ClaudeLLMProvider` class, now much slimmer.
- **`streaming.py`**: Isolate the complex async generator logic for `stream_with_mcp_tools`.

### 3. `src/gobby/cli/skills.py` (1068 lines)

**Current State**:
Documentation-heavy CLI module that contains significant business logic:

- **Validation**: `validate` command contains schema validation logic for `SKILL.md`.
- **Metadata Manipulation**: `_get_nested_value`, `meta_set`, `meta_get` implement generic dict traversal.
- **Installation Logic**: `install` command mixes resolving sources (GitHub vs Local) with validtion.

**Proposed Decomposition**:

- **Move Logic**: Extract `SkillValidator` and `SkillMetaUtils` to `src/gobby/skills/utils.py` or `src/gobby/skills/validation.py`.
- **Refactor CLI**: The CLI command functions should be thin wrappers that call these services.

### 4. `src/gobby/storage/sessions.py` (947 lines)

**Current State**:
Nearing the 1000-line limit. It mixes:

- **Data Access**: `Session.from_row`, `LocalSessionManager` DB queries.
- **Business Logic**: `resolve_session_reference` (complex `#N` parsing).
- **Data Transformation**: `_parse_terminal_context`, `_parse_json_field`.

**Proposed Decomposition**:

- **`resolution.py`**: Extract `SessionReferenceResolver` to handle `#N`, `N`, and UUID parsing.
- **`models.py`**: Move `Session` dataclass and its `from_row` / `to_dict` methods to a dedicated models file.
- **`repository.py`**: Keep `LocalSessionManager` strictly for SQL execution.

### 5. `src/gobby/hooks/hook_manager.py` (944 lines)

**Current State**:
Intended as a "Clean Coordinator", it is re-accumulating complexity:

- **Initialization**: `__init__` is massive (~300 lines) setting up 10+ subsystems.
- **Webhook Logic**: Contains both sync and async webhook dispatch logic inline.
- **Health Checks**: internal `_start_health_check_monitoring`.

**Proposed Decomposition**:

- **`factory.py`**: Extract the massive initialization complexity into a `HookManagerFactory` or `Bootstrap` class.
- **`dispatchers/`**: Move `_dispatch_webhooks_*` logic into a composed `WebhookDelegator`.
