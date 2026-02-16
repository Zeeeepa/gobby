"""Step execution handlers for pipeline workflows."""

import asyncio
import logging
import shlex
from typing import Any

logger = logging.getLogger(__name__)


async def execute_mcp_step(
    rendered_step: Any, context: dict[str, Any], tool_proxy_getter: Any | None
) -> Any:
    """Execute an MCP tool call step."""
    mcp_config = rendered_step.mcp

    logger.info(f"Executing MCP step: {mcp_config.server}:{mcp_config.tool}")

    if not tool_proxy_getter:
        raise RuntimeError(
            f"MCP step {rendered_step.id} requires tool_proxy_getter but none configured"
        )

    tool_proxy = tool_proxy_getter()
    if not tool_proxy:
        raise RuntimeError("tool_proxy_getter returned None")

    result = await tool_proxy.call_tool(
        mcp_config.server,
        mcp_config.tool,
        mcp_config.arguments or {},
    )

    # Convert MCP SDK CallToolResult to a serializable dict
    if hasattr(result, "content") and hasattr(result, "isError"):
        texts = []
        for item in result.content:
            if hasattr(item, "text"):
                texts.append(item.text)
        output = "\n".join(texts) if texts else ""
        if getattr(result, "isError", False):
            raise RuntimeError(
                f"MCP step {rendered_step.id} failed: "
                f"{mcp_config.server}:{mcp_config.tool} returned error: {output}"
            )
        return {"result": output}

    # Check for MCP-level failure (dict responses from internal tools)
    if isinstance(result, dict) and result.get("success") is False:
        error_msg = result.get("error", "Unknown MCP tool error")
        raise RuntimeError(
            f"MCP step {rendered_step.id} failed: "
            f"{mcp_config.server}:{mcp_config.tool} returned error: {error_msg}"
        )

    return result


async def execute_spawn_session_step(
    rendered_step: Any,
    context: dict[str, Any],
    project_id: str,
    spawner: Any | None,
    session_manager: Any | None,
) -> dict[str, Any]:
    """Execute a spawn_session step — spawn a CLI session via tmux."""
    config = rendered_step.spawn_session
    if not spawner:
        return {"error": "spawn_session requires a tmux spawner but none configured"}

    if not session_manager:
        return {"error": "spawn_session requires session_manager but none configured"}

    cli = config.get("cli", "claude")
    prompt = config.get("prompt")
    cwd = config.get("cwd")
    workflow_name = config.get("workflow_name")
    agent_depth = config.get("agent_depth", 1)

    # Create a gobby session record
    session = session_manager.create_session(
        platform=cli,
        project_id=project_id,
    )
    session_id = session.id if hasattr(session, "id") else str(session)

    try:
        result = spawner.spawn_agent(
            cli=cli,
            cwd=cwd or ".",
            session_id=session_id,
            parent_session_id="",
            agent_run_id=session_id,
            project_id=project_id,
            workflow_name=workflow_name,
            agent_depth=agent_depth,
            prompt=prompt,
        )
        return {
            "session_id": session_id,
            "tmux_session_name": getattr(result, "tmux_session_name", ""),
        }
    except (OSError, RuntimeError) as e:
        return {"error": f"Failed to spawn session: {e}"}


async def execute_activate_workflow_step(
    rendered_step: Any,
    context: dict[str, Any],
    loader: Any | None,
    session_manager: Any | None,
    db: Any,
) -> dict[str, Any]:
    """Execute an activate_workflow step — activate a workflow on a session."""
    config = rendered_step.activate_workflow
    if not loader:
        return {"error": "activate_workflow requires workflow loader but none configured"}

    workflow_name = config.get("name")
    session_id = config.get("session_id")
    variables = config.get("variables") or {}

    if not workflow_name:
        return {"error": "activate_workflow requires 'name' field"}
    if not session_id:
        return {"error": "activate_workflow requires 'session_id' field"}
    if not session_manager:
        return {"error": "activate_workflow requires session_manager but none configured"}

    try:
        from gobby.mcp_proxy.tools.workflows._lifecycle import activate_workflow
        from gobby.workflows.state_manager import WorkflowStateManager

        state_manager = WorkflowStateManager(db)

        result = await activate_workflow(
            loader=loader,
            state_manager=state_manager,
            session_manager=session_manager,
            db=db,
            name=workflow_name,
            session_id=session_id,
            variables=variables,
        )
        return result
    except (ImportError, ValueError, RuntimeError, OSError) as e:
        return {"error": f"Failed to activate workflow: {e}"}


async def execute_exec_step(command: str, context: dict[str, Any]) -> dict[str, Any]:
    """Execute a shell command step."""

    try:
        # TODO: This is where we should probably use a proper sandbox or execution service
        # For now, it matches the original implementation
        args = shlex.split(command)

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        return {
            "stdout": stdout.decode().strip(),
            "stderr": stderr.decode().strip(),
            "exit_code": proc.returncode,
        }
    except (OSError, ValueError) as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1,
        }


async def execute_prompt_step(
    prompt: str, context: dict[str, Any], llm_service: Any
) -> dict[str, Any]:
    """Execute an LLM prompt step."""
    if not llm_service:
        return {"error": "prompt step requires llm_service but none configured"}

    try:
        provider = llm_service.get_default_provider()
        response = await provider.generate_text(prompt)
        return {"response": response}
    except (OSError, RuntimeError, ValueError) as e:
        logger.error(f"LLM prompt execution failed: {e}", exc_info=True)
        return {
            "response": "",
            "error": str(e),
        }
