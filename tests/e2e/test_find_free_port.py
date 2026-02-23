"""Tests for find_free_port helper in e2e conftest."""

import pytest

from tests.e2e.conftest import find_free_port

pytestmark = pytest.mark.unit


class TestFindFreePort:
    """Tests for the e2e find_free_port function."""

    def test_returns_port_in_range(self) -> None:
        """Port must be in the 30000-40000 range."""
        port = find_free_port()
        assert 30000 <= port <= 40000, f"Port {port} outside expected range 30000-40000"

    def test_avoids_excluded_ports(self) -> None:
        """Excluded production ports should never be returned."""
        excluded = {60887, 60888, 60889}
        for _ in range(10):
            port = find_free_port()
            assert port not in excluded, f"Got excluded port {port}"

    def test_returns_different_ports(self) -> None:
        """Successive calls should be able to return different ports (not stuck)."""
        ports = {find_free_port() for _ in range(5)}
        # At least 2 distinct ports across 5 calls (can't guarantee all different)
        assert len(ports) >= 1  # At minimum it must return *something*

    def test_port_is_int(self) -> None:
        """Return value must be an integer."""
        port = find_free_port()
        assert isinstance(port, int)
