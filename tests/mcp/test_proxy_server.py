import pytest
from unittest.mock import MagicMock, AsyncMock, patch, Mock
import sys
from gobby.mcp_proxy.server import GobbyDaemonTools
from gobby.mcp_proxy.manager import MCPClientManager
from gobby.config.app import DaemonConfig


# Define dummy classes for mocking imports effectively
class AssistantMessage:
    def __init__(self, content):
        self.content = content


class UserMessage:
    def __init__(self, content):
        self.content = content


class TextBlock:
    def __init__(self, text):
        self.text = text


class ToolResultBlock:
    def __init__(self, content):
        self.content = content


class ClaudeAgentOptions:
    def __init__(self, **kwargs):
        pass


async def mock_query_gen(*args, **kwargs):
    pass


# Mock claude_agent_sdk locally for tests
module_mock = Mock()
module_mock.AssistantMessage = AssistantMessage
module_mock.UserMessage = UserMessage
module_mock.TextBlock = TextBlock
module_mock.ToolResultBlock = ToolResultBlock
module_mock.ClaudeAgentOptions = ClaudeAgentOptions
module_mock.query = mock_query_gen
sys.modules["claude_agent_sdk"] = module_mock


@pytest.fixture
def mock_mcp_manager():
    manager = MagicMock(spec=MCPClientManager)
    manager.connections = {}
    manager.project_id = "test-project-id"
    manager.call_tool = AsyncMock()
    manager.read_resource = AsyncMock()

    mock_config = MagicMock()
    mock_config.name = "downstream"
    mock_config.project_id = "p1"
    mock_config.tools = [{"name": "dt1", "brief": "desc"}]
    manager.server_configs = [mock_config]

    manager.mcp_db_manager = MagicMock()
    manager.mcp_db_manager.get_cached_tools.return_value = []

    return manager


@pytest.fixture
def mock_llm_service():
    service = MagicMock()
    provider = MagicMock()
    provider.execute_code = AsyncMock(return_value={"success": True, "result": "42"})
    provider.recommend_tools = AsyncMock(return_value="Use tool X")
    service.get_provider.return_value = provider
    service.get_default_provider.return_value = provider
    return service


@pytest.fixture
def daemon_tools(mock_mcp_manager, mock_llm_service):
    internal_manager = MagicMock()
    internal_manager.is_internal.return_value = False

    # Mock config to return mcp_proxy config
    mock_config = MagicMock(spec=DaemonConfig)
    mock_proxy_config = MagicMock()
    mock_proxy_config.enabled = True
    mock_proxy_config.tool_timeout = 60.0
    mock_config.get_mcp_client_proxy_config.return_value = mock_proxy_config

    # Mock code execution config
    mock_code_exec = MagicMock()
    mock_code_exec.enabled = True
    mock_code_exec.provider = "claude"
    mock_code_exec.prompt = "exec prompt"
    # IMPORTANT: Set integer values for these fields to avoid TypeError in comparisons
    mock_code_exec.default_timeout = 30
    mock_code_exec.max_dataset_preview = 3
    mock_code_exec.max_turns = 5
    mock_config.get_code_execution_config.return_value = mock_code_exec

    # Mock recommend tools config
    mock_rec_tools = MagicMock()
    mock_rec_tools.enabled = True
    mock_rec_tools.provider = "claude"
    mock_rec_tools.prompt = "rec prompt"
    mock_config.get_recommend_tools_config.return_value = mock_rec_tools

    tools = GobbyDaemonTools(
        mcp_manager=mock_mcp_manager,
        daemon_port=8080,
        websocket_port=8766,
        start_time=1000.0,
        internal_manager=internal_manager,
        config=mock_config,
        llm_service=mock_llm_service,
    )
    return tools


@pytest.mark.asyncio
async def test_status_tool(daemon_tools):
    result = await daemon_tools.status()
    assert result["status"] == "running"
    assert "uptime" in result
    assert result["port"] == 8080


@pytest.mark.asyncio
async def test_list_mcp_servers(daemon_tools):
    mock_conn = MagicMock()
    mock_conn.config.project_id = "p1"
    mock_conn.config.description = "desc"
    mock_conn.is_connected = True
    daemon_tools.mcp_manager.connections = {"server1": mock_conn}

    result = await daemon_tools.list_mcp_servers()
    assert len(result["servers"]) == 1
    assert result["servers"][0]["name"] == "server1"
    assert result["servers"][0]["connected"] is True


@pytest.mark.asyncio
async def test_call_tool_internal(daemon_tools):
    daemon_tools.internal_manager.is_internal.return_value = True
    mock_registry = MagicMock()
    mock_registry.call = AsyncMock(return_value="internal_result")
    daemon_tools.internal_manager.get_registry.return_value = mock_registry

    result = await daemon_tools.call_tool("gobby-tasks", "list_tasks", {})
    assert result["success"] is True
    assert result["result"] == "internal_result"


@pytest.mark.asyncio
async def test_call_tool_downstream(daemon_tools):
    daemon_tools.internal_manager.is_internal.return_value = False
    daemon_tools.mcp_manager.call_tool.return_value = "downstream_result"

    result = await daemon_tools.call_tool("server1", "tool1", {})
    assert result["success"] is True
    assert result["result"] == "downstream_result"


