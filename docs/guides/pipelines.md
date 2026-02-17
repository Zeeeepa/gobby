# Gobby Pipelines

Pipelines are a third workflow type in Gobby that provide **typed, sequential execution** with explicit data flow between steps. Unlike step-based workflows (which are event-driven state machines), pipelines run to completion or pause at approval gates.

## Overview

### When to Use Pipelines

- **Deterministic automation**: CI/CD, deployment, data processing
- **Approval workflows**: Human-in-the-loop for sensitive operations
- **Multi-step orchestration**: Chained operations with data dependencies
- **LLM-powered automation**: AI steps with tool restrictions

### Pipeline vs Step Workflow

| Feature | Pipeline | Step Workflow |
|---------|----------|---------------|
| Execution model | Sequential, runs to completion | Event-driven state machine |
| Data flow | Explicit `$step.output` references | Via workflow variables |
| Approval gates | Built-in with resume tokens | Custom via actions |
| Tool restrictions | Per-step `tools` field | Via `allowed_tools`/`blocked_tools` |
| Typical use | Automation, CI/CD | Interactive agent guidance |

## Quick Start

Create a pipeline file at `.gobby/workflows/deploy.yaml`:

```yaml
name: deploy
type: pipeline
description: Deploy to production

steps:
  - id: build
    exec: npm run build

  - id: test
    exec: npm test

  - id: deploy
    exec: deploy-to-prod
    approval:
      required: true
      message: "Approve production deployment?"
```

Run it:

```bash
gobby pipelines run deploy
```

## YAML Schema Reference

### Pipeline Definition

```yaml
name: string              # Required: Pipeline name
type: pipeline            # Required: Must be "pipeline"
version: string           # Optional: Version (default: "1.0")
description: string       # Optional: Description

inputs:                   # Optional: Input parameters
  env:
    type: string
    default: staging
    description: Target environment

outputs:                  # Optional: Output mapping
  result: $deploy.output

steps:                    # Required: List of steps
  - id: step1
    exec: echo hello
```

### Step Types

Each step must have exactly one execution type: `exec`, `prompt`, `invoke_pipeline`, `mcp`, `spawn_session`, or `activate_workflow`.

#### exec - Shell Command

```yaml
- id: build
  exec: npm run build
  condition: $inputs.skip_build != 'true'
```

#### prompt - LLM Step

```yaml
- id: analyze
  prompt: |
    Analyze the test results in $test.output.
    Summarize failures and suggest fixes.
  tools:
    - Read
    - Grep
```

#### invoke_pipeline - Nested Pipeline

```yaml
- id: run_tests
  invoke_pipeline: test-suite
  condition: $build.status == 'success'
```

#### mcp - MCP Tool Call

Calls an MCP tool directly. Configure with `server`, `tool`, and optional `arguments`.

```yaml
- id: create-issue
  mcp:
    server: github
    tool: create_issue
    arguments:
      title: "Bug report from pipeline"
      body: ${{ steps.analyze.output.summary }}
```

#### spawn_session - Spawn CLI Session

Spawns a CLI session via tmux. Configure with `cli` (default `"claude"`), `prompt`, `cwd`, `workflow_name`, and `agent_depth` (default `1`).

```yaml
- id: worker
  spawn_session:
    cli: claude
    prompt: "Fix the bug described in $analyze.output"
    cwd: /path/to/project
    workflow_name: developer
    agent_depth: 1
```

#### activate_workflow - Activate Workflow

Activates a workflow on a session. Configure with `name` (required), `session_id` (required), and optional `variables`.

```yaml
- id: setup-workflow
  activate_workflow:
    name: developer
    session_id: ${{ steps.worker.output.session_id }}
    variables:
      session_task: "#123"
```

### Step Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Required. Unique step identifier |
| `exec` | string | Shell command to execute |
| `prompt` | string | LLM prompt template |
| `invoke_pipeline` | string | Pipeline name to invoke |
| `mcp` | object | MCP tool call config (`server`, `tool`, `arguments`) |
| `spawn_session` | object | Spawn CLI session config (`cli`, `prompt`, `cwd`, `workflow_name`, `agent_depth`) |
| `activate_workflow` | object | Activate workflow config (`name`, `session_id`, `variables`) |
| `condition` | string | Condition for step execution |
| `input` | string | Explicit input reference (e.g., `$prev_step.output`) |
| `approval` | object | Approval gate configuration |
| `tools` | list | Tool restrictions for prompt steps |

