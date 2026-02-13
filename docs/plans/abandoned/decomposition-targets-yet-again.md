# Decomposition Targets (February 2026)

This document outlines the next phase of "Strangler Fig" decomposition for the Gobby codebase. The goal is to reduce the complexity of "God Objects" (files > 1000 lines) and improve maintainability by extracting distinct concerns into specialized modules.

## Summary of Candidates

| File Path | Line Count | Domain | Primary Issue |
| :--- | :--- | :--- | :--- |
| `src/gobby/workflows/loader.py` | 1142 | Workflows | Mixed IO, Validation, Caching, and Adapter logic. |
| `src/gobby/memory/manager.py` | 1129 | Memory | Core CRUD mixed with Embedding, Search, and Multimodal logic. |
| `src/gobby/cli/installers/shared.py` | 1062 | Install | Generic FS utils mixed with specific Installer logic and MCP config. |
| `src/gobby/cli/workflows.py` | 1034 | CLI | Click definitions mixed with View/Formatting and Service orchestration. |
| `src/gobby/agents/runner.py` | 1011 | Agents | Execution loop mixed with DB tracking and Session management. |

---

## 1. `src/gobby/workflows/loader.py` (1142 lines)

**Domain**: Workflow Loading & Validation

**Seams Identified**:
1.  **Validation Logic**: Deep validation of pipeline references (variable refs, `$step_id.output`) is a complex, distinct concern.
    *   **Proposed Migration**: `src/gobby/workflows/validation/references.py`
2.  **Discovery & Caching**: The file system scanning and caching (`_CachedEntry`, `_CachedDiscovery`) is orthogonal to parsing.
    *   **Proposed Migration**: `src/gobby/workflows/discovery/cache.py` or `scanner.py`
3.  **Agent Spec Adapters**: Logic for parsing "inline" workflows from agent specs (`meeseeks:worker`) is an adapter pattern.
    *   **Proposed Migration**: `src/gobby/workflows/adapters/agent_spec.py`

## 2. `src/gobby/memory/manager.py` (1129 lines)

**Domain**: Memory Orchestration

**Seams Identified**:
1.  **Multimodal Ingestion**: Logic for `remember_with_image` and `remember_screenshot` involves specific LLM interactions and file IO.
    *   **Proposed Migration**: `src/gobby/memory/services/ingestion.py` (or `multimodal.py`)
2.  **Embeddings**: Low-level embedding generation (`_store_embedding_sync`, `reindex_embeddings`) and queuing.
    *   **Proposed Migration**: `src/gobby/memory/services/embeddings.py`
3.  **Cross-Referencing**: The `_create_crossrefs` logic is a background enrichment process.
    *   **Proposed Migration**: `src/gobby/memory/services/crossref.py`

## 3. `src/gobby/cli/installers/shared.py` (1062 lines)

**Domain**: Installation & Setup

**Seams Identified**:
1.  **File System Utilities**: `_install_resource_dir`, `create_symlink`, `_safe_remove` are generic filesystem helpers.
    *   **Proposed Migration**: `src/gobby/cli/installers/fs.py`
2.  **MCP Configuration**: The logic to parse and update `claude.json` / `settings.json` for MCP servers.
    *   **Proposed Migration**: `src/gobby/cli/installers/mcp.py`
3.  **Router/Skill Flattening**: Converting structured skills into flat commands is a specific transformation logic.
    *   **Proposed Migration**: `src/gobby/cli/installers/skills.py`

## 4. `src/gobby/cli/workflows.py` (1034 lines)

**Domain**: CLI View Layer

**Seams Identified**:
1.  **Formatting/View Logic**: The file contains extensive `if json_format:` blocks and `rich` table construction.
    *   **Proposed Migration**: `src/gobby/cli/formatting/workflows.py` (View Layer)
2.  **Command Implementation**: Separate the *definition* of the Click command from the *implementation* script.
    *   **Proposed Migration**: `src/gobby/cli/commands/workflows/` (Package of implementation modules)

## 5. `src/gobby/agents/runner.py` (1011 lines)

**Domain**: Agent Orchestration

**Seams Identified**:
1.  **Run Tracking**: Database operations for creating/updating runs are mixed with execution logic.
    *   **Proposed Migration**: `src/gobby/agents/tracking.py`
2.  **Execution Loop**: The core generic execution loop could be separated from the specific initialization and cleanup.
    *   **Proposed Migration**: `src/gobby/agents/execution/loop.py`
3.  **Session Management**: Child session creation helper logic.
    *   **Proposed Migration**: `src/gobby/agents/execution/session.py`

## Shim Strategy

For all targets, we will follow the standard Gobby decomposition pattern:
1.  **Extract**: Move code to new module.
2.  **Shim**: Import the new module in the old file and alias the symbol.
    ```python
    # Old file
    from gobby.new_module import NewClass as OldClass
    ```
3.  **Refactor**: Update consumers to import from the new location (optional, or done in batches).
4.  **Cleanup**: Remove the shim once all consumers are updated.
