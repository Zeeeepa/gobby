"""Tests for gobby.conductor.alerts module.

Tests for the AlertDispatcher class that:
- Dispatches alerts with different priorities (info, normal, urgent, critical)
- Logs all alerts
- Uses callme.initiate_call for critical alerts when configured
"""

from unittest.mock import MagicMock, patch


class TestAlertDispatcherPriorities:
    """Tests for alert priority handling."""

    def test_dispatch_info_alert(self):
        """AlertDispatcher.dispatch() logs info alerts."""
        from gobby.conductor.alerts import AlertDispatcher

        dispatcher = AlertDispatcher()

        with patch.object(dispatcher, "_logger") as mock_logger:
            result = dispatcher.dispatch(
                priority="info",
                message="Test info alert",
            )

        assert result["success"] is True
        assert result["priority"] == "info"
        mock_logger.info.assert_called_once()

    def test_dispatch_normal_alert(self):
        """AlertDispatcher.dispatch() logs normal alerts."""
        from gobby.conductor.alerts import AlertDispatcher

        dispatcher = AlertDispatcher()

        with patch.object(dispatcher, "_logger") as mock_logger:
            result = dispatcher.dispatch(
                priority="normal",
                message="Test normal alert",
            )

        assert result["success"] is True
        assert result["priority"] == "normal"
        mock_logger.info.assert_called_once()

    def test_dispatch_urgent_alert(self):
        """AlertDispatcher.dispatch() logs urgent alerts as warnings."""
        from gobby.conductor.alerts import AlertDispatcher

        dispatcher = AlertDispatcher()

        with patch.object(dispatcher, "_logger") as mock_logger:
            result = dispatcher.dispatch(
                priority="urgent",
                message="Test urgent alert",
            )

        assert result["success"] is True
        assert result["priority"] == "urgent"
        mock_logger.warning.assert_called_once()

    def test_dispatch_critical_alert(self):
        """AlertDispatcher.dispatch() logs critical alerts as errors."""
        from gobby.conductor.alerts import AlertDispatcher

        dispatcher = AlertDispatcher()

        with patch.object(dispatcher, "_logger") as mock_logger:
            result = dispatcher.dispatch(
                priority="critical",
                message="Test critical alert",
            )

        assert result["success"] is True
        assert result["priority"] == "critical"
        mock_logger.error.assert_called_once()


class TestAlertDispatcherCallme:
    """Tests for callme integration."""

    def test_critical_alert_calls_callme_when_configured(self):
        """Critical alerts trigger callme.initiate_call when configured."""
        from gobby.conductor.alerts import AlertDispatcher

        mock_callme = MagicMock()
        mock_callme.initiate_call.return_value = {"success": True, "call_id": "call-123"}

        dispatcher = AlertDispatcher(callme_client=mock_callme)

        result = dispatcher.dispatch(
            priority="critical",
            message="Critical system failure",
        )

        assert result["success"] is True
        assert result["callme_triggered"] is True
        mock_callme.initiate_call.assert_called_once()

    def test_critical_alert_without_callme(self):
        """Critical alerts work without callme configured."""
        from gobby.conductor.alerts import AlertDispatcher

        dispatcher = AlertDispatcher()  # No callme_client

        result = dispatcher.dispatch(
            priority="critical",
            message="Critical system failure",
        )

        assert result["success"] is True
        assert result.get("callme_triggered") is False

    def test_non_critical_alerts_skip_callme(self):
        """Non-critical alerts do not trigger callme."""
        from gobby.conductor.alerts import AlertDispatcher

        mock_callme = MagicMock()
        dispatcher = AlertDispatcher(callme_client=mock_callme)

        for priority in ["info", "normal", "urgent"]:
            result = dispatcher.dispatch(
                priority=priority,
                message=f"Test {priority} alert",
            )

            assert result.get("callme_triggered", False) is False

        mock_callme.initiate_call.assert_not_called()

    def test_callme_failure_does_not_fail_dispatch(self):
        """Callme failure doesn't prevent alert dispatch."""
        from gobby.conductor.alerts import AlertDispatcher

        mock_callme = MagicMock()
        mock_callme.initiate_call.side_effect = Exception("Callme unavailable")

        dispatcher = AlertDispatcher(callme_client=mock_callme)

        result = dispatcher.dispatch(
            priority="critical",
            message="Critical alert",
        )

        # Alert should still succeed, just callme failed
        assert result["success"] is True
        assert result.get("callme_error") is not None


class TestAlertDispatcherContext:
    """Tests for alert context."""

    def test_dispatch_with_context(self):
        """AlertDispatcher.dispatch() accepts context dict."""
        from gobby.conductor.alerts import AlertDispatcher

        dispatcher = AlertDispatcher()

        result = dispatcher.dispatch(
            priority="urgent",
            message="Task stuck",
            context={"task_id": "task-123", "hours_stuck": 5},
        )

        assert result["success"] is True
        assert result.get("context") == {"task_id": "task-123", "hours_stuck": 5}

    def test_dispatch_with_source(self):
        """AlertDispatcher.dispatch() accepts source identifier."""
        from gobby.conductor.alerts import AlertDispatcher

        dispatcher = AlertDispatcher()

        result = dispatcher.dispatch(
            priority="info",
            message="Health check passed",
            source="TaskMonitor",
        )

        assert result["success"] is True
        assert result.get("source") == "TaskMonitor"


class TestAlertDispatcherHistory:
    """Tests for alert history."""

    def test_dispatch_records_alert(self):
        """AlertDispatcher tracks dispatched alerts."""
        from gobby.conductor.alerts import AlertDispatcher

        dispatcher = AlertDispatcher()

        dispatcher.dispatch(priority="info", message="Alert 1")
        dispatcher.dispatch(priority="urgent", message="Alert 2")

        history = dispatcher.get_history(limit=10)
        assert len(history) == 2
        assert history[0]["message"] == "Alert 1"
        assert history[1]["message"] == "Alert 2"

    def test_history_limit(self):
        """Alert history respects limit parameter."""
        from gobby.conductor.alerts import AlertDispatcher

        dispatcher = AlertDispatcher()

        for i in range(5):
            dispatcher.dispatch(priority="info", message=f"Alert {i}")

        history = dispatcher.get_history(limit=2)
        assert len(history) == 2

    def test_clear_history(self):
        """AlertDispatcher.clear_history() removes all history."""
        from gobby.conductor.alerts import AlertDispatcher

        dispatcher = AlertDispatcher()

        dispatcher.dispatch(priority="info", message="Alert 1")
        dispatcher.clear_history()

        history = dispatcher.get_history(limit=10)
        assert len(history) == 0