## Data Flow

Steps communicate via `$step.output` references:

```yaml
steps:
  - id: fetch
    exec: curl -s https://api.example.com/data

  - id: process
    exec: jq '.items[]'
    input: $fetch.output

  - id: analyze
    prompt: |
      Analyze the processed data: $process.output
      Identify trends and anomalies.
```

### Reference Syntax

- `$step_id.output` - Output from a previous step
- `$step_id.output.field` - Nested field within a step's output
- `$inputs.param` - Pipeline input parameter
- `$step_id.status` - Step execution status

## Template Syntax

Pipelines support Jinja2-style template expressions for dynamic values in step fields.

### Expression Syntax

Use `${{ expression }}` to embed template expressions. Internally, `${{ }}` is converted to `{{ }}` for Jinja2 rendering.

```yaml
- id: greet
  exec: echo "Deploying to ${{ inputs.environment }}"
```

### Available Variables

| Variable | Description |
|----------|-------------|
| `inputs.<param>` | Pipeline input parameters |
| `steps.<step_id>.output` | Output from a completed step |
| `steps.<step_id>.output.<field>` | Nested field from step output |
| `env.<VAR_NAME>` | Environment variable (with filtering, see below) |

### Environment Variable Access

Environment variables are available via `${{ env.VAR_NAME }}` in templates. Sensitive variables are automatically filtered out and will not be available.

**Filtered by suffix** (case-insensitive): `_SECRET`, `_KEY`, `_TOKEN`, `_PASSWORD`, `_CREDENTIAL`, `_PRIVATE_KEY`, `_AUTH`, `_OAUTH`, `_API_KEY`

**Filtered by name**: `DATABASE_URL`, `AWS_SECRET_ACCESS_KEY`, `API_KEY`, `AUTH_TOKEN`, `OAUTH_TOKEN`

```yaml
- id: notify
  mcp:
    server: slack
    tool: post_message
    arguments:
      channel: "#deploys"
      text: "Deployed version ${{ steps.build.output.version }}"
      # This would be filtered: ${{ env.SLACK_API_TOKEN }}
```

### Type Coercion in MCP Arguments

After template rendering, all values are strings. For MCP tool arguments, string values are automatically coerced to native types:

| String Value | Coerced To | Type |
|-------------|------------|------|
| `"true"` / `"false"` | `True` / `False` | bool |
| `"null"` / `"none"` | `None` | NoneType |
| `"600"` | `600` | int |
| `"3.14"` | `3.14` | float |

This ensures MCP tools receive the correct types even when values come from template expressions:

```yaml
- id: configure
  mcp:
    server: myserver
    tool: set_config
    arguments:
      timeout: ${{ inputs.timeout }}     # "600" -> 600
      verbose: ${{ inputs.verbose }}     # "true" -> True
      threshold: ${{ inputs.threshold }} # "3.14" -> 3.14
```

## Approval Gates

Approval gates pause execution until human approval:

```yaml
- id: deploy
  exec: deploy-to-prod
  approval:
    required: true
    message: "Approve production deployment?"
    timeout_seconds: 3600  # Optional: 1 hour timeout
```

When a pipeline hits an approval gate:

1. Execution pauses and returns a **resume token**
2. Pipeline status becomes `waiting_approval`
3. Use CLI or API to approve/reject with the token
4. On approval, execution resumes from that step

### Approval CLI

```bash
# Approve
gobby pipelines approve <token>

# Reject
gobby pipelines reject <token>
```

### Approval API

```bash
# Approve
curl -X POST http://localhost:60887/api/pipelines/approve/<token>

# Reject
curl -X POST http://localhost:60887/api/pipelines/reject/<token>
```

## Webhook Configuration

Pipelines can trigger webhooks on events:

