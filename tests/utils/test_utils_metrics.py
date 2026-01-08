"""Comprehensive tests for the metrics collection module."""

import time
from unittest.mock import MagicMock, patch

import psutil
import pytest

from gobby.utils.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsCollector,
    _metrics_collector,
    get_metrics_collector,
)


class TestCounter:
    """Tests for Counter dataclass."""

    def test_counter_initialization_default_values(self):
        """Test counter initializes with default values."""
        counter = Counter(name="test_counter", help_text="A test counter")
        assert counter.name == "test_counter"
        assert counter.help_text == "A test counter"
        assert counter.value == 0
        assert counter.labels == {}

    def test_counter_initialization_with_labels(self):
        """Test counter initializes with custom labels."""
        labels = {"method": "GET", "status": "200"}
        counter = Counter(name="http_requests", help_text="HTTP requests", labels=labels)
        assert counter.labels == labels

    def test_counter_inc_default_amount(self):
        """Test incrementing counter by default amount of 1."""
        counter = Counter(name="test", help_text="test")
        counter.inc()
        assert counter.value == 1

    def test_counter_inc_custom_amount(self):
        """Test incrementing counter by custom amount."""
        counter = Counter(name="test", help_text="test")
        counter.inc(5)
        assert counter.value == 5

    def test_counter_inc_multiple_times(self):
        """Test incrementing counter multiple times accumulates."""
        counter = Counter(name="test", help_text="test")
        counter.inc(3)
        counter.inc(2)
        counter.inc()
        assert counter.value == 6


class TestGauge:
    """Tests for Gauge dataclass."""

    def test_gauge_initialization_default_values(self):
        """Test gauge initializes with default values."""
        gauge = Gauge(name="test_gauge", help_text="A test gauge")
        assert gauge.name == "test_gauge"
        assert gauge.help_text == "A test gauge"
        assert gauge.value == 0.0
        assert gauge.labels == {}

    def test_gauge_initialization_with_labels(self):
        """Test gauge initializes with custom labels."""
        labels = {"host": "localhost"}
        gauge = Gauge(name="connections", help_text="Active connections", labels=labels)
        assert gauge.labels == labels

    def test_gauge_set(self):
        """Test setting gauge value."""
        gauge = Gauge(name="test", help_text="test")
        gauge.set(42.5)
        assert gauge.value == 42.5

    def test_gauge_set_overwrites_previous(self):
        """Test setting gauge overwrites previous value."""
        gauge = Gauge(name="test", help_text="test")
        gauge.set(10.0)
        gauge.set(20.0)
        assert gauge.value == 20.0

    def test_gauge_inc_default_amount(self):
        """Test incrementing gauge by default amount of 1.0."""
        gauge = Gauge(name="test", help_text="test")
        gauge.inc()
        assert gauge.value == 1.0

    def test_gauge_inc_custom_amount(self):
        """Test incrementing gauge by custom amount."""
        gauge = Gauge(name="test", help_text="test")
        gauge.inc(5.5)
        assert gauge.value == 5.5

    def test_gauge_dec_default_amount(self):
        """Test decrementing gauge by default amount of 1.0."""
        gauge = Gauge(name="test", help_text="test")
        gauge.set(10.0)
        gauge.dec()
        assert gauge.value == 9.0

    def test_gauge_dec_custom_amount(self):
        """Test decrementing gauge by custom amount."""
        gauge = Gauge(name="test", help_text="test")
        gauge.set(10.0)
        gauge.dec(3.5)
        assert gauge.value == 6.5

    def test_gauge_can_go_negative(self):
        """Test gauge can go to negative values."""
        gauge = Gauge(name="test", help_text="test")
        gauge.dec(5.0)
        assert gauge.value == -5.0


