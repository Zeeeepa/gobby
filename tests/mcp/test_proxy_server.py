import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from gobby.config.app import DaemonConfig
from gobby.mcp_proxy.manager import MCPClientManager
from gobby.mcp_proxy.server import GobbyDaemonTools


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


@pytest.fixture(autouse=True)
def mock_claude_sdk():
    with patch.dict(sys.modules, {"claude_agent_sdk": module_mock}):
        yield


@pytest.fixture
def mock_mcp_manager():
    manager = MagicMock(spec=MCPClientManager)
    manager.connections = {}
    manager._connections = {}  # Private attr used by ServerManagementService
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
    service.get_provider.return_value = provider
    service.get_default_provider.return_value = provider
    # Mock generate directly on the service instance since RecommendationService calls it
    service.generate = AsyncMock(
        return_value='{"recommendations": [{"server": "s1", "tool": "t1", "reason": "r1"}]}'
    )
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
    mock_config.code_execution = mock_code_exec  # Direct property access

    # Mock recommend tools config
    mock_rec_tools = MagicMock()
    mock_rec_tools.enabled = True
    mock_rec_tools.provider = "claude"
    mock_rec_tools.prompt = "rec prompt"
    mock_config.get_recommend_tools_config.return_value = mock_rec_tools
    mock_config.recommend_tools = mock_rec_tools  # Direct property access

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
    assert result["running"] is True
    assert result["healthy"] is True
    assert result["http_port"] == 8080


@pytest.mark.asyncio
async def test_list_mcp_servers(daemon_tools, mock_mcp_manager):
    # Mock the health response that get_status uses
    mock_mcp_manager.get_server_health.return_value = {
        "server1": {"state": "connected", "health": "healthy"}
    }

    result = await daemon_tools.list_mcp_servers()
    assert len(result["servers"]) == 1
    assert result["servers"][0]["name"] == "server1"
    assert result["servers"][0]["connected"] is True


@pytest.mark.asyncio
async def test_call_tool_internal(daemon_tools):
    daemon_tools.internal_manager.is_internal.return_value = True
    mock_registry = MagicMock()
    mock_registry.call = AsyncMock(return_value={"tasks": [], "count": 0})
    daemon_tools.internal_manager.get_registry.return_value = mock_registry

    result = await daemon_tools.call_tool("gobby-tasks", "list_tasks", {})
    assert result == {"tasks": [], "count": 0}


@pytest.mark.asyncio
async def test_call_tool_downstream(daemon_tools, mock_mcp_manager):
    daemon_tools.internal_manager.is_internal.return_value = False
    mock_mcp_manager.call_tool.return_value = {"data": "downstream_result"}

    result = await daemon_tools.call_tool("server1", "tool1", {})
    assert result == {"data": "downstream_result"}


@pytest.mark.asyncio
async def test_read_mcp_resource(daemon_tools, mock_mcp_manager):
    mock_resource = MagicMock()
    mock_content = MagicMock()
    mock_content.model_dump.return_value = {"text": "content"}
    mock_resource.contents = [mock_content]
    mock_mcp_manager.read_resource.return_value = mock_resource

    result = await daemon_tools.read_mcp_resource("server1", "uri1")
    # read_resource returns raw result from mcp_manager
    assert result == mock_resource


@pytest.mark.asyncio
async def test_add_mcp_server(daemon_tools, mock_mcp_manager):
    # The ServerManagementService.add_server creates an MCPServerConfig and adds it
    # We need to mock add_server_config and connect_all on the mcp_manager
    mock_mcp_manager.add_server_config = MagicMock()
    mock_mcp_manager.connect_all = AsyncMock(return_value={"s1": True})

    result = await daemon_tools.add_mcp_server(
        name="s1", transport="http", url="http://localhost:8000"
    )
    assert result["success"] is True
    mock_mcp_manager.add_server_config.assert_called_once()


