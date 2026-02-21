---
name: expand
description: "Use when user asks to '/gobby expand', 'expand task', 'break down task', 'decompose task'. Expand a task into subtasks using codebase analysis and visible LLM reasoning. Survives session compaction."
category: core
triggers: expand task, break down, subtask, decompose
metadata:
  gobby:
    audience: interactive
    depth: 0
---

# /gobby expand - Task Expansion Skill

Expand a task into atomic subtasks. YOU do the analysis and reasoning (visible in conversation).
Survives session compaction - spec is saved before execution.

## Input Formats

- `#N` - Task reference (e.g., `/gobby expand #42`)
- `path.md` - Plan file (creates root task first, e.g., `/gobby expand docs/plan.md`)

## Session Context

**IMPORTANT**: Use the `session_id` from your SessionStart hook context.

Look for `Gobby Session Ref:` or `Gobby Session ID:` in your system context:
```
Gobby Session Ref: #5
Gobby Session ID: <uuid>
```

**Note**: All `session_id` parameters accept #N, N, UUID, or prefix formats. Prefix formats are accepted for convenience when they uniquely identify a session; if multiple sessions share the same prefix, the system will require a longer prefix or full UUID to resolve ambiguity.

## Tool Schema Reminder

**First time calling a tool this session?** Use `get_tool_schema(server_name, tool_name)` before `call_tool` to get correct parameters. Schemas are cached per session—no need to refetch.

## Workflow

### Phase 0: Check for Resume

First, check if there's a pending expansion to resume:

```python
result = call_tool("gobby-tasks", "get_expansion_spec", {"task_id": "<ref>"})
if result.get("pending"):
    # Skip directly to Phase 4 with saved spec
    print(f"Resuming expansion with {result['subtask_count']} subtasks")
    # Jump to Phase 4
```

If `pending=True`, skip to **Phase 4** immediately.

### Phase 1: Prepare

1. **Parse input**: Task ref (`#N`) or file path (`plan.md`)

2. **If file path**: Read file content, create root task:
   ```python
   content = Read(file_path)
   # Extract first heading as title
   result = call_tool("gobby-tasks", "create_task", {
       "title": "<first_heading>",
       "description": content,
       "task_type": "epic",
       "session_id": "<session_id>"
   })
   task_id = result["task"]["id"]
   ```

3. **Parse plan sections**: If the plan uses `### N.N` task headings, extract each section's
   content. These sections will be used verbatim as subtask descriptions in Phase 3.
   ```python
   # Parse heading-based plan sections
   # Each ### N.N section's content → subtask description
   plan_sections = {}  # {"1.1": "full section content...", "1.2": "..."}
   for heading in re.finditer(r'^### (\d+\.\d+)\s+', content, re.MULTILINE):
       section_num = heading.group(1)
       # Extract content from this heading to the next ### or ## heading
       plan_sections[section_num] = extract_section_content(content, heading)
   ```

4. **Get task details**:
   ```python
   task = call_tool("gobby-tasks", "get_task", {"task_id": "<ref>"})
   ```

5. **Check for existing children** and handle re-expansion:
   ```python
   children = call_tool("gobby-tasks", "list_tasks", {"parent_task_id": task_id})
   if children["tasks"]:
       # IMPORTANT: Re-expansion will delete all existing subtasks.
       # First, capture the full task object to preserve all fields.
       backup = call_tool("gobby-tasks", "get_task", {"task_id": task_id})

       # Prompt user for confirmation before cascade delete
       print(f"Task #{task_id} has {len(children['tasks'])} existing subtasks.")
       print("Re-expansion will delete all subtasks and their descendants.")
       # In practice, use AskUserQuestion tool for confirmation:
       # response = AskUserQuestion("Confirm re-expansion? This deletes all subtasks.", ...)
       # if not confirmed: return

       # Delete parent cascades to children
       call_tool("gobby-tasks", "delete_task", {"task_id": task_id, "cascade": True})

       # Re-create the parent task with ALL preserved fields from backup
       result = call_tool("gobby-tasks", "create_task", {
           "title": backup["title"],
           "description": backup["description"],
           "task_type": backup["type"],
           "priority": backup.get("priority"),
           "labels": backup.get("labels", []),
           "metadata": backup.get("metadata"),
           "validation_criteria": backup.get("validation_criteria"),
           "category": backup.get("category"),
           "session_id": "<session_id>"
       })
       task_id = result["task"]["id"]

       # Note: Commit links are tracked separately and cannot be preserved
       # through delete/create. If commits were linked, you may need to
       # re-link them manually using link_commit after re-creation.
   ```

