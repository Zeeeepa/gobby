"""Tests for lazy server initialization."""

import asyncio
import time

import pytest

from gobby.mcp_proxy.lazy import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
    LazyConnectionState,
    LazyServerConnector,
    RetryConfig,
)


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def test_initial_state_is_closed(self):
        """Circuit starts in closed state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.can_execute()

    def test_success_resets_failures(self):
        """Success resets failure count."""
        cb = CircuitBreaker()
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2

        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold_failures(self):
        """Circuit opens after failure threshold."""
        cb = CircuitBreaker(failure_threshold=3)

        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()  # Third failure trips circuit
        assert cb.state == CircuitState.OPEN
        assert not cb.can_execute()

    def test_recovery_timeout_triggers_half_open(self):
        """After recovery timeout, circuit enters half-open."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.can_execute()

        # Wait for recovery timeout
        time.sleep(0.15)

        assert cb.can_execute()
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self):
        """Success in half-open state closes circuit."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)

        cb.record_failure()
        time.sleep(0.02)
        cb.can_execute()  # Triggers half-open

        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute()

    def test_half_open_failure_reopens_circuit(self):
        """Failure in half-open state reopens circuit."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)

        cb.record_failure()
        time.sleep(0.02)
        cb.can_execute()  # Triggers half-open

        cb.record_failure()
        assert cb.state == CircuitState.OPEN


class TestRetryConfig:
    """Tests for RetryConfig."""

    def test_exponential_delays(self):
        """Delays increase exponentially."""
        config = RetryConfig(initial_delay=1.0, multiplier=2.0, max_delay=16.0)

        assert config.get_delay(0) == 1.0
        assert config.get_delay(1) == 2.0
        assert config.get_delay(2) == 4.0
        assert config.get_delay(3) == 8.0
        assert config.get_delay(4) == 16.0

    def test_delay_capped_at_max(self):
        """Delay doesn't exceed max_delay."""
        config = RetryConfig(initial_delay=1.0, multiplier=2.0, max_delay=5.0)

        assert config.get_delay(5) == 5.0
        assert config.get_delay(10) == 5.0


class TestLazyConnectionState:
    """Tests for LazyConnectionState."""

    def test_initial_state(self):
        """Initial state is not connected."""
        state = LazyConnectionState()
        assert not state.is_connected
        assert state.connected_at is None
        assert state.last_error is None
        assert state.connection_attempts == 0

    def test_connection_attempt_tracking(self):
        """Connection attempts are tracked."""
        state = LazyConnectionState()

        state.record_connection_attempt()
        assert state.connection_attempts == 1
        assert state.last_attempt_at is not None

        state.record_connection_attempt()
        assert state.connection_attempts == 2

    def test_connection_success(self):
        """Successful connection is recorded."""
        state = LazyConnectionState()

        state.record_connection_success()
        assert state.is_connected
        assert state.connected_at is not None
        assert state.last_error is None

    def test_connection_failure(self):
        """Failed connection is recorded."""
        state = LazyConnectionState()

        state.record_connection_failure("Connection refused")
        assert not state.is_connected
        assert state.last_error == "Connection refused"


class TestLazyServerConnector:
    """Tests for LazyServerConnector."""

    def test_register_server(self):
        """Servers can be registered."""
        connector = LazyServerConnector()

        connector.register_server("test-server")
        assert connector.get_state("test-server") is not None
        assert not connector.is_connected("test-server")

    def test_unregister_server(self):
        """Servers can be unregistered."""
        connector = LazyServerConnector()

        connector.register_server("test-server")
        connector.unregister_server("test-server")
        assert connector.get_state("test-server") is None

    def test_is_connected(self):
        """Connection status is tracked."""
        connector = LazyServerConnector()

        connector.register_server("test-server")
        assert not connector.is_connected("test-server")

        connector.mark_connected("test-server")
        assert connector.is_connected("test-server")

    def test_mark_failed(self):
        """Failures are recorded."""
        connector = LazyServerConnector()

        connector.register_server("test-server")
        connector.mark_failed("test-server", "Connection timeout")

        state = connector.get_state("test-server")
        assert state is not None
        assert state.last_error == "Connection timeout"
        assert state.circuit_breaker.failure_count == 1

    def test_circuit_breaker_blocks_connection(self):
        """Circuit breaker blocks connection attempts."""
        connector = LazyServerConnector(
            circuit_breaker_config={"failure_threshold": 2}
        )

        connector.register_server("test-server")
        assert connector.can_attempt_connection("test-server")

        connector.mark_failed("test-server", "Error 1")
        assert connector.can_attempt_connection("test-server")

        connector.mark_failed("test-server", "Error 2")
        assert not connector.can_attempt_connection("test-server")

    def test_get_all_states(self):
        """All states can be retrieved."""
        connector = LazyServerConnector()

        connector.register_server("server-1")
        connector.register_server("server-2")
        connector.mark_connected("server-1")

        states = connector.get_all_states()
        assert len(states) == 2
        assert states["server-1"]["is_connected"] is True
        assert states["server-2"]["is_connected"] is False

    @pytest.mark.asyncio
    async def test_connection_lock_prevents_concurrent_connects(self):
        """Connection lock serializes connection attempts."""
        connector = LazyServerConnector()
        connector.register_server("test-server")

        lock = connector.get_connection_lock("test-server")

        # Acquire lock
        async with lock:
            # Try to acquire again (should fail or wait)
            acquired = lock.locked()
            assert acquired


class TestCircuitBreakerOpen:
    """Tests for CircuitBreakerOpen exception."""

    def test_exception_message(self):
        """Exception has descriptive message."""
        exc = CircuitBreakerOpen("test-server", 15.5)

        assert exc.server_name == "test-server"
        assert exc.recovery_in == 15.5
        assert "test-server" in str(exc)
        assert "15.5" in str(exc)
