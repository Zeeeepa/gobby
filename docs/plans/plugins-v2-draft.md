# Gobby Extensibility: MCP Routing + Plugin System

## Context

Gobby needs to be extensible for power users and eventually third-party developers. Two scenarios:
1. **Route an external MCP server through Gobby's proxy** — already partially works but DX is rough
2. **Install a plugin that bundles MCP servers + skills + rules** — doesn't exist yet

Strategy: **Level 1 (MCP routing polish) ships first as foundation, Level 2 (plugin system) layers on top.**

---

## Level 1: MCP Server Routing DX

### What Already Exists
- `MCPClientManager` — server registration, lazy connect, health/circuit breakers (`src/gobby/mcp_proxy/manager.py`)
- `LocalMCPManager` — DB CRUD with `upsert()`, `update_server()`, `list_servers()` (`src/gobby/storage/mcp.py`)
- `MCPServer` dataclass with `enabled` field (`src/gobby/storage/mcp.py`)
- HTTP API: `POST /api/mcp/servers`, `GET /api/mcp/servers`, `DELETE /api/mcp/servers/{name}` (`src/gobby/servers/routes/mcp/endpoints/server.py`)
- CLI group `gobby mcp-proxy` with 10+ subcommands: `add-server`, `remove-server`, `list-servers`, `list-tools`, `get-schema`, `call-tool`, `status`, etc. (`src/gobby/cli/mcp_proxy.py`)
- `gobby mcp-server` — standalone stdio server command used by AI CLIs (`src/gobby/cli/mcp.py`)

### What's Missing
1. No `PATCH` endpoint (enable/disable/update)
2. No `test` endpoint (validate connectivity before saving)
3. No `enable`/`disable` CLI commands
4. No `test` CLI command
5. No connection validation on `add-server`
6. No YAML config file support (`.gobby/mcp-servers.yaml`)
7. `mcp-proxy` is verbose — users want `gobby mcp`

### Changes

#### 1a. CLI Namespace: `gobby mcp` group
**File:** `src/gobby/cli/mcp.py`

Convert from standalone `mcp_server` command to a Click group:
```
gobby mcp serve          # was: gobby mcp-server (stdio server for AI CLIs)
gobby mcp add            # short alias → mcp-proxy add-server
gobby mcp remove         # short alias → mcp-proxy remove-server
gobby mcp list           # short alias → mcp-proxy list-servers
gobby mcp test <name>    # NEW
gobby mcp enable <name>  # NEW
gobby mcp disable <name> # NEW
gobby mcp sync           # NEW (YAML sync)
```

**Breaking change:** `gobby mcp-server` → `gobby mcp serve`. Add hidden compat shim in `cli/__init__.py` that delegates `mcp-server` → `mcp serve` with deprecation warning. AI CLI configs reference this exact command name.

**File:** `src/gobby/cli/__init__.py` — register `mcp` group, add hidden `mcp-server` compat command.

`gobby mcp-proxy` remains unchanged for backward compat and power-user access to lower-level commands (`get-schema`, `call-tool`, etc).

#### 1b. HTTP API: PATCH + Test endpoints
**File:** `src/gobby/servers/routes/mcp/endpoints/server.py`

**`PATCH /api/mcp/servers/{name}`** — Update server config (enable/disable, change URL, etc.)
- Calls `LocalMCPManager.update_server()`
- If `enabled` toggled off: disconnect live server
- If `enabled` toggled on: lazy connector picks it up
- Broadcast `server_updated` WebSocket event

**`POST /api/mcp/servers/{name}/test`** — Test connectivity
- Create temporary transport connection with 10s timeout
- On success: return `{"success": true, "tools": [...]}`
- On failure: return `{"success": false, "error": "..."}`
- Always clean up temp connection

**File:** `src/gobby/servers/routes/mcp/tools.py` — register new routes

#### 1c. MCPClientManager additions
**File:** `src/gobby/mcp_proxy/manager.py`

- `async update_server_config(name, **fields)` — update config in-memory + toggle connection state
- `async test_server(config) -> dict` — temp connection, list tools, disconnect, return result

