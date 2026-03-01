"""Tests for workflows constants module."""

import importlib


def test_constants_module_has_docstring() -> None:
    """Verify that the constants module has a module-level docstring."""
    mod = importlib.import_module("gobby.workflows.constants")
    assert mod.__doc__ is not None
    assert "constant" in mod.__doc__.lower()