class TestHistogram:
    """Tests for Histogram dataclass."""

    def test_histogram_initialization_default_buckets(self):
        """Test histogram initializes with default buckets."""
        histogram = Histogram(name="test_histogram", help_text="A test histogram")
        assert histogram.name == "test_histogram"
        assert histogram.help_text == "A test histogram"
        assert histogram.sum == 0.0
        assert histogram.count == 0
        assert histogram.labels == {}
        expected_buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        assert histogram.buckets == expected_buckets

    def test_histogram_initialization_custom_buckets(self):
        """Test histogram initializes with custom buckets."""
        custom_buckets = [0.1, 0.5, 1.0, 5.0]
        histogram = Histogram(
            name="latency", help_text="Request latency", buckets=custom_buckets
        )
        assert histogram.buckets == custom_buckets

    def test_histogram_post_init_initializes_bucket_counts(self):
        """Test __post_init__ initializes bucket counts to zero."""
        histogram = Histogram(name="test", help_text="test")
        for bucket in histogram.buckets:
            assert histogram.bucket_counts[bucket] == 0

    def test_histogram_observe_single_value(self):
        """Test observing a single value in histogram."""
        histogram = Histogram(name="test", help_text="test")
        histogram.observe(0.5)
        assert histogram.count == 1
        assert histogram.sum == 0.5

    def test_histogram_observe_multiple_values(self):
        """Test observing multiple values accumulates correctly."""
        histogram = Histogram(name="test", help_text="test")
        histogram.observe(0.1)
        histogram.observe(0.2)
        histogram.observe(0.3)
        assert histogram.count == 3
        assert histogram.sum == pytest.approx(0.6)

    def test_histogram_observe_updates_bucket_counts(self):
        """Test observing values updates appropriate bucket counts."""
        custom_buckets = [0.1, 0.5, 1.0]
        histogram = Histogram(name="test", help_text="test", buckets=custom_buckets)

        # Observe value that fits in first bucket
        histogram.observe(0.05)
        assert histogram.bucket_counts[0.1] == 1
        assert histogram.bucket_counts[0.5] == 1
        assert histogram.bucket_counts[1.0] == 1

        # Observe value that fits in second bucket but not first
        histogram.observe(0.3)
        assert histogram.bucket_counts[0.1] == 1
        assert histogram.bucket_counts[0.5] == 2
        assert histogram.bucket_counts[1.0] == 2

        # Observe value that only fits in last bucket
        histogram.observe(0.8)
        assert histogram.bucket_counts[0.1] == 1
        assert histogram.bucket_counts[0.5] == 2
        assert histogram.bucket_counts[1.0] == 3

    def test_histogram_observe_value_exceeds_all_buckets(self):
        """Test observing value larger than all buckets."""
        custom_buckets = [0.1, 0.5, 1.0]
        histogram = Histogram(name="test", help_text="test", buckets=custom_buckets)
        histogram.observe(5.0)
        # Value exceeds all buckets, so no bucket counts should be incremented
        assert histogram.bucket_counts[0.1] == 0
        assert histogram.bucket_counts[0.5] == 0
        assert histogram.bucket_counts[1.0] == 0
        # But sum and count should still update
        assert histogram.count == 1
        assert histogram.sum == 5.0

    def test_histogram_observe_value_exactly_on_bucket_boundary(self):
        """Test observing value exactly on bucket boundary."""
        custom_buckets = [0.5, 1.0]
        histogram = Histogram(name="test", help_text="test", buckets=custom_buckets)
        histogram.observe(0.5)
        # Value equals bucket boundary, should be counted in that bucket
        assert histogram.bucket_counts[0.5] == 1
        assert histogram.bucket_counts[1.0] == 1