#### 1d. Validation on add
**File:** `src/gobby/servers/routes/mcp/endpoints/server.py`

Modify `add_mcp_server()`: add optional `validate` param (default `true`). Test connection before persisting. Return structured error on failure.

**File:** `src/gobby/cli/mcp_proxy.py` — add `--skip-validation` flag to `add-server`

#### 1e. YAML Config + Sync
**File format:** `.gobby/mcp-servers.yaml`
```yaml
servers:
  context7:
    transport: http
    url: https://mcp.context7.com/mcp
    description: "Library docs"
    enabled: true

  my-db:
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-postgres"]
    env:
      POSTGRES_URL: "$secret:POSTGRES_URL"
```

**New file:** `src/gobby/mcp_proxy/sync.py`
- `sync_mcp_servers_from_yaml(db, project_id, yaml_path=None)` — parse YAML, upsert to DB
- `--prune` flag: remove DB servers not in YAML (off by default)
- `--dry-run` flag: show what would change

**Auto-sync:** On daemon startup if `.gobby/mcp-servers.yaml` exists (non-blocking, best-effort).

---

## Level 2: Plugin System

### Design

A **plugin** is a directory with a `PLUGIN.yaml` manifest that bundles existing Gobby primitives (MCP servers, skills, rules, pipelines, agents). No new runtime concepts — just composition and lifecycle.

### Manifest Format
```yaml
name: "postgres-toolkit"
version: "1.0.0"
description: "PostgreSQL tools for Gobby"
author: "user"
tags: ["database", "postgres"]

requires:
  gobby: ">=0.3.0"
  plugins:
    - name: "base-db-tools"
      version: ">=1.0.0"

provides:
  mcp_servers:
    - name: "postgres-tools"
      transport: stdio
      command: uvx
      args: ["mcp-server-postgres"]
      env:
        DATABASE_URL: "${POSTGRES_URL}"

  skills:
    - path: "skills/postgres-queries"

  rules:
    - path: "rules/block-raw-sql.yaml"

config_schema:
  POSTGRES_URL:
    type: string
    required: true
    secret: true
    description: "PostgreSQL connection string"
```

### Storage (migration v172)

Two new tables:

**`plugins`** — id, name, version, description, author, tags (JSON), source_type, source_url, source_ref, manifest_json, config_json, requires_json, enabled, project_id, installed_at, updated_at, deleted_at

**`plugin_components`** — id, plugin_id (FK), component_type (mcp_server/skill/rule/pipeline/agent), component_id (FK to actual table), component_name

Existing tables unchanged. Plugin-installed components use `source='plugin'` in their respective tables.

### Lifecycle

| Command | What it does |
|---------|-------------|
| `gobby plugins install github:user/repo` | Fetch, parse manifest, check deps, install components, record ownership |
| `gobby plugins remove <name>` | Remove all owned components, soft-delete plugin |
| `gobby plugins list` | Show installed plugins with status |
| `gobby plugins show <name>` | Show plugin details + components |
| `gobby plugins enable <name>` | Enable plugin + cascade to all owned components |
| `gobby plugins disable <name>` | Disable plugin + cascade to all owned components |
| `gobby plugins upgrade <name>` | Fetch new version, diff manifests, add/remove/update components |
| `gobby plugins config <name> --set KEY=VALUE` | Set plugin config values |

### Install Flow
1. Resolve source (GitHub clone via `SkillLoader.clone_skill_repo()`, local path, ZIP)
2. Parse `PLUGIN.yaml` → `PluginManifest` (Pydantic model)
3. Check deps: `requires.gobby` version, `requires.plugins` installed
4. Collect config: prompt for required `config_schema` fields, store secrets via secrets table
5. Install components by delegating to existing managers:
   - MCP servers → `LocalMCPManager.upsert()` with `source='plugin'`
   - Skills → `SkillLoader.load_skill()` + `LocalSkillManager.create_skill()`
   - Rules/pipelines/agents → `LocalWorkflowDefinitionManager.create()`
6. Record ownership in `plugins` + `plugin_components`
7. Notify daemon to hot-reload

### Namespace Isolation
Plugin component names prefixed: `my-plugin/postgres-tools`. Prevents collisions between plugins and user-installed components.