### Phase 2: Analyze Codebase (VISIBLE)

Use YOUR tools to understand the codebase context. This analysis is visible in the conversation.

**Required analysis**:
- `Glob`: Find relevant source files matching the task domain
- `Grep`: Search for patterns, function names, classes
- `Read`: Examine key files for structure and patterns

**Required when plan references external libraries or GitHub repositories**:
- `context7`: Fetch library documentation for referenced packages/frameworks
- `gitingest`: Analyze referenced GitHub repositories for patterns and structure

#### Setup: External Research Tools

Before using `context7` or `gitingest`, ensure they are configured as MCP servers in Gobby:

1. **context7** - Fetches library documentation
   - Install: See https://github.com/upstash/context7 for setup instructions
   - Add to your MCP config (`~/.gobby/mcp_servers.yaml` or project `.gobby/mcp_servers.yaml`):
     ```yaml
     context7:
       transport: stdio
       command: npx
       args: ["-y", "@upstash/context7-mcp"]
     ```

2. **gitingest** - Analyzes GitHub repositories
   - Install: See https://github.com/cyclotruc/gitingest for setup instructions
   - Add to your MCP config:
     ```yaml
     gitingest:
       transport: stdio
       command: uvx
       args: ["gitingest-mcp"]
     ```

**Verify tools are available**: Run `list_mcp_servers()` to confirm both servers are connected.

#### Detection and Usage

Scan the task description/plan for:
- GitHub URLs (`github.com/...`, `github:...`)
- Library references (e.g., "SkillPort", "FastAPI", "React")
- Spec references (e.g., "Agent Skills spec", "OpenAPI spec")

If external references are found, you MUST use context7/gitingest before generating subtasks (see Setup above).

**Optional tools** (always available):
- `WebSearch`: External API/library research, current documentation

Example analysis approach:
```
1. Search for related code: Glob("**/auth*.py"), Glob("**/user*.py")
2. Find existing patterns: Grep("class.*Handler", type="py")
3. Read key files: Read("/src/api/routes.py")
4. If plan mentions "SkillPort": context7 to fetch SkillPort docs
5. If plan mentions "github.com/org/repo": gitingest to analyze repo structure
```

**What to extract from external research**:
- **Integrations**: How does the library connect? REST API, SDK, CLI, file format?
- **Dependencies**: What packages/tools are required? Version constraints?
- **Test patterns**: How does the reference project test this? Unit tests, integration tests, mocks?
- **Data models**: What are the key types/schemas/interfaces?
- **Error handling**: What errors can occur? How should they be handled?

### Phase 3: Generate & Save Spec

Think through the decomposition with these requirements:

**Requirements**:
1. **Preserve plan content**: If the parent task contains a plan with `### N.N` sections, each subtask description MUST include the FULL content from the corresponding plan section. Do NOT summarize, condense, or paraphrase.
2. **TDD prefix**: Prepend a 3-4 line TDD header (test file, implementation file, red-green cycle), then include the full plan section content below a `---` separator.
3. **Anti-summarization**: The plan author wrote specific code examples, model definitions, SQL schemas, YAML configs, and file paths for a reason. Every line from the plan section must appear in the subtask description.
4. **Atomicity**: Each task should be completable in 10-30 minutes
5. **Categories**: Use `code`, `config`, `docs`, `research`, `planning`, `manual`
6. **No separate test tasks**: TDD is embedded in each code/config task, not separate tasks
7. **Dependencies**: Use indices (0-based) to reference earlier subtasks