class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    @pytest.fixture
    def collector(self):
        """Create a fresh MetricsCollector for each test."""
        return MetricsCollector()

    def test_initialization_creates_standard_metrics(self, collector):
        """Test that initialization creates all standard metrics."""
        metrics = collector.get_all_metrics()

        # Check counters exist
        expected_counters = [
            "http_requests_total",
            "http_requests_errors_total",
            "session_registrations_total",
            "memory_saves_total",
            "memory_saves_succeeded_total",
            "memory_saves_failed_total",
            "context_restores_total",
            "context_restores_succeeded_total",
            "context_restores_failed_total",
            "mcp_calls_total",
            "mcp_calls_succeeded_total",
            "mcp_calls_failed_total",
            "mcp_tool_calls_total",
            "mcp_tool_calls_succeeded_total",
            "mcp_tool_calls_failed_total",
            "background_tasks_total",
            "background_tasks_completed_total",
            "background_tasks_failed_total",
            "hooks_total",
            "hooks_succeeded_total",
            "hooks_failed_total",
        ]
        for counter_name in expected_counters:
            assert counter_name in metrics["counters"], f"Missing counter: {counter_name}"

        # Check gauges exist
        expected_gauges = [
            "mcp_active_connections",
            "background_tasks_active",
            "daemon_uptime_seconds",
            "daemon_memory_usage_bytes",
            "daemon_cpu_percent",
        ]
        for gauge_name in expected_gauges:
            assert gauge_name in metrics["gauges"], f"Missing gauge: {gauge_name}"

        # Check histograms exist
        expected_histograms = [
            "http_request_duration_seconds",
            "memory_save_duration_seconds",
            "context_restore_duration_seconds",
            "mcp_call_duration_seconds",
        ]
        for histogram_name in expected_histograms:
            assert histogram_name in metrics["histograms"], f"Missing histogram: {histogram_name}"

    def test_register_counter_new(self, collector):
        """Test registering a new counter."""
        counter = collector.register_counter("new_counter", "A new counter")
        assert counter.name == "new_counter"
        assert counter.help_text == "A new counter"
        assert counter.value == 0

    def test_register_counter_existing_returns_same(self, collector):
        """Test registering existing counter returns the same instance."""
        counter1 = collector.register_counter("test_counter", "Test")
        counter1.inc(5)
        counter2 = collector.register_counter("test_counter", "Different help")
        assert counter1 is counter2
        assert counter2.value == 5

    def test_register_counter_with_labels(self, collector):
        """Test registering counter with labels."""
        labels = {"env": "test"}
        counter = collector.register_counter("labeled_counter", "Test", labels=labels)
        assert counter.labels == labels

    def test_register_gauge_new(self, collector):
        """Test registering a new gauge."""
        gauge = collector.register_gauge("new_gauge", "A new gauge")
        assert gauge.name == "new_gauge"
        assert gauge.help_text == "A new gauge"
        assert gauge.value == 0.0

    def test_register_gauge_existing_returns_same(self, collector):
        """Test registering existing gauge returns the same instance."""
        gauge1 = collector.register_gauge("test_gauge", "Test")
        gauge1.set(42.0)
        gauge2 = collector.register_gauge("test_gauge", "Different help")
        assert gauge1 is gauge2
        assert gauge2.value == 42.0

    def test_register_gauge_with_labels(self, collector):
        """Test registering gauge with labels."""
        labels = {"host": "server1"}
        gauge = collector.register_gauge("labeled_gauge", "Test", labels=labels)
        assert gauge.labels == labels

    def test_register_histogram_new(self, collector):
        """Test registering a new histogram."""
        histogram = collector.register_histogram("new_histogram", "A new histogram")
        assert histogram.name == "new_histogram"
        assert histogram.help_text == "A new histogram"

    def test_register_histogram_existing_returns_same(self, collector):
        """Test registering existing histogram returns the same instance."""
        hist1 = collector.register_histogram("test_hist", "Test")
        hist1.observe(0.5)
        hist2 = collector.register_histogram("test_hist", "Different help")
        assert hist1 is hist2
        assert hist2.count == 1

    def test_register_histogram_with_custom_buckets(self, collector):
        """Test registering histogram with custom buckets."""
        custom_buckets = [0.1, 1.0, 10.0]
        histogram = collector.register_histogram(
            "custom_histogram", "Test", buckets=custom_buckets
        )
        assert histogram.buckets == custom_buckets

    def test_register_histogram_with_labels(self, collector):
        """Test registering histogram with labels."""
        labels = {"operation": "read"}
        histogram = collector.register_histogram("labeled_hist", "Test", labels=labels)
        assert histogram.labels == labels

    def test_inc_counter_registered(self, collector):
        """Test incrementing a registered counter."""
        collector.register_counter("inc_test", "Test")
        collector.inc_counter("inc_test", 3)
        metrics = collector.get_all_metrics()
        assert metrics["counters"]["inc_test"]["value"] == 3

    def test_inc_counter_unregistered_logs_warning(self, collector):
        """Test incrementing unregistered counter logs warning."""
        with patch("gobby.utils.metrics.logger.warning") as mock_warning:
            collector.inc_counter("nonexistent_counter")
            mock_warning.assert_called_once_with("Counter nonexistent_counter not registered")

    def test_set_gauge_registered(self, collector):
        """Test setting a registered gauge."""
        collector.register_gauge("set_test", "Test")
        collector.set_gauge("set_test", 99.9)
        metrics = collector.get_all_metrics()
        assert metrics["gauges"]["set_test"]["value"] == 99.9

    def test_set_gauge_unregistered_logs_warning(self, collector):
        """Test setting unregistered gauge logs warning."""
        with patch("gobby.utils.metrics.logger.warning") as mock_warning:
            collector.set_gauge("nonexistent_gauge", 10.0)
            mock_warning.assert_called_once_with("Gauge nonexistent_gauge not registered")

    def test_inc_gauge_registered(self, collector):
        """Test incrementing a registered gauge."""
        collector.register_gauge("inc_gauge_test", "Test")
        collector.set_gauge("inc_gauge_test", 10.0)
        collector.inc_gauge("inc_gauge_test", 5.0)
        metrics = collector.get_all_metrics()
        assert metrics["gauges"]["inc_gauge_test"]["value"] == 15.0

    def test_inc_gauge_unregistered_logs_warning(self, collector):
        """Test incrementing unregistered gauge logs warning."""
        with patch("gobby.utils.metrics.logger.warning") as mock_warning:
            collector.inc_gauge("nonexistent_gauge")
            mock_warning.assert_called_once_with("Gauge nonexistent_gauge not registered")

    def test_dec_gauge_registered(self, collector):
        """Test decrementing a registered gauge."""
        collector.register_gauge("dec_gauge_test", "Test")
        collector.set_gauge("dec_gauge_test", 10.0)
        collector.dec_gauge("dec_gauge_test", 3.0)
        metrics = collector.get_all_metrics()
        assert metrics["gauges"]["dec_gauge_test"]["value"] == 7.0

    def test_dec_gauge_unregistered_logs_warning(self, collector):
        """Test decrementing unregistered gauge logs warning."""
        with patch("gobby.utils.metrics.logger.warning") as mock_warning:
            collector.dec_gauge("nonexistent_gauge")
            mock_warning.assert_called_once_with("Gauge nonexistent_gauge not registered")

    def test_observe_histogram_registered(self, collector):
        """Test observing value in a registered histogram."""
        collector.register_histogram("observe_test", "Test")
        collector.observe_histogram("observe_test", 0.5)
        metrics = collector.get_all_metrics()
        assert metrics["histograms"]["observe_test"]["count"] == 1
        assert metrics["histograms"]["observe_test"]["sum"] == 0.5

    def test_observe_histogram_unregistered_logs_warning(self, collector):
        """Test observing in unregistered histogram logs warning."""
        with patch("gobby.utils.metrics.logger.warning") as mock_warning:
            collector.observe_histogram("nonexistent_histogram", 0.5)
            mock_warning.assert_called_once_with("Histogram nonexistent_histogram not registered")

    def test_get_uptime(self, collector):
        """Test get_uptime returns reasonable value."""
        # Allow some time to pass
        time.sleep(0.01)
        uptime = collector.get_uptime()
        assert uptime >= 0.01
        assert uptime < 10.0  # Should be less than 10 seconds

    def test_update_daemon_metrics_current_process(self, collector):
        """Test updating daemon metrics for current process."""
        collector.update_daemon_metrics()
        metrics = collector.get_all_metrics()

        assert metrics["gauges"]["daemon_uptime_seconds"]["value"] > 0
        assert metrics["gauges"]["daemon_memory_usage_bytes"]["value"] > 0
        assert "daemon_cpu_percent" in metrics["gauges"]

    def test_update_daemon_metrics_specific_pid(self, collector):
        """Test updating daemon metrics for specific process."""
        import os

        collector.update_daemon_metrics(pid=os.getpid())
        metrics = collector.get_all_metrics()

        assert metrics["gauges"]["daemon_uptime_seconds"]["value"] > 0
        assert metrics["gauges"]["daemon_memory_usage_bytes"]["value"] > 0

    def test_update_daemon_metrics_invalid_pid(self, collector):
        """Test updating daemon metrics with invalid PID."""
        with patch("gobby.utils.metrics.logger.warning") as mock_warning:
            collector.update_daemon_metrics(pid=999999999)
            mock_warning.assert_called_once()
            assert "Failed to update daemon metrics" in mock_warning.call_args[0][0]

    def test_update_daemon_metrics_access_denied(self, collector):
        """Test updating daemon metrics when access is denied."""
        with patch("psutil.Process") as mock_process:
            mock_process.side_effect = psutil.AccessDenied(pid=1)
            with patch("gobby.utils.metrics.logger.warning") as mock_warning:
                collector.update_daemon_metrics(pid=1)
                mock_warning.assert_called_once()
                assert "Failed to update daemon metrics" in mock_warning.call_args[0][0]

    def test_record_mcp_call_success(self, collector):
        """Test recording a successful MCP call."""
        collector.record_mcp_call(duration=0.5, success=True)
        metrics = collector.get_all_metrics()

        assert metrics["counters"]["mcp_calls_total"]["value"] == 1
        assert metrics["counters"]["mcp_calls_succeeded_total"]["value"] == 1
        assert metrics["counters"]["mcp_calls_failed_total"]["value"] == 0
        assert metrics["histograms"]["mcp_call_duration_seconds"]["count"] == 1
        assert metrics["histograms"]["mcp_call_duration_seconds"]["sum"] == 0.5

    def test_record_mcp_call_failure(self, collector):
        """Test recording a failed MCP call."""
        collector.record_mcp_call(duration=1.0, success=False)
        metrics = collector.get_all_metrics()

        assert metrics["counters"]["mcp_calls_total"]["value"] == 1
        assert metrics["counters"]["mcp_calls_succeeded_total"]["value"] == 0
        assert metrics["counters"]["mcp_calls_failed_total"]["value"] == 1

    def test_record_http_request_success(self, collector):
        """Test recording a successful HTTP request."""
        collector.record_http_request(duration=0.1, error=False)
        metrics = collector.get_all_metrics()

        assert metrics["counters"]["http_requests_total"]["value"] == 1
        assert metrics["counters"]["http_requests_errors_total"]["value"] == 0
        assert metrics["histograms"]["http_request_duration_seconds"]["count"] == 1

    def test_record_http_request_error(self, collector):
        """Test recording an HTTP request with error."""
        collector.record_http_request(duration=0.2, error=True)
        metrics = collector.get_all_metrics()

        assert metrics["counters"]["http_requests_total"]["value"] == 1
        assert metrics["counters"]["http_requests_errors_total"]["value"] == 1

    def test_record_memory_save_success(self, collector):
        """Test recording a successful memory save."""
        collector.record_memory_save(duration=0.3, success=True)
        metrics = collector.get_all_metrics()

        assert metrics["counters"]["memory_saves_total"]["value"] == 1
        assert metrics["counters"]["memory_saves_succeeded_total"]["value"] == 1
        assert metrics["counters"]["memory_saves_failed_total"]["value"] == 0
        assert metrics["histograms"]["memory_save_duration_seconds"]["count"] == 1

    def test_record_memory_save_failure(self, collector):
        """Test recording a failed memory save."""
        collector.record_memory_save(duration=0.4, success=False)
        metrics = collector.get_all_metrics()

        assert metrics["counters"]["memory_saves_total"]["value"] == 1
        assert metrics["counters"]["memory_saves_succeeded_total"]["value"] == 0
        assert metrics["counters"]["memory_saves_failed_total"]["value"] == 1

    def test_record_context_restore_success(self, collector):
        """Test recording a successful context restore."""
        collector.record_context_restore(duration=0.5, success=True)
        metrics = collector.get_all_metrics()

        assert metrics["counters"]["context_restores_total"]["value"] == 1
        assert metrics["counters"]["context_restores_succeeded_total"]["value"] == 1
        assert metrics["counters"]["context_restores_failed_total"]["value"] == 0
        assert metrics["histograms"]["context_restore_duration_seconds"]["count"] == 1

    def test_record_context_restore_failure(self, collector):
        """Test recording a failed context restore."""
        collector.record_context_restore(duration=0.6, success=False)
        metrics = collector.get_all_metrics()

        assert metrics["counters"]["context_restores_total"]["value"] == 1
        assert metrics["counters"]["context_restores_succeeded_total"]["value"] == 0
        assert metrics["counters"]["context_restores_failed_total"]["value"] == 1

    def test_get_all_metrics_structure(self, collector):
        """Test get_all_metrics returns proper structure."""
        metrics = collector.get_all_metrics()

        assert "counters" in metrics
        assert "gauges" in metrics
        assert "histograms" in metrics
        assert "uptime_seconds" in metrics

        assert isinstance(metrics["counters"], dict)
        assert isinstance(metrics["gauges"], dict)
        assert isinstance(metrics["histograms"], dict)
        assert isinstance(metrics["uptime_seconds"], float)

    def test_get_all_metrics_counter_format(self, collector):
        """Test get_all_metrics counter format."""
        labels = {"method": "GET"}
        collector.register_counter("test_counter", "Test", labels=labels)
        collector.inc_counter("test_counter", 5)

        metrics = collector.get_all_metrics()
        counter_data = metrics["counters"]["test_counter"]

        assert counter_data["value"] == 5
        assert counter_data["labels"] == labels

    def test_get_all_metrics_histogram_format(self, collector):
        """Test get_all_metrics histogram format."""
        labels = {"operation": "write"}
        collector.register_histogram("test_hist", "Test", labels=labels)
        collector.observe_histogram("test_hist", 0.5)

        metrics = collector.get_all_metrics()
        hist_data = metrics["histograms"]["test_hist"]

        assert hist_data["count"] == 1
        assert hist_data["sum"] == 0.5
        assert "buckets" in hist_data
        assert hist_data["labels"] == labels

    def test_export_prometheus_format(self, collector):
        """Test export_prometheus produces valid format."""
        output = collector.export_prometheus()

        # Check it ends with newline
        assert output.endswith("\n")

        # Check it contains expected elements
        assert "# HELP" in output
        assert "# TYPE" in output
        assert "counter" in output
        assert "gauge" in output
        assert "histogram" in output

    def test_export_prometheus_counter_format(self, collector):
        """Test prometheus export format for counters."""
        collector.register_counter("test_prom_counter", "Test counter")
        collector.inc_counter("test_prom_counter", 10)

        output = collector.export_prometheus()

        assert "# HELP test_prom_counter Test counter" in output
        assert "# TYPE test_prom_counter counter" in output
        assert "test_prom_counter 10" in output

    def test_export_prometheus_gauge_format(self, collector):
        """Test prometheus export format for gauges."""
        collector.register_gauge("test_prom_gauge", "Test gauge")
        collector.set_gauge("test_prom_gauge", 42.5)

        output = collector.export_prometheus()

        assert "# HELP test_prom_gauge Test gauge" in output
        assert "# TYPE test_prom_gauge gauge" in output
        assert "test_prom_gauge 42.5" in output

    def test_export_prometheus_histogram_format(self, collector):
        """Test prometheus export format for histograms."""
        custom_buckets = [0.1, 0.5, 1.0]
        collector.register_histogram("test_prom_hist", "Test histogram", buckets=custom_buckets)
        collector.observe_histogram("test_prom_hist", 0.3)

        output = collector.export_prometheus()

        assert "# HELP test_prom_hist Test histogram" in output
        assert "# TYPE test_prom_hist histogram" in output
        assert 'test_prom_hist_bucket{le="0.1"}' in output
        assert 'test_prom_hist_bucket{le="0.5"}' in output
        assert 'test_prom_hist_bucket{le="1.0"}' in output
        assert 'test_prom_hist_bucket{le="+Inf"}' in output
        assert "test_prom_hist_sum" in output
        assert "test_prom_hist_count" in output

    def test_export_prometheus_with_labels(self, collector):
        """Test prometheus export with labels."""
        labels = {"method": "GET", "status": "200"}
        collector.register_counter("labeled_counter", "Test", labels=labels)
        collector.inc_counter("labeled_counter")

        output = collector.export_prometheus()

        # Labels should be sorted alphabetically
        assert 'labeled_counter{method="GET",status="200"}' in output

    def test_format_labels_empty(self, collector):
        """Test _format_labels with empty labels."""
        result = collector._format_labels({})
        assert result == ""

    def test_format_labels_single(self, collector):
        """Test _format_labels with single label."""
        result = collector._format_labels({"key": "value"})
        assert result == '{key="value"}'

    def test_format_labels_multiple(self, collector):
        """Test _format_labels with multiple labels (sorted)."""
        result = collector._format_labels({"z_key": "z_value", "a_key": "a_value"})
        assert result == '{a_key="a_value",z_key="z_value"}'

    def test_thread_safety_multiple_increments(self, collector):
        """Test thread safety of counter increments."""
        import threading

        collector.register_counter("thread_test", "Test")

        def increment_many():
            for _ in range(100):
                collector.inc_counter("thread_test")

        threads = [threading.Thread(target=increment_many) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        metrics = collector.get_all_metrics()
        assert metrics["counters"]["thread_test"]["value"] == 1000


class TestGlobalMetricsCollector:
    """Tests for global metrics collector singleton."""

    def teardown_method(self):
        """Reset global collector after each test."""
        import gobby.utils.metrics as metrics_module

        metrics_module._metrics_collector = None

    def test_get_metrics_collector_creates_singleton(self):
        """Test get_metrics_collector creates singleton instance."""
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()
        assert collector1 is collector2

    def test_get_metrics_collector_returns_metrics_collector(self):
        """Test get_metrics_collector returns MetricsCollector instance."""
        collector = get_metrics_collector()
        assert isinstance(collector, MetricsCollector)

    def test_global_collector_has_standard_metrics(self):
        """Test global collector has standard metrics initialized."""
        collector = get_metrics_collector()
        metrics = collector.get_all_metrics()

        # Verify some standard metrics exist
        assert "http_requests_total" in metrics["counters"]
        assert "daemon_uptime_seconds" in metrics["gauges"]
        assert "http_request_duration_seconds" in metrics["histograms"]


class TestMetricsCollectorEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def collector(self):
        """Create a fresh MetricsCollector for each test."""
        return MetricsCollector()

    def test_histogram_observe_zero(self, collector):
        """Test observing zero value in histogram."""
        collector.register_histogram("zero_test", "Test")
        collector.observe_histogram("zero_test", 0.0)
        metrics = collector.get_all_metrics()
        assert metrics["histograms"]["zero_test"]["count"] == 1
        assert metrics["histograms"]["zero_test"]["sum"] == 0.0

    def test_histogram_observe_negative_value(self, collector):
        """Test observing negative value in histogram."""
        collector.register_histogram("neg_test", "Test")
        collector.observe_histogram("neg_test", -1.0)
        metrics = collector.get_all_metrics()
        # Negative values won't fit in any bucket
        assert metrics["histograms"]["neg_test"]["count"] == 1
        assert metrics["histograms"]["neg_test"]["sum"] == -1.0

    def test_counter_inc_zero(self, collector):
        """Test incrementing counter by zero."""
        collector.register_counter("zero_inc_test", "Test")
        collector.inc_counter("zero_inc_test", 0)
        metrics = collector.get_all_metrics()
        assert metrics["counters"]["zero_inc_test"]["value"] == 0

    def test_gauge_operations_with_large_numbers(self, collector):
        """Test gauge operations with large numbers."""
        collector.register_gauge("large_test", "Test")
        large_value = 10**15
        collector.set_gauge("large_test", float(large_value))
        metrics = collector.get_all_metrics()
        assert metrics["gauges"]["large_test"]["value"] == float(large_value)

    def test_histogram_with_empty_buckets_list(self, collector):
        """Test histogram with empty buckets list."""
        # This should still work, just no bucket counts
        histogram = Histogram(name="empty_buckets", help_text="Test", buckets=[])
        assert histogram.bucket_counts == {}
        histogram.observe(0.5)
        assert histogram.count == 1
        assert histogram.sum == 0.5

    def test_counter_with_special_characters_in_name(self, collector):
        """Test counter with underscores in name (valid prometheus naming)."""
        collector.register_counter("my_counter_total", "Test with underscores")
        collector.inc_counter("my_counter_total")
        metrics = collector.get_all_metrics()
        assert "my_counter_total" in metrics["counters"]

    def test_multiple_record_operations(self, collector):
        """Test multiple record operations accumulate correctly."""
        # Record multiple operations
        for i in range(5):
            collector.record_mcp_call(duration=0.1 * (i + 1), success=i % 2 == 0)

        metrics = collector.get_all_metrics()
        assert metrics["counters"]["mcp_calls_total"]["value"] == 5
        assert metrics["counters"]["mcp_calls_succeeded_total"]["value"] == 3  # i=0,2,4
        assert metrics["counters"]["mcp_calls_failed_total"]["value"] == 2  # i=1,3
        assert metrics["histograms"]["mcp_call_duration_seconds"]["count"] == 5
        # Sum = 0.1 + 0.2 + 0.3 + 0.4 + 0.5 = 1.5
        assert metrics["histograms"]["mcp_call_duration_seconds"]["sum"] == pytest.approx(1.5)

    def test_uptime_increases_over_time(self, collector):
        """Test that uptime increases over time."""
        uptime1 = collector.get_uptime()
        time.sleep(0.05)
        uptime2 = collector.get_uptime()
        assert uptime2 > uptime1