@pytest.mark.asyncio
async def test_read_mcp_resource(daemon_tools):
    mock_resource = MagicMock()
    mock_content = MagicMock()
    mock_content.model_dump.return_value = {"text": "content"}
    mock_resource.contents = [mock_content]
    daemon_tools.mcp_manager.read_resource.return_value = mock_resource

    result = await daemon_tools.read_mcp_resource("server1", "uri1")
    assert result["success"] is True
    assert result["content"] == [{"text": "content"}]


@patch("gobby.mcp_proxy.actions.add_mcp_server", new_callable=AsyncMock)
@patch("gobby.utils.project_init.initialize_project")
@pytest.mark.asyncio
async def test_add_mcp_server(mock_init, mock_add_action, daemon_tools):
    mock_init.return_value.project_id = "new-project-id"
    daemon_tools.mcp_manager.project_id = None
    mock_add_action.return_value = {"success": True}

    result = await daemon_tools.add_mcp_server(name="s1", transport="stdio")
    assert result["success"] is True
    assert daemon_tools.mcp_manager.project_id == "new-project-id"
    mock_add_action.assert_called_once()


@patch("gobby.mcp_proxy.actions.remove_mcp_server", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_remove_mcp_server(mock_remove_action, daemon_tools):
    mock_remove_action.return_value = {"success": True}
    result = await daemon_tools.remove_mcp_server(name="s1")
    assert result["success"] is True
    mock_remove_action.assert_called_once()


@pytest.mark.asyncio
async def test_list_tools(daemon_tools):
    internal_registry = MagicMock()
    internal_registry.name = "internal1"
    internal_registry.list_tools.return_value = [{"name": "it1"}]
    daemon_tools.internal_manager.get_all_registries.return_value = [internal_registry]

    result = await daemon_tools.list_tools()
    assert result["success"] is True
    assert len(result["servers"]) >= 2


@pytest.mark.asyncio
async def test_get_tool_schema(daemon_tools):
    mock_tool = MagicMock()
    mock_tool.name = "dt1"
    mock_tool.description = "desc"
    mock_tool.input_schema = {"type": "object"}
    daemon_tools.mcp_manager.mcp_db_manager.get_cached_tools.return_value = [mock_tool]

    result = await daemon_tools.get_tool_schema("downstream", "dt1")
    assert result["success"] is True
    assert result["tool"]["name"] == "dt1"


@pytest.mark.asyncio
async def test_execute_code(daemon_tools, mock_llm_service):
    result = await daemon_tools.execute_code("print('hello')")
    assert result["success"] is True
    assert result["result"] == "42"


@pytest.mark.asyncio
async def test_recommend_tools(daemon_tools, mock_llm_service):
    result = await daemon_tools.recommend_tools("find logic")
    assert result["success"] is True
    assert result["recommendation"] == "Use tool X"


@patch("gobby.mcp_proxy.server.GobbyDaemonTools.get_hook_manager")
@pytest.mark.asyncio
async def test_call_hook(mock_get_hook_manager, daemon_tools):
    mock_hook_manager = MagicMock()
    mock_hook_manager.execute.return_value = {"status": "ok"}
    mock_get_hook_manager.return_value = mock_hook_manager

    result = await daemon_tools.call_hook("SessionStart", {"session_id": "123"})
    assert result["success"] is True
    assert result["result"] == {"status": "ok"}


@pytest.mark.asyncio
async def test_process_large_dataset_mocked(daemon_tools):
    # Patch module_mock.query directly
    async def async_gen(*args, **kwargs):
        msg = AssistantMessage(content=[TextBlock(text='{"processed": true}')])
        yield msg

    module_mock.query = async_gen

    data = [{"id": 1}, {"id": 2}]
    # max_dataset_preview is int now, so slice works and f-string works
    result = await daemon_tools.process_large_dataset(data, "filter")

    assert result["success"] is True, (
        f"Failed: {result.get('error')} type: {result.get('error_type')}"
    )
    assert result["result"] == {"processed": True}
    assert result["original_size"] == 2


@patch("gobby.utils.machine_id.get_machine_id")
@pytest.mark.asyncio
async def test_codex_tools(mock_get_id, daemon_tools):
    mock_get_id.return_value = "machine-id"
    mock_codex = MagicMock()
    mock_codex.is_connected = False
    mock_codex.start = AsyncMock()
    mock_thread = MagicMock()
    mock_thread.id = "thread-123"
    mock_codex.start_thread = AsyncMock(return_value=mock_thread)

    async def run_turn_gen(*args, **kwargs):
        yield {"type": "item/completed", "item": {"type": "agent_message", "text": "response"}}

    mock_codex.run_turn.side_effect = run_turn_gen

    daemon_tools.codex_client = mock_codex

    result = await daemon_tools.codex("prompt")
    assert result["success"] is True
    assert result["response"] == "response"

    mock_codex.list_threads = AsyncMock(return_value=([], None))
    result = await daemon_tools.codex_list_threads()
    assert result["success"] is True