### New Files
```
src/gobby/plugins/
    __init__.py
    manifest.py       # PluginManifest Pydantic model
    installer.py      # Install/upgrade/uninstall logic
    resolver.py       # Dependency + version checking
    manager.py        # High-level orchestration

src/gobby/storage/plugins.py    # LocalPluginManager (DB CRUD)
src/gobby/cli/plugins.py        # Click CLI group
```

### Reused Patterns
- `SkillLoader.parse_github_url()` / `clone_skill_repo()` — source resolution
- `HubProvider` base class — plugin marketplace discovery (later)
- `LocalWorkflowDefinitionManager` — storage CRUD pattern (from_row/to_dict, soft deletes)
- `MCPClientManager` health + circuit breaker — failure isolation for plugin MCP servers

---

## Implementation Sequence

### Phase 1: Level 1 — API Layer
1. `PATCH /api/mcp/servers/{name}` endpoint + `MCPClientManager.update_server_config()`
2. `POST /api/mcp/servers/{name}/test` endpoint + `MCPClientManager.test_server()`
3. Validation-on-add for `add_mcp_server` endpoint

### Phase 2: Level 1 — CLI
4. `enable`, `disable`, `test` commands in `mcp-proxy` group
5. `--skip-validation` on `add-server`
6. New `gobby mcp` group in `mcp.py` with `serve` + short aliases
7. Backward-compat `mcp-server` shim

### Phase 3: Level 1 — YAML Sync
8. `src/gobby/mcp_proxy/sync.py` — sync function
9. `sync` CLI command
10. Auto-sync on daemon startup

### Phase 4: Level 2 — Plugin Foundation
11. DB migration v172: `plugins` + `plugin_components` tables
12. `storage/plugins.py` — LocalPluginManager
13. `plugins/manifest.py` — PluginManifest model

### Phase 5: Level 2 — Plugin Core
14. `plugins/resolver.py` — dependency resolution
15. `plugins/installer.py` — install/upgrade/uninstall
16. `plugins/manager.py` — orchestration

### Phase 6: Level 2 — Plugin CLI
17. `cli/plugins.py` — full CLI group
18. Register in `cli/__init__.py`

---

## Verification

### Level 1
1. `gobby mcp add --transport http --url https://mcp.context7.com/mcp context7` — should validate then register
2. `gobby mcp test context7` — should show connected + tool list
3. `gobby mcp disable context7` / `gobby mcp enable context7` — toggle works
4. Create `.gobby/mcp-servers.yaml`, run `gobby mcp sync` — servers appear in `gobby mcp list`
5. `gobby mcp serve` works, `gobby mcp-server` shows deprecation warning but still works
6. Run existing `mcp_proxy` tests + new unit tests for sync, test, enable/disable

### Level 2
7. Create a test plugin directory with `PLUGIN.yaml` containing an MCP server + skill
8. `gobby plugins install ./test-plugin` — components appear in their respective lists
9. `gobby plugins disable test-plugin` — MCP server disconnects, skill deactivated
10. `gobby plugins remove test-plugin` — all components cleaned up
11. Unit tests for manifest parsing, install flow, dependency resolution, storage CRUD

### Critical files to modify
- `src/gobby/cli/mcp.py` — restructure to group
- `src/gobby/cli/mcp_proxy.py` — add enable/disable/test, --skip-validation
- `src/gobby/cli/__init__.py` — register new groups
- `src/gobby/servers/routes/mcp/endpoints/server.py` — PATCH + test endpoints
- `src/gobby/servers/routes/mcp/tools.py` — register routes
- `src/gobby/mcp_proxy/manager.py` — update_server_config, test_server
- `src/gobby/storage/migrations.py` — v172 migration

### New files
- `src/gobby/mcp_proxy/sync.py` — YAML sync
- `src/gobby/plugins/__init__.py`
- `src/gobby/plugins/manifest.py`
- `src/gobby/plugins/installer.py`
- `src/gobby/plugins/resolver.py`
- `src/gobby/plugins/manager.py`
- `src/gobby/storage/plugins.py`
- `src/gobby/cli/plugins.py`