```yaml
name: deploy
type: pipeline

webhooks:
  on_approval_pending:
    url: https://slack.com/webhook/xxx
    method: POST
    headers: {}

  on_complete:
    url: https://api.example.com/notify
    headers:
      Authorization: "Bearer ${{ env.API_TOKEN }}"

  on_failure:
    url: https://api.example.com/notify-failure

steps:
  - id: deploy
    exec: deploy-app
    approval:
      required: true
```

### Webhook Config Fields

The `WebhookConfig` model supports these fields:

- `on_approval_pending` -- Fires when a pipeline step is waiting for approval
- `on_complete` -- Fires when the pipeline finishes successfully
- `on_failure` -- Fires when the pipeline fails

Each webhook endpoint accepts `url` (required), `method` (default `"POST"`), and `headers` (optional dict).

## MCP Tool Exposure

Pipelines can be exposed as MCP tools for LLM agents:

```yaml
name: run-tests
type: pipeline
description: Run the test suite

expose_as_tool: true  # Makes this available as MCP tool

inputs:
  test_filter:
    type: string
    description: Filter tests by pattern

steps:
  - id: test
    exec: pytest -k "{{ inputs.test_filter }}"
```

When exposed, agents can invoke the pipeline:

```python
# Agent can call via MCP
result = mcp__gobby__call_tool(
    server_name="gobby-pipelines",
    tool_name="run-tests",
    arguments={"test_filter": "test_api"}
)
```

## MCP Tools

The `gobby-pipelines` MCP server registers the following tools for pipeline management:

| Tool | Description |
|------|-------------|
| `list_pipelines` | List available pipeline definitions |
| `get_pipeline` | Get details about a specific pipeline (steps, inputs) |
| `run_pipeline` | Run a pipeline by name with inputs |
| `approve_pipeline` | Approve a waiting pipeline execution |
| `reject_pipeline` | Reject a waiting pipeline execution |
| `get_pipeline_status` | Get execution status including step details |
| `create_pipeline` | Create from YAML content (must have `type: pipeline`) |
| `update_pipeline` | Update by name or ID |
| `delete_pipeline` | Delete by name or ID (bundled protected unless `force=True`) |
| `export_pipeline` | Export as YAML content |

Additionally, pipelines with `expose_as_tool: true` are automatically registered as dynamic MCP tools named `pipeline:<name>`. These tools accept the pipeline's declared inputs as arguments and run the pipeline when invoked.

## Execution Status Reference

### ExecutionStatus (pipeline-level)

| Status | Description |
|--------|-------------|
| `pending` | Pipeline created, not yet started |
| `running` | Pipeline is executing steps |
| `waiting_approval` | Paused at an approval gate |
| `completed` | All steps finished successfully |
| `failed` | A step failed |
| `cancelled` | Pipeline was rejected/cancelled |

### StepStatus (step-level)

| Status | Description |
|--------|-------------|
| `pending` | Step not yet started |
| `running` | Step is executing |
| `waiting_approval` | Step waiting for approval |
| `completed` | Step finished successfully |
| `failed` | Step failed |
| `skipped` | Step skipped (condition was false) |

## CLI Reference

### List Pipelines

```bash
gobby pipelines list
gobby pipelines list --json
```

### Show Pipeline Details

```bash
gobby pipelines show deploy
gobby pipelines show deploy --json
```

### Run Pipeline

```bash
# Run by name
gobby pipelines run deploy

# With inputs
gobby pipelines run deploy -i env=prod -i version=1.0

# Run Lobster file directly
gobby pipelines run --lobster ci.lobster

# JSON output
gobby pipelines run deploy --json
```

### Check Status

```bash
gobby pipelines status pe-abc123
gobby pipelines status pe-abc123 --json
```

### Approve/Reject

```bash
gobby pipelines approve <token>
gobby pipelines reject <token>
```

### Execution History

```bash
gobby pipelines history deploy
gobby pipelines history deploy --limit 10
gobby pipelines history deploy --json
```

### Import Lobster Files

```bash
# Import to .gobby/workflows/
gobby pipelines import ci.lobster

# Import to custom location
gobby pipelines import ci.lobster -o custom/path.yaml
```

## HTTP API Reference

