import pytest

import gobby.mcp_proxy.stdio
import gobby.runner

pytestmark = pytest.mark.unit


def test_import_pathing_trap_is_fixed(protect_production_resources) -> None:
    """
    Verify that the protect_production_resources fixture successfully patches
    load_config in modules that have already imported it.
    """
    # Check gobby.mcp_proxy.stdio.load_config
    # It should be the 'safe_load_config' function defined in the fixture
    assert gobby.mcp_proxy.stdio.load_config.__name__ == "safe_load_config", (
        "gobby.mcp_proxy.stdio.load_config should be patched to safe_load_config"
    )

    # Check its behavior
    config = gobby.mcp_proxy.stdio.load_config()
    assert "test-safe.db" in config.database_path, (
        "Resulting config should point to safe test database"
    )


@pytest.mark.skip(reason="Flaky: numpy reimport crash when run after tests that load numpy")
def test_runner_uses_patched_config(protect_production_resources) -> None:
    """Integration checks that Runner actually initializes with safe config."""
    runner = gobby.runner.GobbyRunner()

    # Ensure it's using the safe DB
    assert "test-safe.db" in str(runner.database.db_path)
