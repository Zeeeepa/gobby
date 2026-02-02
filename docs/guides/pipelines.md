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

Each step must have exactly one execution type: `exec`, `prompt`, or `invoke_pipeline`.

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

### Step Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Required. Unique step identifier |
| `exec` | string | Shell command to execute |
| `prompt` | string | LLM prompt template |
| `invoke_pipeline` | string | Pipeline name to invoke |
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
- `$inputs.param` - Pipeline input parameter
- `$step_id.status` - Step execution status

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
  on_approval_required:
    url: https://slack.com/webhook/xxx
    method: POST
    body:
      text: "Deployment needs approval: {{ execution_id }}"

  on_completed:
    url: https://api.example.com/notify
    headers:
      Authorization: "Bearer {{ env.API_TOKEN }}"

steps:
  - id: deploy
    exec: deploy-app
    approval:
      required: true
```

### Webhook Events

- `on_started` - Pipeline execution started
- `on_approval_required` - Waiting for approval
- `on_approved` - Approval granted
- `on_rejected` - Approval rejected
- `on_completed` - Pipeline finished successfully
- `on_failed` - Pipeline failed

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