### Run Pipeline

```
POST /api/pipelines/run
```

Request:
```json
{
  "name": "deploy",
  "inputs": {"env": "prod"},
  "project_id": "optional-project-id"
}
```

Response (200 - completed):
```json
{
  "status": "completed",
  "execution_id": "pe-abc123",
  "pipeline_name": "deploy"
}
```

Response (202 - waiting approval):
```json
{
  "status": "waiting_approval",
  "execution_id": "pe-abc123",
  "step_id": "deploy",
  "token": "approval-token-xyz",
  "message": "Approve production deployment?"
}
```

### Get Execution Status

```
GET /api/pipelines/{execution_id}
```

Response:
```json
{
  "id": "pe-abc123",
  "pipeline_name": "deploy",
  "project_id": "proj-1",
  "status": "completed",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:01:00Z",
  "steps": [
    {"id": 1, "step_id": "build", "status": "completed"},
    {"id": 2, "step_id": "test", "status": "completed"},
    {"id": 3, "step_id": "deploy", "status": "completed"}
  ]
}
```

### Approve Execution

```
POST /api/pipelines/approve/{token}
```

Response (200 - completed):
```json
{
  "status": "completed",
  "execution_id": "pe-abc123",
  "pipeline_name": "deploy"
}
```

Response (202 - needs another approval):
```json
{
  "status": "waiting_approval",
  "execution_id": "pe-abc123",
  "step_id": "next-approval-step",
  "token": "new-approval-token",
  "message": "Next approval needed"
}
```

### Reject Execution

```
POST /api/pipelines/reject/{token}
```

Response:
```json
{
  "status": "cancelled",
  "execution_id": "pe-abc123",
  "pipeline_name": "deploy"
}
```

## Complete Examples

### CI/CD Pipeline

```yaml
name: ci-cd
type: pipeline
description: Build, test, and deploy

inputs:
  environment:
    type: string
    default: staging

steps:
  - id: install
    exec: npm ci

  - id: lint
    exec: npm run lint

  - id: test
    exec: npm test

  - id: build
    exec: npm run build

  - id: deploy-staging
    exec: deploy --env staging
    condition: $inputs.environment == 'staging'

  - id: deploy-prod
    exec: deploy --env production
    condition: $inputs.environment == 'production'
    approval:
      required: true
      message: "Deploy to production?"
```

### Data Processing Pipeline

```yaml
name: etl-pipeline
type: pipeline
description: Extract, transform, load data

steps:
  - id: extract
    exec: |
      curl -s https://api.source.com/data \
        -H "Authorization: Bearer $SOURCE_API_KEY"

  - id: validate
    prompt: |
      Validate the extracted data: $extract.output
      Check for required fields and data types.
      Return JSON: {"valid": true/false, "errors": [...]}
    tools:
      - Read

  - id: transform
    exec: jq '.items | map({id, name, value})'
    input: $extract.output
    condition: $validate.output.valid == true

  - id: load
    exec: |
      curl -X POST https://api.dest.com/import \
        -H "Content-Type: application/json" \
        -d @-
    input: $transform.output
```

### Multi-Agent Orchestration

```yaml
name: task-orchestration
type: pipeline
description: Orchestrate multiple agents for parallel task work

steps:
  - id: find_tasks
    exec: gobby task list --status=open --type=task --json

  - id: spawn_workers
    prompt: |
      For each task in $find_tasks.output, spawn a worker agent:
      - Use spawn_agent with isolation=worktree
      - Assign one task per worker
      - Track spawned agent IDs
    tools:
      - mcp__gobby__call_tool

  - id: monitor
    exec: gobby agent list --status=running --json

  - id: review
    approval:
      required: true
      message: "All workers complete. Review and finalize?"

  - id: merge
    exec: |
      gobby worktree merge --all --strategy=squash
```

## See Also

- [Workflows Guide](./workflows.md) - Lifecycle and step-based workflows
- [Webhook Actions](./webhook-action-schema.md) - Webhook configuration
- [CLI Commands](./cli-commands.md) - Full CLI reference
- [HTTP Endpoints](./http-endpoints.md) - API documentation
