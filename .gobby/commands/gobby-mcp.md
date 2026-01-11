---
description: This skill should be used when the user asks to "/gobby-mcp", "mcp servers", "list tools", "add server", "call tool". Manage MCP servers and tools - list, add, remove, search, and call tools.
---

# /gobby-mcp - MCP Server Management Skill

This skill manages MCP servers and tools via the gobby MCP proxy. Parse the user's input to determine which subcommand to execute.

## Subcommands

### `/gobby-mcp servers` - List all MCP servers
Call `gobby.list_mcp_servers` with no arguments.

Returns all configured MCP servers with:
- Connection status
- Available tools count
- Transport type

Example: `/gobby-mcp servers` → `list_mcp_servers()`

### `/gobby-mcp tools <server>` - List tools from a server
Call `gobby.list_tools` with:
- `server`: Server name (required)

Returns brief metadata for all tools on that server.

Example: `/gobby-mcp tools context7` → `list_tools(server="context7")`
Example: `/gobby-mcp tools gobby-tasks` → `list_tools(server="gobby-tasks")`

### `/gobby-mcp schema <server> <tool>` - Get full tool schema
Call `gobby.get_tool_schema` with:
- `server_name`: Server name
- `tool_name`: Tool name

Returns the complete inputSchema for the tool.

Example: `/gobby-mcp schema gobby-tasks create_task` → `get_tool_schema(server_name="gobby-tasks", tool_name="create_task")`

### `/gobby-mcp call <server> <tool> [args]` - Execute a tool
Call `gobby.call_tool` with:
- `server_name`: Server name
- `tool_name`: Tool name
- `arguments`: Optional dict of arguments

Example: `/gobby-mcp call gobby-memory list_memories` → `call_tool(server_name="gobby-memory", tool_name="list_memories")`
Example: `/gobby-mcp call context7 get-library-docs {"library": "react"}` → `call_tool(server_name="context7", tool_name="get-library-docs", arguments={"library": "react"})`

### `/gobby-mcp recommend <task>` - Get tool recommendations
Call `gobby.recommend_tools` with:
- `task_description`: What you're trying to accomplish
- `agent_id`: Optional agent profile filter
- `search_mode`: "llm" (default), "semantic", or "hybrid"
- `top_k`: Max recommendations (default 10)

Returns intelligent tool recommendations with usage suggestions.

Example: `/gobby-mcp recommend create a new task` → `recommend_tools(task_description="create a new task")`
Example: `/gobby-mcp recommend fetch documentation for React` → `recommend_tools(task_description="fetch documentation for React")`

### `/gobby-mcp search <query>` - Search for tools semantically
Call `gobby.search_tools` with:
- `query`: Natural language description
- `top_k`: Max results (default 10)
- `min_similarity`: Threshold 0-1 (default 0.0)
- `server`: Optional server filter

Returns tools matching the query, sorted by similarity.

Example: `/gobby-mcp search task management` → `search_tools(query="task management")`
Example: `/gobby-mcp search memory storage --server=gobby-memory` → `search_tools(query="memory storage", server="gobby-memory")`

### `/gobby-mcp add <name>` - Add a new MCP server
Call `gobby.add_mcp_server` with:
- `name`: Unique server name (required)
- `transport`: "http", "stdio", or "websocket" (required)
- `url`: Server URL (for http/websocket)
- `command`: Command to run (for stdio)
- `args`: Command arguments (for stdio)
- `env`: Environment variables (for stdio)
- `headers`: Custom HTTP headers (for http)
- `enabled`: Whether enabled (default true)

Example: `/gobby-mcp add myserver http https://example.com/mcp` → `add_mcp_server(name="myserver", transport="http", url="https://example.com/mcp")`
Example: `/gobby-mcp add local stdio npx mcp-server` → `add_mcp_server(name="local", transport="stdio", command="npx", args=["mcp-server"])`

### `/gobby-mcp remove <name>` - Remove an MCP server
Call `gobby.remove_mcp_server` with:
- `name`: Server name to remove

Example: `/gobby-mcp remove myserver` → `remove_mcp_server(name="myserver")`

### `/gobby-mcp import` - Import MCP servers
Call `gobby.import_mcp_server` with:
- `from_project`: Source project name
- `servers`: Optional list of specific server names
- `github_url`: GitHub repo URL to parse
- `query`: Natural language search query

Example: `/gobby-mcp import --from=other-project` → `import_mcp_server(from_project="other-project")`
Example: `/gobby-mcp import --github=https://github.com/user/repo` → `import_mcp_server(github_url="https://github.com/user/repo")`

### `/gobby-mcp init [name]` - Initialize Gobby project
Call `gobby.init_project` with:
- `name`: Optional project name (auto-detected if not provided)
- `github_url`: Optional GitHub URL (auto-detected from git remote)

Creates `.gobby/project.json` in the current directory.

Example: `/gobby-mcp init` → `init_project()`
Example: `/gobby-mcp init my-project` → `init_project(name="my-project")`

## Response Format

After executing the appropriate MCP tool, present the results clearly:
- For servers: Table of servers with status indicators
- For tools: List with tool name and brief description
- For schema: Full inputSchema formatted for readability
- For call: Tool result formatted appropriately
- For recommend/search: Ranked list with descriptions
- For add/remove/import: Confirmation with details
- For init: Project configuration summary

## Progressive Disclosure Pattern

For efficient token usage, follow this pattern:
1. `servers` - See available MCP servers
2. `tools <server>` - Brief metadata for server's tools
3. `schema <server> <tool>` - Full schema when needed
4. `call <server> <tool>` - Execute with arguments

## Error Handling

If the subcommand is not recognized, show available subcommands:
- servers, tools, schema, call, recommend, search, add, remove, import, init
