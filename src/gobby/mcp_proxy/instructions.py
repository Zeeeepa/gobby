"""Gobby MCP server instructions.

Provides XML-structured instructions that teach agents how to use Gobby correctly.
These instructions are injected into the MCP server via FastMCP's `instructions` parameter.
"""


def build_gobby_instructions() -> str:
    """Build XML-structured instructions for Gobby MCP server.

    These instructions teach agents how to use Gobby correctly.
    Every agent connecting to Gobby receives these automatically.

    The instructions cover:
    - Session startup sequence
    - Progressive tool disclosure pattern
    - Progressive skill disclosure pattern
    - Critical rules for task management

    Returns:
        XML-structured instructions string
    """
    return """<gobby_system>

<startup>
At the start of EVERY session:
1. `list_mcp_servers()` — Discover available servers
2. `list_skills()` — Discover available skills
3. Session ID: Look for `Gobby Session Ref:` or `Gobby Session ID:` in your context.
   If missing, call:
   `call_tool("gobby-sessions", "get_current_session", {"external_id": "<your-session-id>", "source": "<cli-name>"})`

Session and task references use `#N` format (e.g., `#1`, `#42`) which is project-scoped.
</startup>

<tool_discovery>
NEVER assume tool schemas. Use progressive disclosure:
1. `list_tools(server="...")` — Lightweight metadata (~100 tokens/tool)
2. `get_tool_schema(server, tool)` — Full schema when needed
3. `call_tool(server, tool, args)` — Execute
</tool_discovery>

<skill_discovery>
Skills provide detailed guidance. Use progressive disclosure:
1. `list_skills()` — Already done at startup
2. `get_skill(name="...")` — Full content when needed
3. `search_skills(query="...")` — Find by task description
</skill_discovery>

<rules>
- Create/claim a task before using Edit, Write, or NotebookEdit tools
- Pass session_id to create_task (required), claim_task (required), and close_task (optional, for tracking)
- NEVER load all tool schemas upfront — use progressive disclosure
</rules>

</gobby_system>"""
