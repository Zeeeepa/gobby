"""Tests for CLI __main__ module."""


def test_cli_main_import():
    """Test that cli.__main__ module can be imported."""
    # This tests the entry point module loads correctly
    from gobby.cli import __main__  # noqa: F401

    # Verify cli is accessible
    assert hasattr(__main__, "cli")


def test_cli_main_cli_callable():
    """Test that the cli object is callable."""
    from gobby.cli.__main__ import cli

    assert callable(cli)