@pytest.mark.asyncio
async def test_remove_mcp_server(daemon_tools, mock_mcp_manager):
    # ServerManagementService.remove_server calls mcp_manager.remove_server_config
    mock_mcp_manager.remove_server_config = MagicMock()

    result = await daemon_tools.remove_mcp_server(name="s1")
    assert result["success"] is True
    mock_mcp_manager.remove_server_config.assert_called_once_with("s1")


@pytest.mark.asyncio
async def test_list_tools(daemon_tools, mock_mcp_manager):
    # Setup internal registry
    internal_registry = MagicMock()
    internal_registry.name = "internal1"
    internal_registry.list_tools.return_value = [{"name": "it1", "brief": "internal tool"}]
    daemon_tools.internal_manager.get_all_registries.return_value = [internal_registry]

    # Mock the external tools - mcp_manager.list_tools returns dict mapping server -> tools
    mock_mcp_manager.list_tools = AsyncMock(
        return_value={"downstream": [{"name": "dt1", "description": "downstream tool"}]}
    )

    result = await daemon_tools.list_tools()
    # The actual implementation returns {"servers": [...]} without "success" key
    assert "servers" in result
    assert len(result["servers"]) >= 2  # internal1 + downstream


@pytest.mark.asyncio
async def test_get_tool_schema(daemon_tools, mock_mcp_manager):
    # For internal tools, the internal_manager.get_registry().get_schema() is called
    # For external tools, mcp_manager.get_tool_input_schema() is called

    # Test with external tool - mock the mcp_manager method
    mock_mcp_manager.get_tool_input_schema = AsyncMock(
        return_value={
            "success": True,
            "server": "downstream",
            "tool": {"name": "dt1", "description": "desc", "inputSchema": {"type": "object"}},
        }
    )

    result = await daemon_tools.get_tool_schema("downstream", "dt1")
    assert result["success"] is True
    assert result["tool"]["name"] == "dt1"


@pytest.mark.asyncio
async def test_execute_code(daemon_tools):
    # CodeExecutionService requires a codex_client with execute method
    # The daemon_tools was created without a codex_client, so we need to mock it
    mock_codex_client = MagicMock()
    mock_codex_client.execute = AsyncMock(return_value={"success": True, "result": "42"})
    daemon_tools.code_execution._codex_client = mock_codex_client

    result = await daemon_tools.execute_code("print('hello')")
    assert result["success"] is True
    assert result["result"] == "42"


@pytest.mark.asyncio
async def test_recommend_tools(daemon_tools, mock_mcp_manager):
    # The RecommendationService.recommend_tools accesses mcp_manager._configs
    mock_mcp_manager._configs = {"server1": MagicMock()}

    result = await daemon_tools.recommend_tools("find logic")
    assert result["success"] is True
    # The actual implementation returns a stubbed recommendation
    assert "recommendation" in result


@pytest.mark.skip(reason="GobbyDaemonTools does not have call_hook method - removed in refactor")
@pytest.mark.asyncio
async def test_call_hook(daemon_tools):
    # GobbyDaemonTools no longer exposes call_hook - this functionality
    # is handled by the hook system directly, not through MCP tools
    pass


@pytest.mark.asyncio
async def test_process_large_dataset_mocked(daemon_tools):
    # The CodeExecutionService.process_dataset is currently stubbed
    # It returns {"success": True, "result": "Stubbed for refactor"}
    # We test that it returns a success response

    data = [{"id": 1}, {"id": 2}]
    result = await daemon_tools.process_large_dataset(data, "filter")

    # The stub always returns success
    assert result["success"] is True


@pytest.mark.skip(
    reason="GobbyDaemonTools does not have codex/codex_list_threads methods - removed in refactor"
)
@pytest.mark.asyncio
async def test_codex_tools(daemon_tools):
    # GobbyDaemonTools no longer exposes codex and codex_list_threads methods
    # Codex functionality is handled through CodeExecutionService which uses a codex_client
    # but exposes it through execute_code, not direct codex() calls
    pass
