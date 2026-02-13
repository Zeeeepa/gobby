 # Workflow UI: DB Storage + Visual Builder

  ## Context

  Workflow definitions currently live as YAML files on disk, loaded by `WorkflowLoader` with filesystem scanning. This works for power users but prevents building a visual editor. We need
  to:

  1. Move workflow/pipeline definitions into the SQLite database as source of truth
  2. Import all bundled YAML workflows into DB on first boot
  3. Build a full visual workflow builder with drag-and-drop canvas (React Flow)
  4. Keep YAML as an import/export format for power users

  **User decisions:**
  - Single `workflow_definitions` table for both workflows and pipelines (type discriminator)
  - Full drag-and-drop canvas using React Flow (`@xyflow/react`)
  - One-off import of bundled YAMLs into DB (no fork mechanism - not live with users yet)

  **Inspiration & prior art:**
  - [Sim Studio](https://github.com/simstudioai/sim) — React Flow + Zustand, separation of canvas UI from execution
  - [Open Agent Builder](https://github.com/firecrawl/open-agent-builder) — React Flow, 8 node types (Start, Agent, MCP Tools, Transform, If/Else, While Loop, User Approval, End),
  node-level property editing
  - [Flowise](https://flowiseai.com/) — React Flow for LLM chain building
  - [Lobster/OpenClaw](https://github.com/openclaw/lobster) — YAML pipeline engine (no visual builder), confirms our approach is differentiated
  - React Flow has a [Workflow Editor template](https://reactflow.dev/components/templates/workflow-editor) with drag-and-drop sidebar, auto-layout (ELK), dark mode, runner functionality

  **Key React Flow patterns** (from Context7 docs):
  - `@xyflow/react` provides `ReactFlow`, `useNodesState`, `useEdgesState`, `Handle`, `Position`, `Controls`, `MiniMap`, `Background`, `Panel`
  - Drag-and-drop: `onDragOver` (preventDefault + dropEffect) + `onDrop` (screenToFlowPosition + create node) + `onDragStart` on palette items (setData + effectAllowed)
  - Custom nodes: `nodeTypes` object defined OUTSIDE component to prevent re-renders, each node uses `<Handle type="source|target" position={Position.Top|Bottom|Left|Right} />`
  - Dagre layout: `@dagrejs/dagre` (already installed) — `dagreGraph.setGraph({rankdir: 'TB'})`, set nodes with width/height, set edges, call `dagre.layout()`, map positions
  - Edges: `ConnectionLineType.SmoothStep` with `animated: true` for clean workflow arrows

  ---

  ## Phase 1: Database Storage Layer

  ### Migration 102 — `workflow_definitions` table

  **File:** `src/gobby/storage/migrations.py`

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

  Also bump `BASELINE_VERSION` to 102 and add table to baseline schema.

  ### Bundled Workflow Import (part of migration 102)

  Python migration function that:
  1. Uses `WorkflowLoader` to discover all bundled workflows from `src/gobby/install/shared/workflows/`
  2. For each discovered workflow, serializes to JSON and inserts with `source='bundled'`
  3. Handles both `lifecycle/` subdirectory and root directory workflows
  4. Sets `project_id=NULL` (global) for all bundled workflows

  ### Storage Manager

  **New file:** `src/gobby/storage/workflow_definitions.py`

  Pattern: Follow `src/gobby/storage/agent_definitions.py` exactly.

  ```python
  @dataclass
  class WorkflowDefinitionRow:
      id: str
      name: str
      workflow_type: str  # 'workflow' | 'pipeline'
      enabled: bool
      priority: int
      definition_json: str
      canvas_json: str | None
      source: str
      # ... metadata fields

  class LocalWorkflowDefinitionManager:
      def create(name, workflow_type, definition_json, ...) -> WorkflowDefinitionRow
      def get(definition_id) -> WorkflowDefinitionRow | None
      def get_by_name(name, project_id) -> WorkflowDefinitionRow | None
      def update(definition_id, **fields) -> WorkflowDefinitionRow
      def delete(definition_id) -> bool
      def list_all(project_id=None) -> list[WorkflowDefinitionRow]
      def list_by_type(workflow_type, project_id=None) -> list[WorkflowDefinitionRow]
      def import_from_yaml(yaml_content: str, project_id=None) -> WorkflowDefinitionRow
      def export_to_yaml(definition_id) -> str
      def duplicate(definition_id, new_name) -> WorkflowDefinitionRow
  ```

  ### WorkflowLoader Integration

  **File:** `src/gobby/workflows/loader.py`

  Add a `load_from_db()` path:
  - New method `load_workflow_from_db(name, project_id)` that queries the DB
  - Update `load_workflow()` to check DB first, then fall back to filesystem
  - Cache DB results with the same mtime-based invalidation (use `updated_at` as version)

  ---

  ## Phase 2: HTTP API Routes

  **New file:** `src/gobby/servers/routes/workflows.py`

  Pattern: Follow `src/gobby/servers/routes/agents.py` exactly.

  ### Request/Response Models

  ```python
  class CreateWorkflowRequest(BaseModel):
      name: str
      description: str | None = None
      workflow_type: str = "workflow"  # 'workflow' | 'pipeline'
      project_id: str | None = None
      definition: dict[str, Any]  # Full definition as dict
      canvas: dict[str, Any] | None = None
      enabled: bool = True
      priority: int = 100
      tags: list[str] | None = None

  class UpdateWorkflowRequest(BaseModel):
      name: str | None = None
      description: str | None = None
      definition: dict[str, Any] | None = None
      canvas: dict[str, Any] | None = None
      enabled: bool | None = None
      priority: int | None = None
      tags: list[str] | None = None
  ```

  ### Endpoints

  | Method | Path | Purpose |
  |--------|------|---------|
  | `GET /api/workflows` | List all definitions (query params: type, enabled, project_id) |
  | `GET /api/workflows/{id}` | Get single definition |
  | `POST /api/workflows` | Create new definition |
  | `PUT /api/workflows/{id}` | Update definition |
  | `DELETE /api/workflows/{id}` | Delete definition |
  | `POST /api/workflows/import` | Import from YAML string |
  | `GET /api/workflows/{id}/export` | Export as YAML |
  | `POST /api/workflows/{id}/duplicate` | Clone with new name |
  | `PUT /api/workflows/{id}/toggle` | Quick enable/disable toggle |

  ### Registration

  **File:** `src/gobby/servers/http.py`
  - Import `create_workflows_router`
  - Add `app.include_router(create_workflows_router(self))` alongside existing routers

  ---

  ## Phase 3: Web UI — Workflow List Page

  ### New Dependencies

  ```bash
  cd web && npm install @xyflow/react
  ```

  Note: `@dagrejs/dagre` already installed (for auto-layout).

  ### New Files

  | File | Purpose |
  |------|---------|
  | `web/src/hooks/useWorkflows.ts` | Data hook — CRUD, list, filters |
  | `web/src/components/WorkflowsPage.tsx` | List view — cards, filters, overview |
  | `web/src/components/WorkflowsPage.css` | List view styles |
  | `web/src/components/WorkflowBuilder.tsx` | Canvas builder — React Flow integration |
  | `web/src/components/WorkflowBuilder.css` | Builder styles |
  | `web/src/components/workflow-nodes/` | Custom React Flow node components |

  ### `useWorkflows.ts` Hook

  Pattern: Follow `web/src/hooks/useMcp.ts`

  ```typescript
  export interface WorkflowSummary {
    id: string
    name: string
    description: string | null
    workflow_type: 'workflow' | 'pipeline'
    enabled: boolean
    priority: number
    source: 'bundled' | 'custom' | 'imported'
    tags: string[]
    step_count: number
    trigger_count: number
    updated_at: string
  }

  export function useWorkflows() {
    const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
    const [loading, setLoading] = useState(false)
    const [selectedId, setSelectedId] = useState<string | null>(null)
    const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowDetail | null>(null)

    // CRUD operations
    const fetchWorkflows: () => Promise<void>
    const fetchWorkflow: (id: string) => Promise<WorkflowDetail>
    const createWorkflow: (data: CreateWorkflowData) => Promise<string | null>
    const updateWorkflow: (id: string, data: UpdateWorkflowData) => Promise<boolean>
    const deleteWorkflow: (id: string) => Promise<boolean>
    const duplicateWorkflow: (id: string, newName: string) => Promise<string | null>
    const toggleEnabled: (id: string) => Promise<boolean>
    const importYaml: (yaml: string) => Promise<string | null>
    const exportYaml: (id: string) => Promise<string | null>
  }
  ```

  ### `WorkflowsPage.tsx` — List View

  Layout modeled on `McpPage.tsx`:

  ```
  WorkflowsPage
  ├── Toolbar
  │   ├── Title + count badge
  │   ├── Search input
  │   ├── Import button
  │   ├── + New Workflow button
  │   └── + New Pipeline button
  ├── Overview Cards (clickable filters)
  │   ├── Total count
  │   ├── Workflows count
  │   ├── Pipelines count
  │   └── Active/Enabled count
  ├── Filter Chips
  │   ├── Type: All | Workflows | Pipelines
  │   ├── Source: All | Bundled | Custom | Imported
  │   └── Status: All | Enabled | Disabled
  ├── Workflow Cards Grid
  │   └── WorkflowCard (each)
  │       ├── Name + type badge (workflow/pipeline)
  │       ├── Description excerpt
  │       ├── Badges: source, priority, step count, trigger count
  │       ├── Enabled toggle switch
  │       └── Actions: Edit (opens builder), Duplicate, Export, Delete
  └── Create Modal (for new workflow/pipeline scaffold)
  ```

  Clicking "Edit" on a card transitions to the builder view. Use local state (`view: 'list' | 'builder'`) to switch between list and builder within the same page.

  ### `App.tsx` Integration

  **File:** `web/src/App.tsx`

  Replace the `ComingSoonPage` fallthrough for `activeTab === 'workflows'` with `<WorkflowsPage />`.

  ---

  ## Phase 4: Web UI — Visual Workflow Builder

  ### React Flow Canvas Architecture

  ```
  WorkflowBuilder
  ├── Toolbar
  │   ├── Back button (return to list)
  │   ├── Workflow name (editable)
  │   ├── Type badge
  │   ├── Save button
  │   ├── Export YAML button
  │   ├── Run/Test button (pipelines)
  │   └── Settings gear (priority, enabled, sources, variables)
  ├── Left Sidebar — Node Palette (200px)
  │   ├── For Workflows:
  │   │   ├── Step (draggable)
  │   │   ├── Trigger Group (draggable)
  │   │   ├── Observer (draggable)
  │   │   └── Exit Condition (draggable)
  │   ├── For Pipelines:
  │   │   ├── Exec Step (draggable)
  │   │   ├── Prompt Step (draggable)
  │   │   ├── MCP Step (draggable)
  │   │   ├── Pipeline Step (draggable)
  │   │   ├── Spawn Session (draggable)
  │   │   └── Approval Gate (draggable)
  │   └── Common:
  │       ├── Variable (draggable)
  │       └── Rule (draggable)
  ├── Center — React Flow Canvas
  │   ├── Custom nodes (see below)
  │   ├── Edges with labels (transition conditions)
  │   ├── Minimap
  │   ├── Controls (zoom, fit, lock)
  │   └── Background (dots pattern)
  └── Right Panel — Property Editor (360px)
      ├── Dynamic form based on selected node type
      ├── Step properties: name, tools, rules
      ├── Transition editor with CodeMirror for `when` expressions
      ├── Trigger editor: event type, conditions, actions
      ├── Action list editor (add/remove/reorder)
      └── Variable declarations editor
  ```

  ### Custom Node Types

  **Workflow nodes** (`web/src/components/workflow-nodes/`):

  | Node Type | File | Visual |
  |-----------|------|--------|
  | `StepNode` | `StepNode.tsx` | Card with name header, tool restriction badges, rule count, transition handles on bottom |
  | `TriggerNode` | `TriggerNode.tsx` | Colored header (event type), condition preview, action count |
  | `ObserverNode` | `ObserverNode.tsx` | Eye icon, event type, variable assignments |
  | `VariableNode` | `VariableNode.tsx` | Variable icon, name/default pairs, scope badge (workflow/session) |
  | `ExitNode` | `ExitNode.tsx` | Flag icon, exit condition expression |
  | `PipelineExecNode` | `PipelineExecNode.tsx` | Terminal icon, command preview |
  | `PipelineMcpNode` | `PipelineMcpNode.tsx` | Plug icon, server:tool display |
  | `PipelinePromptNode` | `PipelinePromptNode.tsx` | Message icon, prompt preview |
  | `ApprovalNode` | `ApprovalNode.tsx` | Shield icon, approval config |

  Each node:
  - Has connection handles (source/target) for edge connections
  - Shows a compact preview in the canvas
  - Opens full property editor in right panel on click/select
  - Matches the dark theme (--bg-secondary cards, --border edges, --accent highlights)

  ### Edge Types

  - **Transition edges** (workflow): Labeled with `when` condition, colored by type
  - **Sequential edges** (pipeline): Simple arrow showing execution order
  - **Conditional edges**: Dashed line with condition label

  ### Serialization: Canvas <-> Definition

  **Definition → Canvas (on load):**

  ```typescript
  function definitionToFlow(def: WorkflowDefinition, canvas?: CanvasState): { nodes: Node[], edges: Edge[] }
  ```

  - Each step → StepNode (positioned from canvas_json or auto-layout via dagre)
  - Each trigger group → TriggerNode
  - Each observer → ObserverNode
  - Transitions → edges between StepNodes
  - Auto-layout with `@dagrejs/dagre` when no canvas positions saved

  **Canvas → Definition (on save):**

  ```typescript
  function flowToDefinition(nodes: Node[], edges: Edge[]): { definition: WorkflowDefinition, canvas: CanvasState }
  ```

  - StepNodes → steps array (preserving all properties from the property editor)
  - TriggerNodes → triggers dict
  - Edges → transitions on source steps
  - Canvas positions saved separately in `canvas_json`

  ### Property Editor (Right Panel)

  Dynamic form rendered based on selected node type. Uses the same form patterns as `AgentDefinitionsPage.tsx` (grid layout, labeled inputs, collapsible sections).

  **Step properties form:**
  - Name (text input)
  - Description (textarea)
  - Status message (text input with template preview)
  - Tool Restrictions section (collapsible):
    - Allowed tools (multi-select or "all")
    - Blocked tools (multi-select)
    - MCP tool restrictions (server:tool format)
  - Rules section (collapsible):
    - Inline rules list (add/remove, each with when/tool/decision/reason)
    - Named rule references (check_rules)
  - Actions section (collapsible):
    - on_enter actions list
    - on_exit actions list
  - Transitions section (collapsible):
    - List of transitions with target step dropdown + when condition (CodeMirror)

  **Trigger properties form:**
  - Event type (select: on_session_start, on_stop, on_before_tool, on_before_agent, etc.)
  - Actions list with condition (when) and action type selectors

  **Pipeline step properties form:**
  - Step type (read-only badge)
  - Type-specific fields:
    - Exec: command (CodeMirror), timeout
    - Prompt: template (CodeMirror), tools list
    - MCP: server select, tool select, arguments editor
  - Condition (CodeMirror)
  - Approval gate toggle + config

  ### Drag-and-Drop from Palette

  Using React Flow's HTML Drag and Drop API integration (from Context7 docs):

  **Palette sidebar** — each item is a draggable div:
  ```tsx
  const onDragStart = (event: DragEvent, nodeType: string) => {
    event.dataTransfer.setData('application/reactflow', nodeType)
    event.dataTransfer.effectAllowed = 'move'
  }
  // <div draggable onDragStart={(e) => onDragStart(e, 'stepNode')}>Step</div>
  ```

  **Canvas** — `onDragOver` + `onDrop` handlers on `<ReactFlow>`:
  ```tsx
  const onDragOver = useCallback((event) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback((event) => {
    event.preventDefault()
    const type = event.dataTransfer.getData('application/reactflow')
    if (!type) return
    const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
    const newNode = { id: getId(), type, position, data: getDefaultData(type) }
    setNodes((nds) => nds.concat(newNode))
    setSelectedNode(newNode.id) // opens property panel
  }, [screenToFlowPosition])
  ```

  **Auto-layout** with dagre (already installed) when no canvas positions:
  ```tsx
  const getLayoutedElements = (nodes, edges, direction = 'TB') => {
    const g = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
    g.setGraph({ rankdir: direction })
    nodes.forEach(n => g.setNode(n.id, { width: 280, height: 80 }))
    edges.forEach(e => g.setEdge(e.source, e.target))
    dagre.layout(g)
    return { nodes: nodes.map(n => ({ ...n, position: { x: g.node(n.id).x - 140, y: g.node(n.id).y - 40 } })), edges }
  }
  ```

  **Node type registration** (defined OUTSIDE component to prevent re-renders):
  ```tsx
  const nodeTypes = {
    stepNode: StepNode,
    triggerNode: TriggerNode,
    observerNode: ObserverNode,
    variableNode: VariableNode,
    exitNode: ExitNode,
    pipelineExecNode: PipelineExecNode,
    pipelineMcpNode: PipelineMcpNode,
    pipelinePromptNode: PipelinePromptNode,
    approvalNode: ApprovalNode,
  }
  ```

  ---

  ## Phase 5: Integration & Polish

  ### MCP Tools Update

  **File:** `src/gobby/mcp_proxy/tools/workflows/_query.py`

  Update `list_workflows` and `get_workflow` tools to read from DB instead of filesystem. Keep backward compatibility — if DB has no results, fall back to loader.

  ### Create Workflow Templates

  Pre-built templates accessible from the "New" button:
  - **Blank Workflow** — empty steps + triggers
  - **Lifecycle Template** — enabled:true, common triggers (session_start, stop, before_tool)
  - **TDD Developer** — red/green/blue steps with tool restrictions
  - **Blank Pipeline** — empty sequential pipeline
  - **CI Pipeline Template** — build/test/deploy steps with approval gate

  ### Settings Panel (Workflow-Level)

  Accessible from the gear icon in the builder toolbar:
  - Name, description (editable)
  - Enabled toggle
  - Priority (number input)
  - Sources filter (multi-select: claude, gemini, codex)
  - Variables editor (key/value table for workflow-scoped)
  - Session variables editor (key/value table for session-scoped)
  - Rule definitions editor (named rules for reuse within workflow)
  - Exit condition (CodeMirror expression)

  ---

  ## File Manifest

  ### New Files

  | File | Purpose |
  |------|---------|
  | `src/gobby/storage/workflow_definitions.py` | `LocalWorkflowDefinitionManager` + `WorkflowDefinitionRow` |
  | `src/gobby/servers/routes/workflows.py` | HTTP API routes for workflow CRUD |
  | `web/src/hooks/useWorkflows.ts` | React hook for workflow API |
  | `web/src/components/WorkflowsPage.tsx` | List view page |
  | `web/src/components/WorkflowsPage.css` | List view styles |
  | `web/src/components/WorkflowBuilder.tsx` | Canvas builder page |
  | `web/src/components/WorkflowBuilder.css` | Builder styles |
  | `web/src/components/WorkflowPropertyPanel.tsx` | Right-side property editor |
  | `web/src/components/workflow-nodes/StepNode.tsx` | Workflow step node |
  | `web/src/components/workflow-nodes/TriggerNode.tsx` | Trigger group node |
  | `web/src/components/workflow-nodes/ObserverNode.tsx` | Observer node |
  | `web/src/components/workflow-nodes/PipelineStepNode.tsx` | Pipeline step node (all types) |
  | `web/src/components/workflow-nodes/nodeTypes.ts` | Node type registry + shared types |

  ### Modified Files

  | File | Change |
  |------|--------|
  | `src/gobby/storage/migrations.py` | Add migration 102 + bump BASELINE_VERSION |
  | `src/gobby/servers/http.py` | Register workflows router |
  | `src/gobby/workflows/loader.py` | Add DB lookup path |
  | `web/src/App.tsx` | Wire WorkflowsPage to 'workflows' tab |
  | `web/package.json` | Add `@xyflow/react` dependency |

  ---

  ## Implementation Order

  1. **DB layer** — migration, storage manager, tests
  2. **HTTP API** — routes, registration, test with curl
  3. **useWorkflows hook** — API integration
  4. **WorkflowsPage list view** — cards, filters, CRUD
  5. **WorkflowBuilder canvas** — React Flow setup, node types, palette
  6. **Property panel** — forms for each node type
  7. **Serialization** — definition ↔ canvas conversion
  8. **WorkflowLoader integration** — DB-first loading
  9. **Templates + polish** — starter templates, import/export

  ---

  ## Verification

  1. **DB migration**: `uv run gobby restart` — verify table created, bundled workflows imported
  2. **API**: `curl localhost:60887/api/workflows` — verify list returns imported workflows
  3. **API CRUD**: POST create, PUT update, DELETE, GET single — all work
  4. **UI list**: Open web UI → Workflows tab → see all imported workflows with cards
  5. **UI builder**: Click Edit on a workflow → canvas shows steps/triggers as nodes
  6. **UI edit**: Drag new step from palette → edit properties → save → verify API persists
  7. **UI pipeline**: Create pipeline → add exec/prompt/mcp steps → save → verify
  8. **Import/Export**: Export workflow as YAML → import YAML → verify round-trip
  9. **Loader integration**: Verify workflow engine still loads definitions correctly (via DB)
  10. **Tests**: `uv run pytest tests/storage/test_workflow_definitions.py tests/servers/routes/test_workflows.py -v`