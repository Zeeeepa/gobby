# Workflow UI: DB Storage + Visual Builder

## Context

Workflow definitions currently live as YAML files on disk, loaded by `WorkflowLoader` with filesystem scanning. This works for power users but prevents building a visual editor. This plan moves definitions into SQLite as the source of truth, adds REST API routes for CRUD, builds a list page UI, and (in a future epic) a visual drag-and-drop builder using React Flow.

**User decisions:**
- Single `workflow_definitions` table for both workflows and pipelines (type discriminator)
- Full drag-and-drop canvas using React Flow (`@xyflow/react`) — Phase 4, separate epic
- One-off import of bundled YAMLs into DB (no fork mechanism)
- `definition_json` is source of truth; column fields (`name`, `enabled`, `priority`, `sources`) are denormalized for querying

## Constraints

1. **Migration 102 must be synchronous.** `WorkflowLoader.discover_workflows()` is async. The migration must scan the filesystem directly using `pathlib.Path.glob("*.yaml")` + `yaml.safe_load()`, not the loader.
2. **BASELINE_VERSION must bump to 102** and `workflow_definitions` table + indexes must be added to `BASELINE_SCHEMA`.
3. **Routes `__init__.py` must export** `create_workflows_router` alongside other router factories.
4. **`@xyflow/react` not yet installed** — must `npm install` before Phase 4. `@dagrejs/dagre` and `@atlaskit/pragmatic-drag-and-drop` already present.
5. **Workflow type mapping:** YAML `type: "pipeline"` -> DB `workflow_type: 'pipeline'`; YAML `type: "step"` or `type: "lifecycle"` or unset -> DB `workflow_type: 'workflow'`.
6. **Pipeline node unification:** `PipelineStep` has 6 mutually exclusive execution types (exec, prompt, invoke_pipeline, mcp, spawn_session, activate_workflow) — use a single `PipelineStepNode.tsx` with internal discriminator, not separate node files.

## Phase 1: Database Storage Layer

**Goal**: Workflow definitions stored in SQLite with CRUD operations, bundled YAMLs imported.

**Tasks:**
- [ ] Add migration 102 — `workflow_definitions` table + bundled YAML import (code)
- [ ] Create `LocalWorkflowDefinitionManager` storage manager (code)
- [ ] Add DB-first lookup path to `WorkflowLoader` (code, depends: Task 1-2)

### Migration 102

**File:** `src/gobby/storage/migrations.py`

SQL schema:
```sql
CREATE TABLE workflow_definitions (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    workflow_type TEXT NOT NULL DEFAULT 'workflow',  -- 'workflow' | 'pipeline'
    version TEXT DEFAULT '1.0',
    enabled INTEGER DEFAULT 1,
    priority INTEGER DEFAULT 100,
    sources TEXT,              -- JSON array: ["claude", "gemini"] or null
    definition_json TEXT NOT NULL,  -- Full WorkflowDefinition/PipelineDefinition as JSON
    canvas_json TEXT,          -- React Flow node/edge positions (UI-only state)
    source TEXT DEFAULT 'custom',  -- 'bundled' | 'custom' | 'imported'
    tags TEXT,                 -- JSON array for categorization
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(name, COALESCE(project_id, '__global__'))
);
CREATE INDEX idx_wf_defs_project ON workflow_definitions(project_id);
CREATE INDEX idx_wf_defs_name ON workflow_definitions(name);
CREATE INDEX idx_wf_defs_type ON workflow_definitions(workflow_type);
CREATE INDEX idx_wf_defs_enabled ON workflow_definitions(enabled);
```

Also add table + indexes to `BASELINE_SCHEMA`, bump `BASELINE_VERSION` to 102.

Python migration function `_migrate_add_workflow_definitions(db)`:
- Runs the CREATE TABLE + indexes SQL
- Scans `_BUNDLED_WORKFLOWS_DIR` (from `src/gobby/workflows/loader.py` line 53) using `Path.glob("**/*.yaml")`
- For each YAML: `yaml.safe_load()`, extract `name`, `description`, `type`, `enabled`, `priority`, `sources`, `version`
- Map `type` to `workflow_type`: `"pipeline"` -> `"pipeline"`, else `"workflow"`
- `json.dumps()` the full dict as `definition_json`, set `source='bundled'`, `project_id=NULL`
- `INSERT OR IGNORE` to handle re-runs

### Storage Manager

**New file:** `src/gobby/storage/workflow_definitions.py`

**Pattern:** Follow `src/gobby/storage/agent_definitions.py` exactly.

`WorkflowDefinitionRow` dataclass with all columns:
- `id`, `project_id`, `name`, `description`, `workflow_type`, `version`, `enabled` (bool), `priority` (int), `sources` (list[str] | None), `definition_json` (str), `canvas_json` (str | None), `source`, `tags` (list[str] | None), `created_at`, `updated_at`
- `from_row(cls, row)` classmethod — parse JSON for `sources`, `tags`
- `to_dict()` method

