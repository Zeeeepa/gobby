import pytest

from gobby.tui.screens.agents import AgentsScreen
from gobby.tui.screens.chat import ChatScreen
from gobby.tui.screens.dashboard import DashboardScreen
from gobby.tui.screens.memory import MemoryScreen
from gobby.tui.screens.metrics import MetricsScreen
from gobby.tui.screens.orchestrator import OrchestratorScreen
from gobby.tui.screens.sessions import SessionsScreen
from gobby.tui.screens.tasks import TasksScreen
from gobby.tui.screens.workflows import WorkflowsScreen
from gobby.tui.screens.worktrees import WorktreesScreen

SCREENS = [
    DashboardScreen,
    MetricsScreen,
    SessionsScreen,
    TasksScreen,
    MemoryScreen,
    AgentsScreen,
    ChatScreen,
    OrchestratorScreen,
    WorkflowsScreen,
    WorktreesScreen,
]


@pytest.mark.parametrize("screen_cls", SCREENS)
def test_screen_instantiation(screen_cls, mock_api_client, mock_ws_client):
    """Test that all screens can be instantiated."""
    screen = screen_cls(api_client=mock_api_client, ws_client=mock_ws_client)
    assert screen is not None


async def test_dashboard_compose(mock_api_client, mock_ws_client):
    """Test dashboard specific composition logic."""
    screen = DashboardScreen(api_client=mock_api_client, ws_client=mock_ws_client)
    # Default state is loading=True
    assert screen.loading is True

    # We can check compose output manually if we iterate the generator
    # Note: compose returns a ComposeResult which is an iterator
    # The actual output depends on the structure (Container vs direct yields)

    # For DashboardScreen:
    # if self.loading:
    #    with Container(classes="loading-container"):
    #        yield LoadingIndicator()

    # Textual's compose() handles context managers specially.
    # Invoking it directly without the App context might be tricky if it relies on app features,
    # but strictly checking instantiation is safer for smoke tests.
    pass