**Do NOT**:
- Replace plan section content with a brief summary
- Omit code examples, schemas, or configs from the plan
- Write descriptions shorter than the plan section they correspond to
- Paraphrase implementation specs that the plan author wrote verbatim

**Spec format**:
```python
spec = {
    "subtasks": [
        {
            "title": "Add User model with password hashing",
            "category": "code",
            "depends_on": [],
            "validation": "Tests pass. User model exists with hash_password method.",
            "description": (
                "TDD: 1) Write tests in tests/test_user.py.\n"
                "     2) Run tests (expect fail).\n"
                "     3) Implement in models/user.py.\n"
                "     4) Run tests (expect pass).\n"
                "\n---\n\n"
                "Target: `models/user.py`\n\n"
                "Add User model with bcrypt password hashing:\n\n"
                "class User(Base):\n"
                "    __tablename__ = 'users'\n"
                "    id: Mapped[int] = mapped_column(primary_key=True)\n"
                "    email: Mapped[str] = mapped_column(String(255), unique=True)\n"
                "    password_hash: Mapped[str] = mapped_column(String(60))\n\n"
                "    def hash_password(self, raw: str) -> None: ...\n"
                "    def verify_password(self, raw: str) -> bool: ...\n\n"
                "Migration: alembic/versions/001_add_users.py\n"
                "CREATE TABLE users (\n"
                "    id INTEGER PRIMARY KEY,\n"
                "    email VARCHAR(255) UNIQUE NOT NULL,\n"
                "    password_hash VARCHAR(60) NOT NULL\n"
                ");\n\n"
                "Edge cases: duplicate email (409), empty password (422)"
            ),
            "priority": 2
        },
        {
            "title": "Implement login endpoint",
            "category": "code",
            "depends_on": [0],  # Depends on User model
            "validation": "Tests pass. POST /login returns JWT on valid credentials.",
            "description": (
                "TDD: 1) Write tests in tests/test_auth.py.\n"
                "     2) Run tests (expect fail).\n"
                "     3) Implement in api/auth.py.\n"
                "     4) Run tests (expect pass).\n"
                "\n---\n\n"
                "Target: `api/auth.py`\n\n"
                "POST /login endpoint:\n"
                "- Accept {'email': str, 'password': str} JSON body\n"
                "- Look up user by email, verify with user.verify_password()\n"
                "- Return {'token': jwt_token, 'expires_in': 3600} on success\n"
                "- Return 401 with {'error': 'invalid_credentials'} on failure\n"
                "- JWT payload: {'sub': user.id, 'exp': now + 1h}"
            )
        }
    ]
}
```

**Save the spec BEFORE creating tasks** (this enables resume):
```python
result = call_tool("gobby-tasks", "save_expansion_spec", {
    "task_id": "<ref>",
    "spec": spec
})
# Returns: {"saved": True, "task_id": "...", "subtask_count": N}
```

### Phase 4: Execute (ATOMIC)

Execute the saved spec atomically:
```python
result = call_tool("gobby-tasks", "execute_expansion", {
    "task_id": "<ref>",
    "session_id": "<session_id>"
})
# Returns: {"created": ["#43", "#44", "#45"], "count": 3}
```

This creates all subtasks and wires dependencies in one transaction.

### Phase 5: Report

Show the created task tree with refs, dependencies, and description sizes:

```
Created 3 subtasks for #42 "Implement user authentication":

#43 [code] Add User model with password hashing
    └─ validation: Tests pass. User model exists with hash_password method.
    └─ description: (27 lines — TDD header + full plan section content)

#44 [code] Implement login endpoint (depends on #43)
    └─ validation: Tests pass. POST /login returns JWT on valid credentials.
    └─ description: (18 lines — TDD header + full plan section content)

#45 [code] Add logout endpoint (depends on #44)
    └─ validation: Tests pass. POST /logout invalidates session.
    └─ description: (14 lines — TDD header + full plan section content)

Use `suggest_next_task` to get the first ready task.
```

## Subtask Categories

