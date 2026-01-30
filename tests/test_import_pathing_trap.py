import pytest

import gobby.mcp_proxy.stdio

# Force import of modules that use load_config to ensure they are in sys.modules
# BEFORE the fixture runs. pytest collection usually does this anyway, but let's be explicit.
import gobby.runner

pytestmark = pytest.mark.unit

def test_import_pathing_trap_is_fixed(protect_production_resources) -> None:
    """
    Verify that the protect_production_resources fixture successfully patches
    load_config in modules that have already imported it.
    """
    # 1. Check gobby.runner.load_config
    # It should be the 'safe_load_config' function defined in the fixture
    # matching the name 'safe_load_config'
    assert gobby.runner.load_config.__name__ == "safe_load_config", (
        f"gobby.runner.load_config should be patched to safe_load_config, got {gobby.runner.load_config}"
    )

    # 2. Check its behavior
    config = gobby.runner.load_config()
    assert "test-safe.db" in config.database_path, (
        "Resulting config should point to safe test database"
    )

    # 3. Check another module: gobby.mcp_proxy.stdio
    assert gobby.mcp_proxy.stdio.load_config.__name__ == "safe_load_config", (
        "gobby.mcp_proxy.stdio.load_config should also be patched"
    )


def test_runner_uses_patched_config(protect_production_resources) -> None:
    """Integration checks that Runner actually initializes with safe config."""
    runner = gobby.runner.GobbyRunner()

    # Ensure it's using the safe DB
    assert "test-safe.db" in str(runner.database.db_path)
