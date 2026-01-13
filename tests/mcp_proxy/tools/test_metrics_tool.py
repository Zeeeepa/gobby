import pytest
from unittest.mock import MagicMock
from typing import cast
from gobby.mcp_proxy.tools.metrics import create_metrics_registry
from gobby.mcp_proxy.metrics import ToolMetricsManager


@pytest.fixture
def mock_metrics_manager():
    return MagicMock(spec=ToolMetricsManager)


@pytest.fixture
def metrics_tools(mock_metrics_manager):
    return create_metrics_registry(metrics_manager=mock_metrics_manager)


class TestMetricsTools:
    def test_get_tool_metrics(self, metrics_tools, mock_metrics_manager):
        tool = metrics_tools._tools["get_tool_metrics"]

        expected_metrics = {
            "gobby-tasks": {
                "create_task": {"call_count": 10, "success_rate": 0.9, "avg_latency_ms": 100}
            }
        }
        mock_metrics_manager.get_metrics.return_value = expected_metrics

        result = tool.func(project_id="test-proj")

        assert result["success"] is True
        assert result["metrics"] == expected_metrics
        mock_metrics_manager.get_metrics.assert_called_with(
            project_id="test-proj", server_name=None, tool_name=None
        )

    def test_get_tool_metrics_error(self, metrics_tools, mock_metrics_manager):
        tool = metrics_tools._tools["get_tool_metrics"]
        mock_metrics_manager.get_metrics.side_effect = Exception("DB error")

        result = tool.func()

        assert result["success"] is False
        assert "DB error" in result["error"]

    def test_get_top_tools(self, metrics_tools, mock_metrics_manager):
        tool = metrics_tools._tools["get_top_tools"]
        expected_tools = [{"name": "tool1", "call_count": 100}]
        mock_metrics_manager.get_top_tools.return_value = expected_tools

        result = tool.func(project_id="p1", limit=5, order_by="success_count")

        assert result["success"] is True
        assert result["tools"] == expected_tools
        assert result["count"] == 1
        mock_metrics_manager.get_top_tools.assert_called_with(
            project_id="p1", limit=5, order_by="success_count"
        )

    def test_get_failing_tools(self, metrics_tools, mock_metrics_manager):
        tool = metrics_tools._tools["get_failing_tools"]
        expected_tools = [{"name": "bad_tool", "failure_rate": 0.8}]
        mock_metrics_manager.get_failing_tools.return_value = expected_tools

        result = tool.func(project_id="p1", threshold=0.7)

        assert result["success"] is True
        assert result["tools"] == expected_tools
        assert result["threshold"] == 0.7
        mock_metrics_manager.get_failing_tools.assert_called_with(
            project_id="p1", threshold=0.7, limit=10
        )

    def test_get_tool_success_rate(self, metrics_tools, mock_metrics_manager):
        tool = metrics_tools._tools["get_tool_success_rate"]
        mock_metrics_manager.get_tool_success_rate.return_value = 0.95

        result = tool.func(server_name="srv", tool_name="tool", project_id="p1")

        assert result["success"] is True
        assert result["success_rate"] == 0.95
        mock_metrics_manager.get_tool_success_rate.assert_called_with(
            server_name="srv", tool_name="tool", project_id="p1"
        )

    def test_reset_metrics(self, metrics_tools, mock_metrics_manager):
        tool = metrics_tools._tools["reset_metrics"]
        mock_metrics_manager.reset_metrics.return_value = 5

        result = tool.func(project_id="p1", server_name="s1")

        assert result["success"] is True
        assert result["deleted_count"] == 5
        mock_metrics_manager.reset_metrics.assert_called_with(
            project_id="p1", server_name="s1", tool_name=None
        )

    def test_reset_tool_metrics(self, metrics_tools, mock_metrics_manager):
        tool = metrics_tools._tools["reset_tool_metrics"]
        mock_metrics_manager.reset_metrics.return_value = 2

        result = tool.func(server_name="s1", tool_name="t1")

        assert result["success"] is True
        assert result["deleted_count"] == 2
        mock_metrics_manager.reset_metrics.assert_called_with(server_name="s1", tool_name="t1")

    def test_cleanup_old_metrics(self, metrics_tools, mock_metrics_manager):
        tool = metrics_tools._tools["cleanup_old_metrics"]
        mock_metrics_manager.cleanup_old_metrics.return_value = 100

        result = tool.func(retention_days=30)

        assert result["success"] is True
        assert result["deleted_count"] == 100
        mock_metrics_manager.cleanup_old_metrics.assert_called_with(retention_days=30)

    def test_get_retention_stats(self, metrics_tools, mock_metrics_manager):
        tool = metrics_tools._tools["get_retention_stats"]
        expected_stats = {"total_rows": 1000, "oldest_entry": "2023-01-01"}
        mock_metrics_manager.get_retention_stats.return_value = expected_stats

        result = tool.func()

        assert result["success"] is True
        assert result["stats"] == expected_stats
        mock_metrics_manager.get_retention_stats.assert_called_once()
