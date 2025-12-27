"""
FastMCP server for Gobby daemon control.

Provides MCP tools and resources for controlling the Gobby daemon,
including session management, status monitoring, and proxying calls
to downstream MCP servers.

Local-first version: No platform auth, no platform sync.
"""

import logging
import os
import time
import json
import asyncio
from typing import TYPE_CHECKING, Any, cast

from fastmcp import FastMCP

logger = logging.getLogger("gobby.mcp.server")

if TYPE_CHECKING:
    from gobby.config.app import DaemonConfig
    from gobby.hooks.hook_manager import HookManager
    from gobby.llm.base import LLMProvider
    from gobby.llm.service import LLMService
    from gobby.mcp_proxy.manager import MCPClientManager
    from gobby.storage.tasks import LocalTaskManager
    from gobby.sync.tasks import TaskSyncManager

    from gobby.memory.manager import MemoryManager
    from gobby.memory.skills import SkillLearner
    from gobby.storage.sessions import LocalSessionManager


_mcp_instance: FastMCP | None = None


def get_mcp_server() -> FastMCP | None:
    """Get the current MCP server instance."""
    return _mcp_instance


class GobbyDaemonTools:
    """Handler for Gobby Daemon MCP tools."""

    def __init__(
        self,
        mcp_manager: "MCPClientManager",
        daemon_port: int,
        websocket_port: int,
        start_time: float,
        internal_manager: Any,
        config: "DaemonConfig | None" = None,
        llm_service: "LLMService | None" = None,
        codex_client: Any | None = None,
        session_manager: "LocalSessionManager | None" = None,
        memory_manager: "MemoryManager | None" = None,
        skill_learner: "SkillLearner | None" = None,
    ):
        self.mcp_manager = mcp_manager
        self.daemon_port = daemon_port
        self.websocket_port = websocket_port
        self.start_time = start_time
        self.internal_manager = internal_manager
        self.config = config
        self.llm_service = llm_service
        self.codex_client = codex_client
        self.session_manager = session_manager
        self.memory_manager = memory_manager
        self.skill_learner = skill_learner

        # Extract config values
        self.code_exec_enabled = True
        self.code_exec_model = "claude-sonnet-4-5"
        self.code_exec_max_turns = 5
        self.code_exec_timeout = 30
        self.code_exec_preview = 3
        self.code_exec_prompt: str | None = None
        self.code_exec_provider: str | None = None

        if config:
            code_exec_config = config.get_code_execution_config()
            if code_exec_config:
                self.code_exec_enabled = code_exec_config.enabled
                self.code_exec_model = code_exec_config.model
                self.code_exec_max_turns = code_exec_config.max_turns
                self.code_exec_timeout = code_exec_config.default_timeout
                self.code_exec_preview = code_exec_config.max_dataset_preview
                self.code_exec_prompt = code_exec_config.prompt
                self.code_exec_provider = code_exec_config.provider

        self.recommend_tools_enabled = True
        self.recommend_tools_model = "claude-sonnet-4-5"
        self.recommend_tools_provider: str | None = None
        self.recommend_tools_prompt: str | None = None

        if config:
            recommend_tools_config = config.get_recommend_tools_config()
            if recommend_tools_config:
                self.recommend_tools_enabled = recommend_tools_config.enabled
                self.recommend_tools_model = recommend_tools_config.model
                self.recommend_tools_provider = recommend_tools_config.provider
                self.recommend_tools_prompt = recommend_tools_config.prompt

        self.mcp_proxy_enabled = True
        self.mcp_tool_timeout = 60.0

        if config:
            mcp_proxy_config = config.get_mcp_client_proxy_config()
            if mcp_proxy_config:
                self.mcp_proxy_enabled = mcp_proxy_config.enabled
                self.mcp_tool_timeout = mcp_proxy_config.tool_timeout

        # Import config stored as full config object
        self.import_mcp_server_config = config

        # Hook Manager init
        self._hook_manager: "HookManager | None" = None
        self.HOOK_TYPE_ALIASES = {
            "SessionStart": "session-start",
            "SessionEnd": "session-end",
            "PromptSubmit": "user-prompt-submit",
            "UserPromptSubmit": "user-prompt-submit",
            "Stop": "stop",
            "PreToolUse": "pre-tool-use",
            "PostToolUse": "post-tool-use",
            "PreCompact": "pre-compact",
            "SubagentStart": "subagent-start",
            "SubagentStop": "subagent-stop",
            "Notification": "notification",
            "session-start": "session-start",
            "session-end": "session-end",
            "user-prompt-submit": "user-prompt-submit",
            "stop": "stop",
            "pre-tool-use": "pre-tool-use",
            "post-tool-use": "post-tool-use",
            "pre-compact": "pre-compact",
            "subagent-start": "subagent-start",
            "subagent-stop": "subagent-stop",
            "notification": "notification",
        }

        # Codex state
        self._codex_session_mapping: dict[str, str] = {}
        self._codex_session_lock = __import__("threading").Lock()

    def get_llm_provider_for_feature(self, provider_name: str | None) -> "LLMProvider | None":
        """Get LLM provider by name from LLMService."""
        if self.llm_service and provider_name:
            try:
                return self.llm_service.get_provider(provider_name)
            except ValueError as e:
                logger.warning(f"Provider '{provider_name}' not available: {e}")
        if self.llm_service:
            try:
                return self.llm_service.get_default_provider()
            except ValueError:
                pass
        return None

    def get_hook_manager(self) -> "HookManager":
        """Get or create the HookManager instance."""
        if self._hook_manager is None:
            from gobby.hooks.hook_manager import HookManager

            self._hook_manager = HookManager(
                daemon_host="localhost",
                daemon_port=self.daemon_port,
                llm_service=self.llm_service,
                config=self.config,
            )
            logger.debug("HookManager initialized for MCP call_hook tool")
        return self._hook_manager

    async def status(self) -> dict[str, Any]:
        """Get current daemon status and health information."""
        from pathlib import Path
        from gobby.utils.status import format_status_message

        uptime_seconds = time.time() - self.start_time
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        uptime = f"{hours}h {minutes}m {seconds}s"

        mcp_servers_status = []
        for server_name, connection in self.mcp_manager.connections.items():
            mcp_servers_status.append(
                {
                    "name": server_name,
                    "state": connection.state.value,
                    "connected": connection.is_connected,
                    "transport": connection.config.transport,
                }
            )

        pid = os.getpid()
        pid_file = str(Path.home() / ".gobby" / "gobby.pid")
        log_files = str(Path.home() / ".gobby" / "logs")

        formatted_message = format_status_message(
            running=True,
            pid=pid,
            pid_file=pid_file,
            log_files=log_files,
            uptime=uptime,
            http_port=self.daemon_port,
            websocket_port=self.websocket_port,
        )

        return {
            "status": "running",
            "uptime": uptime,
            "uptime_seconds": int(uptime_seconds),
            "pid": pid,
            "port": self.daemon_port,
            "mcp_servers": mcp_servers_status,
            "mcp_server_count": len(mcp_servers_status),
            "formatted_message": formatted_message,
        }

    async def list_mcp_servers(self) -> dict[str, Any]:
        """List all configured MCP servers and their connection status."""
        servers = []
        for server_name, connection in self.mcp_manager.connections.items():
            server_info = {
                "name": server_name,
                "project_id": connection.config.project_id,
                "description": connection.config.description,
                "connected": connection.is_connected,
            }
            servers.append(server_info)

        return {"servers": servers}

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a tool on a connected MCP server."""
        if self.internal_manager.is_internal(server_name):
            registry = self.internal_manager.get_registry(server_name)
            if not registry:
                available = ", ".join(r.name for r in self.internal_manager.get_all_registries())
                return {
                    "success": False,
                    "server": server_name,
                    "error": f"Internal server '{server_name}' not found",
                    "available_internal_servers": available,
                }
            try:
                result = await registry.call(tool_name, arguments or {})
                return {"success": True, "result": result}
            except ValueError as e:
                return {
                    "success": False,
                    "server": server_name,
                    "tool": tool_name,
                    "error": str(e),
                    "error_type": "ValueError",
                }
            except Exception as e:
                logger.error(f"Failed to call internal tool {tool_name}: {e}")
                return {
                    "success": False,
                    "server": server_name,
                    "tool": tool_name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }

        try:
            result = await self.mcp_manager.call_tool(
                server_name, tool_name, arguments or {}, timeout=self.mcp_tool_timeout
            )
            return {"success": True, "result": result}
        except TimeoutError:
            logger.error(
                f"Tool call timed out after {self.mcp_tool_timeout}s: {server_name}.{tool_name}"
            )
            return {
                "success": False,
                "server": server_name,
                "tool": tool_name,
                "error": f"Tool call timed out after {self.mcp_tool_timeout} seconds",
                "error_type": "TimeoutError",
            }
        except Exception as e:
            logger.error(f"Failed to call {tool_name} on {server_name}: {e}")
            return {
                "success": False,
                "server": server_name,
                "tool": tool_name,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def read_mcp_resource(self, server_name: str, resource_uri: str) -> dict[str, Any]:
        """Read a resource from a downstream MCP server."""
        try:
            resource = await self.mcp_manager.read_resource(server_name, resource_uri)
            return {
                "success": True,
                "content": [item.model_dump() for item in resource.contents],
                "mime_type": resource.mimeType if hasattr(resource, "mimeType") else None,
            }
        except Exception as e:
            logger.error(f"Failed to read {resource_uri} from {server_name}: {e}")
            return {
                "success": False,
                "server": server_name,
                "uri": resource_uri,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def add_mcp_server(
        self,
        name: str,
        transport: str,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Add a new MCP server to the current project."""
        from gobby.mcp_proxy.actions import add_mcp_server as add_server_action
        from gobby.utils.project_init import initialize_project

        project_id = self.mcp_manager.project_id
        if not project_id:
            init_result = initialize_project()
            project_id = init_result.project_id
            self.mcp_manager.project_id = project_id

        return await add_server_action(
            mcp_manager=self.mcp_manager,
            name=name,
            transport=transport,
            project_id=project_id,
            url=url,
            headers=headers,
            command=command,
            args=args,
            env=env,
            enabled=enabled,
        )

    async def remove_mcp_server(self, name: str) -> dict[str, Any]:
        """Remove an MCP server from the current project."""
        from gobby.mcp_proxy.actions import remove_mcp_server as remove_server_action

        project_id = self.mcp_manager.project_id
        if not project_id:
            return {
                "success": False,
                "name": name,
                "error": "No project context - initialize a project first with init_project()",
            }

        return await remove_server_action(
            mcp_manager=self.mcp_manager,
            name=name,
            project_id=project_id,
        )

    async def import_mcp_server(
        self,
        from_project: str | None = None,
        servers: list[str] | None = None,
        github_url: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Import MCP servers from various sources."""
        from gobby.mcp_proxy.importer import MCPServerImporter
        from gobby.storage.database import LocalDatabase
        from gobby.utils.project_init import initialize_project

        project_id = self.mcp_manager.project_id
        if not project_id:
            init_result = initialize_project()
            project_id = init_result.project_id
            self.mcp_manager.project_id = project_id

        db = LocalDatabase()
        importer = MCPServerImporter(
            config=cast(Any, self.import_mcp_server_config),
            db=db,
            current_project_id=project_id,
            mcp_client_manager=self.mcp_manager,
        )

        if from_project is not None:
            return await importer.import_from_project(from_project, servers)

        if github_url is not None:
            return await importer.import_from_github(github_url)

        if query is not None:
            return await importer.import_from_query(query)

        return {
            "success": False,
            "error": "Must provide one of: from_project, github_url, or query",
        }

    async def list_tools(self, server: str | None = None) -> dict[str, Any]:
        """List tools from DOWNSTREAM/PROXIED MCP servers."""
        try:
            if server:
                if self.internal_manager.is_internal(server):
                    registry = self.internal_manager.get_registry(server)
                    if not registry:
                        available_internal = ", ".join(
                            r.name for r in self.internal_manager.get_all_registries()
                        )
                        return {
                            "success": False,
                            "error": f"Internal server '{server}' not found",
                            "available_internal_servers": available_internal,
                        }
                    return {"success": True, "tools": registry.list_tools()}

                server_config = next(
                    (s for s in self.mcp_manager.server_configs if s.name == server), None
                )

                if not server_config:
                    internal_names = [r.name for r in self.internal_manager.get_all_registries()]
                    downstream_names = [s.name for s in self.mcp_manager.server_configs]
                    available = ", ".join(internal_names + downstream_names)
                    return {
                        "success": False,
                        "error": f"Server '{server}' not found",
                        "available_servers": available,
                    }

                tools_list = []
                if server_config.tools:
                    for tool in server_config.tools:
                        tools_list.append(
                            {
                                "name": tool.get("name"),
                                "brief": tool.get("brief", "No description available"),
                            }
                        )

                return {"success": True, "tools": tools_list}
            else:
                servers_list = []
                for registry in self.internal_manager.get_all_registries():
                    servers_list.append({"name": registry.name, "tools": registry.list_tools()})

                for server_config in self.mcp_manager.server_configs:
                    tools_list = []
                    if server_config.tools:
                        for tool in server_config.tools:
                            tools_list.append(
                                {
                                    "name": tool.get("name"),
                                    "brief": tool.get("brief", "No description available"),
                                }
                            )

                    servers_list.append({"name": server_config.name, "tools": tools_list})

                return {"success": True, "servers": servers_list}

        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def get_tool_schema(self, server_name: str, tool_name: str) -> dict[str, Any]:
        """Get full schema (inputSchema) for a specific MCP tool."""
        try:
            if self.internal_manager.is_internal(server_name):
                registry = self.internal_manager.get_registry(server_name)
                if not registry:
                    available_internal = ", ".join(
                        r.name for r in self.internal_manager.get_all_registries()
                    )
                    return {
                        "success": False,
                        "error": f"Internal server '{server_name}' not found",
                        "available_internal_servers": available_internal,
                    }

                schema = registry.get_schema(tool_name)
                if not schema:
                    available_tools = [t["name"] for t in registry.list_tools()]
                    return {
                        "success": False,
                        "error": f"Tool '{tool_name}' not found on '{server_name}'",
                        "available_tools": available_tools,
                    }

                return {"success": True, "tool": schema}

            server_config = next(
                (s for s in self.mcp_manager.server_configs if s.name == server_name), None
            )

            if not server_config:
                internal_names = [r.name for r in self.internal_manager.get_all_registries()]
                downstream_names = [s.name for s in self.mcp_manager.server_configs]
                available = ", ".join(internal_names + downstream_names)
                return {
                    "success": False,
                    "error": f"Server '{server_name}' not found",
                    "available_servers": available,
                }

            if self.mcp_manager.mcp_db_manager is None:
                return {
                    "success": False,
                    "error": "Database manager not available",
                }

            cached_tools = self.mcp_manager.mcp_db_manager.get_cached_tools(
                server_name, project_id=server_config.project_id
            )
            tool = next((t for t in cached_tools if t.name == tool_name), None)

            if not tool:
                available_tools = [t.name for t in cached_tools]
                return {
                    "success": False,
                    "error": f"Tool '{tool_name}' not found on server '{server_name}'",
                    "available_tools": available_tools,
                }

            tool_schema = {
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.input_schema or {},
            }

            return {"success": True, "tool": tool_schema}

        except Exception as e:
            logger.error(f"Failed to get tool schema for {server_name}/{tool_name}: {e}")
            return {
                "success": False,
                "server": server_name,
                "tool_name": tool_name,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        context: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Execute code using Claude's code execution sandbox."""
        try:
            provider = self.get_llm_provider_for_feature(self.code_exec_provider)

            if not provider:
                return {
                    "success": False,
                    "error": f"Code execution provider '{self.code_exec_provider}' not found or not configured",
                }

            return cast(
                dict[str, Any],
                await provider.execute_code(
                    code=code,
                    language=language,
                    context=context,
                    timeout=timeout,
                    prompt_template=self.code_exec_prompt,
                ),
            )

        except Exception as e:
            logger.error(f"Code execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def process_large_dataset(
        self,
        data: list[dict[str, Any]] | dict[str, Any],
        operation: str,
        parameters: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Process large datasets using Claude's code execution."""
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                TextBlock,
                ToolResultBlock,
                UserMessage,
                query,
            )

            if isinstance(data, list):
                original_size = len(data)
            else:
                original_size = 1

            params_str = f"\n\nParameters: {json.dumps(parameters, indent=2)}" if parameters else ""

            preview_data = data[: self.code_exec_preview] if isinstance(data, list) else data

            prompt = f"""Process this dataset using Python code execution.

Operation: {operation}{params_str}

Dataset preview (first {self.code_exec_preview} items):
{json.dumps(preview_data, indent=2)}

Dataset size: {original_size} items

Write and execute Python code to perform the requested operation.
Return the processed data as a JSON-serializable result.

Requirements:
- Import any needed libraries (pandas, numpy, etc.)
- The full dataset is available in a variable called 'data'
- Return the final result as a Python object (list, dict, or primitive)
- Be efficient - we're processing {original_size} items"""

            options = ClaudeAgentOptions(
                system_prompt=f"""You are a data processing assistant with code execution capabilities.
You have access to a dataset with {original_size} items.
Execute Python code to process the data according to the user's operation.
The variable 'data' contains: {json.dumps(data[:2] if isinstance(data, list) else data)}
Use pandas, numpy, or standard Python as needed.
Always use code execution tools - never just describe what the code would do.""",
                max_turns=self.code_exec_max_turns,
                model=self.code_exec_model,
                allowed_tools=["code_execution"],
                permission_mode="bypassPermissions",
            )

            actual_timeout = timeout if timeout is not None else self.code_exec_timeout
            start_time_exec = time.time()

            async def _run_dataset_query() -> str:
                result_text = ""
                tool_results: list[str] = []
                async for message in query(prompt=prompt, options=options):
                    if isinstance(message, UserMessage):
                        for block in message.content:
                            if isinstance(block, ToolResultBlock):
                                tool_results.append(str(block.content))
                    elif isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                result_text += block.text
                if tool_results:
                    return "\n".join(tool_results)
                return result_text

            try:
                result_text: str = await asyncio.wait_for(
                    _run_dataset_query(), timeout=actual_timeout
                )
            except TimeoutError:
                return {
                    "success": False,
                    "error": f"Dataset processing timed out after {actual_timeout} seconds",
                    "error_type": "TimeoutError",
                    "timeout": actual_timeout,
                    "operation": operation,
                }

            execution_time = time.time() - start_time_exec

            try:
                processed_data = json.loads(result_text.strip())
            except json.JSONDecodeError:
                processed_data = result_text.strip()

            if isinstance(processed_data, list):
                processed_size = len(processed_data)
            elif isinstance(processed_data, dict):
                processed_size = len(processed_data)
            else:
                processed_size = 1

            reduction_pct = (
                round((1 - processed_size / original_size) * 100, 1) if original_size > 0 else 0
            )

            return {
                "success": True,
                "result": processed_data,
                "original_size": original_size,
                "processed_size": processed_size,
                "reduction_percent": reduction_pct,
                "execution_time": round(execution_time, 2),
            }

        except Exception as e:
            logger.error(f"Dataset processing failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "operation": operation,
            }

    async def recommend_tools(
        self, task_description: str, agent_id: str | None = None
    ) -> dict[str, Any]:
        """Get intelligent tool recommendations for a given task."""
        try:
            from claude_agent_sdk import ClaudeAgentOptions, query

            tools_by_server = {}
            for server_config in self.mcp_manager.server_configs:
                if server_config.tools:
                    tools_by_server[server_config.name] = [
                        {
                            "name": tool.get("name"),
                            "description": tool.get("description"),
                            "args": tool.get("args", {}),
                        }
                        for tool in server_config.tools
                    ]

            if not tools_by_server:
                return {
                    "success": False,
                    "error": "No MCP tools available. Please connect to MCP servers first.",
                }

            if agent_id:
                logger.debug(
                    f"Agent filtering requested (agent_id={agent_id}) but database "
                    "integration not yet implemented. Showing all tools."
                )

            tools_summary = []
            for server_name, tools in tools_by_server.items():
                tools_summary.append(f"\n**{server_name}**:")
                for tool in tools:
                    args_info = ""
                    if tool.get("args") and tool["args"].get("properties"):
                        required = tool["args"].get("required", [])
                        params: list[str] = []
                        for param_name, param_info in tool["args"]["properties"].items():
                            param_type = param_info.get("type", "any")
                            req_marker = "*" if param_name in required else ""
                            params.append(f"{param_name}{req_marker}: {param_type}")
                        args_info = f" ({', '.join(params)})"

                    tools_summary.append(
                        f"  - {tool['name']}{args_info}\n    {tool['description']}"
                    )

            prompt = f"""The user is trying to: {task_description}

Available MCP tools:
{"".join(tools_summary)}

Analyze the user's task and recommend which tool(s) would be most helpful.

Provide your response in this format:
1. A brief explanation of the recommended approach
2. Suggested tools in order of use, with:
   - Server and tool name
   - Why this tool is recommended
   - Suggested arguments (if applicable)

If multiple tools should be used together, explain the workflow.
If no tools are relevant, say so clearly."""

            provider = self.get_llm_provider_for_feature(self.recommend_tools_provider)

            recommendation_text = ""
            if provider and hasattr(provider, "recommend_tools"):
                try:
                    recommendation_text = await cast(Any, provider).recommend_tools(
                        task_description=task_description,
                        tools_summary="".join(tools_summary),
                        system_prompt=self.recommend_tools_prompt,
                    )
                except Exception as e:
                    logger.warning(f"LLMProvider.recommend_tools failed, falling back to SDK: {e}")
                    provider = None

            if not provider or not hasattr(provider, "recommend_tools"):
                options = ClaudeAgentOptions(
                    system_prompt=self.recommend_tools_prompt,
                    max_turns=1,
                    model=self.recommend_tools_model,
                    allowed_tools=[],
                    permission_mode="default",
                )

                async for message in query(prompt=prompt, options=options):
                    from claude_agent_sdk import AssistantMessage, TextBlock

                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                recommendation_text = block.text

            return {
                "success": True,
                "recommendation": recommendation_text.strip(),
                "available_servers": list(tools_by_server.keys()),
                "total_tools": sum(len(tools) for tools in tools_by_server.values()),
            }

        except Exception as e:
            logger.error(f"Failed to generate tool recommendations: {e}")
            return {
                "success": False,
                "task": task_description,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def call_hook(
        self,
        hook_type: str,
        params: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Trigger a session hook for non-Claude-Code CLIs."""
        try:
            normalized_hook_type = self.HOOK_TYPE_ALIASES.get(hook_type)
            if not normalized_hook_type:
                available = ", ".join(
                    sorted({k for k in self.HOOK_TYPE_ALIASES.keys() if "-" not in k})
                )
                return {
                    "success": False,
                    "error": f"Unknown hook type: {hook_type}",
                    "available_types": available,
                }

            input_data = dict(params) if params else {}

            if source:
                input_data["_cli_source"] = source

            hook_manager = self.get_hook_manager()

            original_source = None
            original_session_manager_source = None
            if source:
                original_source = cast(Any, hook_manager).SOURCE
                cast(Any, hook_manager).SOURCE = source
                if hasattr(hook_manager, "_session_manager"):
                    original_session_manager_source = cast(
                        Any, hook_manager
                    )._session_manager.source
                    cast(Any, hook_manager)._session_manager.source = source

            try:
                # Bypass health check
                with hook_manager._health_check_lock:
                    hook_manager._cached_daemon_is_ready = True
                    hook_manager._cached_daemon_status = "running"
                    hook_manager._cached_daemon_error = None

                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: cast(Any, hook_manager).execute(normalized_hook_type, input_data)
                )

                return {"success": True, "result": result}
            finally:
                if original_source is not None:
                    cast(Any, hook_manager).SOURCE = original_source
                if original_session_manager_source is not None:
                    if hasattr(hook_manager, "_session_manager"):
                        cast(
                            Any, hook_manager
                        )._session_manager.source = original_session_manager_source

        except Exception as e:
            logger.error(f"Failed to execute hook {hook_type}: {e}", exc_info=True)
            return {
                "success": False,
                "hook_type": hook_type,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def codex(
        self,
        prompt: str,
        thread_id: str | None = None,
        cwd: str | None = None,
        model: str | None = None,
        sandbox: str | None = None,
        approval_policy: str | None = None,
    ) -> dict[str, Any]:
        """Run Codex with automatic Gobby session tracking."""
        if not self.codex_client:
            return {"success": False, "error": "Codex client not available"}

        try:
            if not self.codex_client.is_connected:
                await self.codex_client.start()

            is_continuation = thread_id is not None

            if is_continuation:
                thread = await self.codex_client.resume_thread(thread_id)
            else:
                working_dir = cwd or os.getcwd()
                thread = await self.codex_client.start_thread(
                    cwd=working_dir,
                    model=model,
                    approval_policy=approval_policy,
                    sandbox=sandbox,
                )

                try:
                    hook_manager = self.get_hook_manager()
                    original_source = hook_manager.SOURCE
                    hook_manager.SOURCE = "codex"
                    if hasattr(hook_manager, "_session_manager"):
                        hook_manager._session_manager.source = "codex"

                    try:
                        from gobby.utils.machine_id import get_machine_id

                        machine_id = get_machine_id()

                        session_id, _ = hook_manager._session_manager.register_session(
                            external_id=thread.id,
                            machine_id=machine_id,
                            cwd=working_dir,
                        )

                        with self._codex_session_lock:
                            self._codex_session_mapping[thread.id] = session_id

                        logger.debug(
                            f"Registered Codex session: thread_id={thread.id} "
                            f"-> session_id={session_id}"
                        )

                    finally:
                        hook_manager.SOURCE = original_source
                        if hasattr(hook_manager, "_session_manager"):
                            hook_manager._session_manager.source = original_source

                except Exception as e:
                    logger.error(f"Failed to register Codex session: {e}", exc_info=True)

            response_text = ""
            items = []
            turn_id = None
            usage = None

            async for event in self.codex_client.run_turn(thread.id, prompt):
                event_type = event.get("type", "")

                if event_type == "turn/created":
                    turn_data = event.get("turn", {})
                    turn_id = turn_data.get("id")

                elif event_type == "item/completed":
                    item = event.get("item", {})
                    items.append(item)

                    if item.get("type") == "agent_message":
                        response_text = item.get("text", "")

                elif event_type == "turn/completed":
                    usage = event.get("usage")

            with self._codex_session_lock:
                gobby_session_id = self._codex_session_mapping.get(thread.id)

            return {
                "success": True,
                "thread_id": thread.id,
                "session_id": gobby_session_id,
                "turn_id": turn_id,
                "response": response_text,
                "items": items,
                "usage": usage,
                "is_continuation": is_continuation,
            }

        except Exception as e:
            logger.error(f"Codex call failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def codex_list_threads(
        self, limit: int = 25, cursor: str | None = None
    ) -> dict[str, Any]:
        """List available Codex conversation threads."""
        if not self.codex_client:
            return {"success": False, "error": "Codex client not available"}
        try:
            if not self.codex_client.is_connected:
                await self.codex_client.start()

            threads, next_cursor = await self.codex_client.list_threads(limit=limit, cursor=cursor)

            return {
                "success": True,
                "threads": [
                    {
                        "id": t.id,
                        "preview": t.preview,
                        "model_provider": t.model_provider,
                        "created_at": t.created_at,
                    }
                    for t in threads
                ],
                "next_cursor": next_cursor,
            }

        except Exception as e:
            logger.error(f"Failed to list Codex threads: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def codex_archive_thread(self, thread_id: str) -> dict[str, Any]:
        """Archive a Codex conversation thread."""
        if not self.codex_client:
            return {"success": False, "error": "Codex client not available"}
        try:
            if not self.codex_client.is_connected:
                await self.codex_client.start()

            await self.codex_client.archive_thread(thread_id)

            with self._codex_session_lock:
                self._codex_session_mapping.pop(thread_id, None)

            return {"success": True}

        except Exception as e:
            logger.error(f"Failed to archive Codex thread: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def get_daemon_config(self) -> dict[str, Any]:
        """Get daemon configuration."""
        return {
            "daemon_port": self.daemon_port,
            "mcp_servers": list(self.mcp_manager.connections.keys()),
        }

    # ==================== MEMORY TOOLS ====================

    async def remember(
        self,
        content: str,
        memory_type: str = "fact",
        importance: float = 0.5,
        project_id: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Store a new memory.

        Args:
            content: The memory content to store
            memory_type: Type of memory (fact, preference, etc)
            importance: Importance score (0.0-1.0)
            project_id: Optional project ID to associate with
            tags: Optional list of tags
        """
        if not self.memory_manager:
            return {"success": False, "error": "Memory manager not enabled"}

        try:
            memory = self.memory_manager.remember(
                content=content,
                memory_type=memory_type,
                importance=importance,
                project_id=project_id,
                tags=tags,
                source_type="mcp_tool",
            )
            return {
                "success": True,
                "memory": {
                    "id": memory.id,
                    "content": memory.content,
                    "type": memory.memory_type,
                    "importance": memory.importance,
                },
            }
        except Exception as e:
            logger.error(f"Failed to remember: {e}")
            return {"success": False, "error": str(e)}

    async def recall(
        self,
        query: str | None = None,
        project_id: str | None = None,
        limit: int = 10,
        min_importance: float | None = None,
    ) -> dict[str, Any]:
        """
        Recall memories.

        Args:
            query: Search query string
            project_id: Optional project to filter by
            limit: Maximum number of memories to return
            min_importance: Minimum importance threshold
        """
        if not self.memory_manager:
            return {"success": False, "error": "Memory manager not enabled"}

        try:
            memories = self.memory_manager.recall(
                query=query,
                project_id=project_id,
                limit=limit,
                min_importance=min_importance,
            )
            return {
                "success": True,
                "memories": [
                    {
                        "id": m.id,
                        "content": m.content,
                        "type": m.memory_type,
                        "importance": m.importance,
                        "created_at": m.created_at,
                        "similarity": getattr(m, "similarity", None),  # Might be added by search
                    }
                    for m in memories
                ],
            }
        except Exception as e:
            logger.error(f"Failed to recall: {e}")
            return {"success": False, "error": str(e)}

    async def forget(self, memory_id: str) -> dict[str, Any]:
        """
        Delete a memory by ID.

        Args:
            memory_id: The ID of the memory to delete
        """
        if not self.memory_manager:
            return {"success": False, "error": "Memory manager not enabled"}

        try:
            success = self.memory_manager.forget(memory_id)
            if success:
                return {"success": True, "message": f"Memory {memory_id} deleted"}
            else:
                return {"success": False, "error": f"Memory {memory_id} not found"}
        except Exception as e:
            logger.error(f"Failed to forget: {e}")
            return {"success": False, "error": str(e)}

    # ==================== SKILL TOOLS ====================

    async def learn_skill_from_session(self, session_id: str) -> dict[str, Any]:
        """
        Learn skills from a completed session.

        Args:
            session_id: The ID of the session to learn from
        """
        if not self.skill_learner or not self.session_manager:
            return {"success": False, "error": "Skill learner or session manager not enabled"}

        try:
            session = self.session_manager.get(session_id)
            if not session:
                return {"success": False, "error": f"Session {session_id} not found"}

            skills = await self.skill_learner.learn_from_session(session)
            return {
                "success": True,
                "skills": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "description": s.description,
                    }
                    for s in skills
                ],
                "count": len(skills),
            }
        except Exception as e:
            logger.error(f"Failed to learn skills: {e}")
            return {"success": False, "error": str(e)}

    async def list_skills(
        self,
        project_id: str | None = None,
        tag: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        List available skills.

        Args:
            project_id: Filter by project
            tag: Filter by tag
            limit: Max results
        """
        if not self.skill_learner:
            return {"success": False, "error": "Skill learner not enabled"}

        try:
            skills = self.skill_learner.storage.list_skills(
                project_id=project_id,
                tag=tag,
                limit=limit,
            )
            return {
                "success": True,
                "skills": [s.to_dict() for s in skills],
            }
        except Exception as e:
            logger.error(f"Failed to list skills: {e}")
            return {"success": False, "error": str(e)}

    async def get_skill(self, skill_id: str) -> dict[str, Any]:
        """
        Get details of a specific skill.

        Args:
            skill_id: The skill ID
        """
        if not self.skill_learner:
            return {"success": False, "error": "Skill learner not enabled"}

        try:
            skill = self.skill_learner.storage.get_skill(skill_id)
            if skill:
                return {"success": True, "skill": skill.to_dict()}
            else:
                return {"success": False, "error": "Skill not found"}
        except Exception as e:
            logger.error(f"Failed to get skill: {e}")
            return {"success": False, "error": str(e)}

    async def delete_skill(self, skill_id: str) -> dict[str, Any]:
        """
        Delete a skill.

        Args:
            skill_id: The skill ID
        """
        if not self.skill_learner:
            return {"success": False, "error": "Skill learner not enabled"}

        try:
            success = self.skill_learner.storage.delete_skill(skill_id)
            if success:
                return {"success": True, "message": f"Skill {skill_id} deleted"}
            else:
                return {"success": False, "error": "Skill not found"}
        except Exception as e:
            logger.error(f"Failed to delete skill: {e}")
            return {"success": False, "error": str(e)}

    async def match_skills(
        self,
        prompt: str,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Find applicable skills for a prompt.

        Args:
            prompt: User prompt/request
            project_id: Optional project context
        """
        if not self.skill_learner:
            return {"success": False, "error": "Skill learner not enabled"}

        try:
            skills = await self.skill_learner.match_skills(prompt, project_id)
            return {
                "success": True,
                "matches": [s.to_dict() for s in skills],
            }
        except Exception as e:
            logger.error(f"Failed to match skills: {e}")
            return {"success": False, "error": str(e)}


def create_mcp_server(
    mcp_manager: "MCPClientManager",
    daemon_port: int,
    start_time: float,
    config: "DaemonConfig | None" = None,
    llm_service: "LLMService | None" = None,
    codex_client: Any | None = None,
    task_manager: "LocalTaskManager | None" = None,
    task_sync_manager: "TaskSyncManager | None" = None,
    message_manager: "Any | None" = None,
    session_manager: "LocalSessionManager | None" = None,
    memory_manager: "MemoryManager | None" = None,
    skill_learner: "SkillLearner | None" = None,
) -> FastMCP:
    """
    Create FastMCP server with daemon control tools.
    """
    global _mcp_instance
    mcp = FastMCP(name="Gobby Daemon")
    _mcp_instance = mcp

    # Helper to get LLM provider for a feature - NOT used directly by tools anymore
    # but tools use self.get_llm_provider_for_feature

    websocket_port = 8766
    if config and hasattr(config, "websocket") and config.websocket:
        websocket_port = config.websocket.port

    # ===== INTERNAL TOOL REGISTRIES =====
    from gobby.mcp_proxy.tools.internal import InternalRegistryManager

    internal_manager = InternalRegistryManager()

    if message_manager:
        try:
            from gobby.mcp_proxy.tools.messages import create_messages_registry

            internal_manager.add_registry(create_messages_registry(message_manager))
        except Exception as e:
            logger.error(f"Failed to create messages registry: {e}")

    if task_manager and task_sync_manager:
        try:
            from gobby.mcp_proxy.tools.tasks import create_task_registry
            from gobby.tasks.expansion import TaskExpander
            from gobby.tasks.validation import TaskValidator

            task_expander = None
            task_validator = None

            if llm_service and config:
                try:
                    task_expander = TaskExpander(config.task_expansion, llm_service)
                    logger.info("Task expander enabled")
                except Exception as e:
                    logger.warning(f"Failed to create task expander: {e}")

                try:
                    task_validator = TaskValidator(config.task_validation, llm_service)
                    logger.info("Task validator enabled")
                except Exception as e:
                    logger.warning(f"Failed to create task validator: {e}")

            internal_manager.add_registry(
                create_task_registry(
                    task_manager,
                    task_sync_manager,
                    task_expander=task_expander,
                    task_validator=task_validator,
                )
            )
        except Exception as e:
            logger.error(f"Failed to create task registry: {e}")

    # Create tools handler
    tools = GobbyDaemonTools(
        mcp_manager=mcp_manager,
        daemon_port=daemon_port,
        websocket_port=websocket_port,
        start_time=start_time,
        internal_manager=internal_manager,
        config=config,
        llm_service=llm_service,
        codex_client=codex_client,
        session_manager=session_manager,
        memory_manager=memory_manager,
        skill_learner=skill_learner,
    )

    # Register tools
    mcp.add_tool(tools.status)
    mcp.add_tool(tools.list_mcp_servers)

    if tools.mcp_proxy_enabled:
        mcp.add_tool(tools.call_tool)
        mcp.add_tool(tools.read_mcp_resource)
        mcp.add_tool(tools.list_tools)
        mcp.add_tool(tools.get_tool_schema)

    mcp.add_tool(tools.add_mcp_server)
    mcp.add_tool(tools.remove_mcp_server)
    mcp.add_tool(tools.import_mcp_server)

    if tools.code_exec_enabled:
        mcp.add_tool(tools.execute_code)
        mcp.add_tool(tools.process_large_dataset)

    if tools.recommend_tools_enabled:
        mcp.add_tool(tools.recommend_tools)

    mcp.add_tool(tools.call_hook)

    if codex_client is not None:
        mcp.add_tool(tools.codex)
        mcp.add_tool(tools.codex_list_threads)
        mcp.add_tool(tools.codex_archive_thread)
        logger.debug("Codex integration tools registered")

    # Register Memory Tools
    if memory_manager:
        try:
            from gobby.mcp_proxy.tools.memory import create_memory_registry

            internal_manager.add_registry(create_memory_registry(memory_manager))
            logger.debug("Memory internal registry created")
        except Exception as e:
            logger.error(f"Failed to create memory registry: {e}")

    # Register Skill Tools
    if skill_learner:
        try:
            from gobby.mcp_proxy.tools.skills import create_skills_registry

            internal_manager.add_registry(
                create_skills_registry(
                    storage=skill_learner.storage,
                    learner=skill_learner,
                    session_manager=session_manager,
                )
            )
            logger.debug("Skills internal registry created")
        except Exception as e:
            logger.error(f"Failed to create skills registry: {e}")

    # Register resources
    mcp.add_resource(tools.get_daemon_config, "gobby://config")

    logger.debug("FastMCP server created with daemon control tools")
    return mcp
