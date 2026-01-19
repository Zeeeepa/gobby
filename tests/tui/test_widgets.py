import pytest
from gobby.tui.widgets.token_budget import TokenBudgetMeter
from gobby.tui.widgets.review_gate import ReviewGatePanel, ReviewItem
from gobby.tui.widgets.message_panel import InterAgentMessagePanel, AgentMessage
from gobby.tui.widgets.menu import MenuPanel, MenuItemWidget, MenuItem
from gobby.tui.widgets.conductor import HaikuDisplay, ModeIndicator
from gobby.tui.widgets.chat import ChatInput, ChatHistory, ChatMessage
from gobby.tui.widgets.task_tree import TaskTree


def test_token_budget_instantiation():
    widget = TokenBudgetMeter()
    assert widget is not None


def test_review_gate_instantiation():
    widget = ReviewGatePanel()
    assert widget is not None

    item = ReviewItem(task_data={"id": "1", "title": "Test Task"})
    assert item is not None


def test_message_panel_instantiation():
    widget = InterAgentMessagePanel()
    assert widget is not None

    msg_widget = AgentMessage(sender="User", content="Hello")
    assert msg_widget is not None


def test_menu_instantiation():
    widget = MenuPanel()
    assert widget is not None

    item = MenuItem("k", "Test Item", "test_screen")
    item_widget = MenuItemWidget(item=item)
    assert item_widget is not None


def test_conductor_instantiation():
    widget = HaikuDisplay()
    assert widget is not None
    widget2 = ModeIndicator()
    assert widget2 is not None


def test_chat_widgets_instantiation():
    widget = ChatInput()
    assert widget is not None
    widget2 = ChatHistory()
    assert widget2 is not None

    widget3 = ChatMessage(sender="User", content="Hello")
    assert widget3 is not None


def test_task_tree_instantiation():
    widget = TaskTree()
    assert widget is not None
