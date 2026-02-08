"""Gobby MCP server instructions.

Provides XML-structured instructions that teach agents how to use Gobby correctly.
These instructions are injected into the MCP server via FastMCP's `instructions` parameter.
"""


def build_gobby_instructions() -> str:
    """Build instructions for Gobby MCP server.

    Provides guidance for progressive tool disclosure, caching, task rules,
    available servers, skill discovery, and common mistakes to avoid.

    Returns:
        XML-structured instructions string
    """
    return """<gobby_system>

<tool_discovery>
NEVER assume tool schemas. Use progressive disclosure:
1. `list_mcp_servers()` — Discover server names
2. `list_tools(server="...")` — Lightweight metadata (~100 tokens/tool)
3. `get_tool_schema(server, tool)` — Full schema when needed
4. `call_tool(server, tool, args)` — Execute

Server names are internal sub-servers (see table below).
The name `"gobby"` is the MCP proxy namespace, not a server name.
</tool_discovery>

<servers>
| Server | Purpose |
|--------|---------|
| `gobby-tasks` | Task management |
| `gobby-sessions` | Session handoff |
| `gobby-memory` | Persistent memory |
| `gobby-workflows` | Workflow control |
| `gobby-agents` | Agent spawning |
| `gobby-worktrees` | Git worktrees |
| `gobby-clones` | Repository clones |
| `gobby-merge` | Merge resolution |
| `gobby-hub` | Hub / cross-project |
| `gobby-skills` | Skill management |
| `gobby-metrics` | Usage metrics |
| `gobby-artifacts` | Artifact storage |
| `gobby-pipelines` | Pipeline execution |
</servers>

<skills>
Discover skills with progressive disclosure too:
1. `list_skills()` on `gobby-skills` — Names and descriptions
2. `get_skill(name="...")` — Full skill content
3. `search_skills(query="...")` — Semantic search by topic
</skills>

<caching>
Schema fetches are cached per session. Once you call `get_tool_schema(server, tool)`,
you can `call_tool` repeatedly WITHOUT re-fetching. Only fetch on first use.
</caching>

<common_mistakes>
WRONG — Loading all schemas upfront (wastes 30-40K tokens):
  for server in servers: get_tool_schema(server, tool) for each tool

WRONG — Guessing parameters without schema:
  call_tool("gobby-tasks", "create_task", {"name": "Fix bug"})  # Wrong param!

RIGHT — Just-in-time discovery:
  get_tool_schema("gobby-tasks", "create_task")  # Learn: needs "title" not "name"
  call_tool("gobby-tasks", "create_task", {"title": "Fix bug", "session_id": "#123"})
</common_mistakes>

<rules>
- Create/claim a task before using Edit, Write, or NotebookEdit tools
- Pass session_id to create_task (required), claim_task (required), and close_task (optional, for tracking)
- NEVER load all tool schemas upfront — use progressive disclosure
</rules>

</gobby_system>"""