`LocalWorkflowDefinitionManager(db: DatabaseProtocol)`:
- `create(name, workflow_type, definition_json, ...)` -> `WorkflowDefinitionRow`
- `get(definition_id)` -> `WorkflowDefinitionRow | None`
- `get_by_name(name, project_id=None)` -> `WorkflowDefinitionRow | None` (project-scoped first, global fallback)
- `update(definition_id, **fields)` -> `WorkflowDefinitionRow`
- `delete(definition_id)` -> `bool`
- `list_all(project_id=None, workflow_type=None, enabled=None)` -> `list[WorkflowDefinitionRow]`
- `import_from_yaml(yaml_content, project_id=None)` -> `WorkflowDefinitionRow`
- `export_to_yaml(definition_id)` -> `str`
- `duplicate(definition_id, new_name)` -> `WorkflowDefinitionRow`

### WorkflowLoader Integration

**File:** `src/gobby/workflows/loader.py`

- Add optional `db: DatabaseProtocol | None = None` parameter to `__init__`
- In `load_workflow()` (line ~110): before filesystem search, if `self.db` is set, query DB via `LocalWorkflowDefinitionManager.get_by_name(name, project_path)`. If found, deserialize `definition_json` and return as `WorkflowDefinition`/`PipelineDefinition`. Cache with `updated_at` as staleness key.
- In `discover_workflows()` (line ~700): merge DB results with filesystem. DB entries shadow filesystem entries with same name.
- **File:** `src/gobby/runner.py` (line 305): pass `db=self.database` when constructing `WorkflowLoader()`

## Phase 2: HTTP API Routes

**Goal**: REST API for workflow definition CRUD, import/export, toggle.

**Tasks:**
- [ ] Create `src/gobby/servers/routes/workflows.py` with CRUD endpoints (code, depends: Phase 1)
- [ ] Register router in `__init__.py` and `http.py` (code, depends: Task 1)

### Routes

**New file:** `src/gobby/servers/routes/workflows.py`

**Pattern:** Follow `src/gobby/servers/routes/agents.py` exactly (factory function, Pydantic request models, lazy imports, metrics, try/catch).

Factory: `create_workflows_router(server: "HTTPServer") -> APIRouter`
Prefix: `/api/workflows`

Request models:
- `CreateWorkflowRequest(BaseModel)`: name, description, workflow_type, project_id, definition (dict), canvas (dict|None), enabled, priority, tags
- `UpdateWorkflowRequest(BaseModel)`: all optional overrides

Endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/workflows` | List (query: type, enabled, project_id) |
| GET | `/api/workflows/{id}` | Get single |
| POST | `/api/workflows` | Create |
| PUT | `/api/workflows/{id}` | Update |
| DELETE | `/api/workflows/{id}` | Delete |
| POST | `/api/workflows/import` | Import from YAML string |
| GET | `/api/workflows/{id}/export` | Export as YAML |
| POST | `/api/workflows/{id}/duplicate` | Clone with new name |
| PUT | `/api/workflows/{id}/toggle` | Enable/disable |

### Registration

- **File:** `src/gobby/servers/routes/__init__.py` — add import and `__all__` entry for `create_workflows_router`
- **File:** `src/gobby/servers/http.py` — add `app.include_router(create_workflows_router(self))` in `_register_routes()` (line ~684)

## Phase 3: Web UI — Workflow List Page

**Goal**: Workflows tab shows all definitions with cards, filters, and CRUD actions.

**Tasks:**
- [ ] Create `useWorkflows` data hook (code, depends: Phase 2)
- [ ] Create `WorkflowsPage` list view component + CSS (code)
- [ ] Wire `WorkflowsPage` into `App.tsx` workflows tab (code)

### useWorkflows Hook

**New file:** `web/src/hooks/useWorkflows.ts`

**Pattern:** Follow `web/src/hooks/useMcp.ts`

Interfaces: `WorkflowSummary` (id, name, description, workflow_type, enabled, priority, source, tags, step_count, trigger_count, updated_at), `WorkflowDetail` (adds definition_json, canvas_json)

Returns: `workflows`, `loading`, `selectedWorkflow`, CRUD functions (fetchWorkflows, createWorkflow, updateWorkflow, deleteWorkflow, duplicateWorkflow, toggleEnabled, importYaml, exportYaml)

### WorkflowsPage

**New files:** `web/src/components/WorkflowsPage.tsx`, `web/src/components/WorkflowsPage.css`

**Pattern:** Follow `McpPage.tsx` layout.

Structure:
- Toolbar: title + count, search input, import button, + New Workflow, + New Pipeline
- Overview cards: Total, Workflows, Pipelines, Active (clickable filters)
- Filter chips: Type (All|Workflows|Pipelines), Source (All|Bundled|Custom|Imported), Status (All|Enabled|Disabled)
- Workflow card grid: name, type badge, description, source badge, priority, step/trigger counts, enabled toggle, actions (Edit, Duplicate, Export, Delete)
- Edit opens read-only JSON view until Phase 4 adds the visual builder
- Create modal for new workflow/pipeline scaffold

### App.tsx Wiring

**File:** `web/src/App.tsx` — add `activeTab === 'workflows' ? <WorkflowsPage />` before `ComingSoonPage` fallthrough (around line 309)

## Phase 4: Web UI — Visual Builder (Separate Epic)

**Goal**: React Flow canvas for visual workflow editing with drag-and-drop and property panel.

This phase is large enough for its own epic. Summary of sub-phases:

### 4A: Canvas Scaffold
- Install `@xyflow/react`
- Create `WorkflowBuilder.tsx` with React Flow canvas, toolbar (back, name, save, export), palette sidebar
- Implement dagre auto-layout for nodes without saved canvas positions
- Implement `definitionToFlow()` / `flowToDefinition()` serialization

### 4B: Custom Node Types
- `workflow-nodes/nodeTypes.ts` — type registry + default data factories
- `StepNode.tsx` — workflow step (name, tool badges, rule count, transition handles)
- `TriggerNode.tsx` — trigger group (event type header, action count)
- `ObserverNode.tsx` — observer (eye icon, event type, variable assignments)
- `PipelineStepNode.tsx` — unified pipeline step (discriminated by exec type: exec/prompt/mcp/spawn/pipeline/activate)
- `VariableNode.tsx`, `ExitNode.tsx` — utility nodes

### 4C: Property Panel
- `WorkflowPropertyPanel.tsx` — right panel shell with dynamic form routing by node type
- Step form: name, description, tools, rules, transitions
- Trigger form: event type, conditions, actions
- Pipeline step form: type-specific fields (exec: command, prompt: template, mcp: server/tool/args)
- CodeMirror for `when` expressions

### 4D: Polish
- Palette drag-and-drop (React Flow HTML5 DnD pattern)
- Edge types (transition edges with condition labels, sequential pipeline edges)
- Save/load cycle (canvas_json persistence)
- Workflow settings panel (gear icon)

## Phase 5: Integration (Follow-up)

**Goal**: Update MCP tools to read from DB, add templates.

**Tasks:**
- [ ] Update MCP workflow query tools to use DB with filesystem fallback (code, depends: Phase 1)
- [ ] Create workflow templates (blank, lifecycle, TDD developer, blank pipeline, CI pipeline) (code)

### MCP Tools

**File:** `src/gobby/mcp_proxy/tools/workflows/_query.py`

`list_workflows()` (line 99): query DB via `LocalWorkflowDefinitionManager.list_all()`, merge with filesystem. `get_workflow()` (line 25): handled automatically by WorkflowLoader DB integration from Phase 1.

## File Manifest

### New Files (Phases 1-3)

| File | Purpose |
|------|---------|
| `src/gobby/storage/workflow_definitions.py` | `WorkflowDefinitionRow` + `LocalWorkflowDefinitionManager` |
| `src/gobby/servers/routes/workflows.py` | HTTP API routes for workflow CRUD |
| `web/src/hooks/useWorkflows.ts` | React hook for workflow API |
| `web/src/components/WorkflowsPage.tsx` | List view page |
| `web/src/components/WorkflowsPage.css` | List view styles |

### Modified Files (Phases 1-3)

| File | Change |
|------|--------|
| `src/gobby/storage/migrations.py` | Migration 102 + bump BASELINE_VERSION + add to BASELINE_SCHEMA |
| `src/gobby/workflows/loader.py` | Add `db` param to `__init__`, DB-first in `load_workflow`/`discover_workflows` |
| `src/gobby/runner.py` | Pass `db=self.database` to `WorkflowLoader()` (line 305) |
| `src/gobby/servers/routes/__init__.py` | Export `create_workflows_router` |
| `src/gobby/servers/http.py` | Register workflows router in `_register_routes()` |
| `web/src/App.tsx` | Wire `WorkflowsPage` to 'workflows' tab |

### Critical Reference Files

| File | Why |
|------|-----|
| `src/gobby/storage/agent_definitions.py` | Storage manager pattern to follow |
| `src/gobby/servers/routes/agents.py` | HTTP route pattern to follow |
| `web/src/hooks/useMcp.ts` | Data hook pattern to follow |
| `web/src/components/McpPage.tsx` | List page pattern to follow |
| `src/gobby/workflows/definitions.py` | `WorkflowDefinition` + `PipelineDefinition` Pydantic models (definition_json deserializes to these) |

## Verification

1. `uv run gobby restart` — verify migration 102 runs, table created, bundled workflows imported
2. `curl localhost:60887/api/workflows` — returns list of imported bundled workflows
3. CRUD: POST create, PUT update, DELETE, GET single — all return correct data
4. Web UI: Workflows tab shows cards for all workflows with correct metadata
5. Toggle enable/disable from UI card — persists via API
6. Import YAML → export YAML — round-trip preserves definition
7. WorkflowLoader still loads definitions correctly (DB-first, filesystem fallback)

## Plan Verification (TDD Compliance)

- No explicit test tasks found (TDD applied automatically by /gobby:expand)
- Dependency tree is valid (no cycles, all refs exist: Phase 2 depends Phase 1, Phase 3 depends Phase 2)
- Categories assigned: all `code` except npm install (`config`)