| Category | When to Use | Requires TDD? |
|----------|-------------|---------------|
| `code` | Implementation tasks | Yes - test before implement |
| `config` | Configuration/YAML/schema changes | Yes - test loading, defaults, behavior |
| `docs` | Documentation updates | No |
| `research` | Investigation/exploration tasks | No |
| `planning` | Design/architecture tasks | No |
| `manual` | Manual testing/verification | No |

## TDD Approach

TDD workflow MUST be embedded in every `code` AND `config` task description,
followed by the **full plan section content**.

**Two-part description structure**:
```
TDD: 1) Write tests in <test_file>.
     2) Run tests (expect fail).
     3) Implement in <source_file>.
     4) Run tests (expect pass).

---

{FULL plan section content — code examples, schemas, configs, file paths,
behavioral specs. EVERYTHING from the plan section for this task.}
```

The TDD header is 3-4 lines. The plan content may be 5-100+ lines.

**Config tasks follow the same pattern**:
```
TDD: 1) Write tests in <test_file> verifying: config loads, defaults correct,
        validation works, system respects config.
     2) Run tests (expect fail).
     3) Create/update <config_file>.
     4) Run tests (expect pass).

---

{FULL plan section content for this config task...}
```

**Why this two-part structure?**
- The TDD header tells the agent the red-green workflow
- The plan content tells the agent WHAT to build — code, schemas, specs
- Without the plan content, agents guess at implementation details and guess wrong
- Explicit test file paths guide agents to correct locations
- "expect fail" / "expect pass" enforces red-green cycle

**Do NOT**:
- Replace plan section content with a brief summary
- Omit code examples, schemas, or configs from the plan
- Write descriptions shorter than the plan section they correspond to
- Create separate `[TEST]` and `[IMPL]` tasks
- Say only "write tests" without specifying what to test
- Omit test file paths from descriptions
- Skip tests for config tasks (they need tests too!)

## Error Handling

**Task not found**:
```
Error: Task #42 not found. Verify the task reference exists.
```

**Invalid spec**:
```
Error: Spec must contain 'subtasks' array with at least one subtask.
Each subtask requires a 'title' field.
```

**Session compaction recovery**:
If expansion was interrupted after Phase 3, the skill will detect the pending spec
and resume from Phase 4 automatically.

## Examples

### Basic Expansion
```
User: /gobby expand #42

Agent: Checking for pending expansion...
No pending spec found. Starting fresh expansion.

Phase 1: Getting task #42...
Task: "Implement user authentication" (feature)

Phase 2: Analyzing codebase...
[Glob, Grep, Read calls visible here]

Phase 3: Generating subtasks...
[Agent reasoning visible here]
Saving expansion spec with 4 subtasks...

Phase 4: Executing expansion...
Created 4 subtasks.

Phase 5: Task tree created:
#43 [code] Add User model...
#44 [code] Implement login...
...
```

### Resume After Interruption
```
User: /gobby expand #42

Agent: Checking for pending expansion...
Found pending spec with 4 subtasks. Resuming from Phase 4.

Phase 4: Executing expansion...
Created 4 subtasks.

Phase 5: Task tree created:
#43 [code] Add User model...
...
```

### From Plan File
```
User: /gobby expand docs/auth-plan.md

Agent: Reading plan file...
Parsing plan sections: found 6 task headings (### N.N)
Creating root epic from plan...
Created epic #50 "User Authentication System"

Phase 2: Analyzing codebase...
[Glob, Grep, Read calls visible here]

Phase 3: Generating subtasks...
Preserving plan section content for each subtask:
  1.1 "Add User model" → 27 lines (TDD header + model class + migration SQL)
  1.2 "Implement login" → 18 lines (TDD header + endpoint spec + JWT details)
  1.3 "Add logout"      → 14 lines (TDD header + session invalidation spec)
  2.1 "Add config"      → 22 lines (TDD header + YAML schema + defaults)
  2.2 "Add middleware"   → 31 lines (TDD header + auth flow + error codes)
  2.3 "Add rate limit"  → 19 lines (TDD header + rate limit config + headers)
Saving expansion spec with 6 subtasks...

Phase 4: Executing expansion...
Created 6 subtasks.
```
