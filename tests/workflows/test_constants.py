"""Tests for workflows constants module."""

import importlib

from gobby.workflows.constants import PIPELINE_TEST_1, PIPELINE_TEST_2


def test_constants_module_has_docstring() -> None:
    """Verify that the constants module has a module-level docstring."""
    mod = importlib.import_module("gobby.workflows.constants")
    assert mod.__doc__ is not None
    assert "constant" in mod.__doc__.lower()


def test_pipeline_test_1_exists() -> None:
    """Verify that PIPELINE_TEST_1 constant exists."""
    from gobby.workflows import constants

    assert hasattr(constants, "PIPELINE_TEST_1")


def test_pipeline_test_1_value() -> None:
    """Verify that PIPELINE_TEST_1 has the correct value."""
    assert PIPELINE_TEST_1 == "coordinator-run-1"


def test_pipeline_test_1_is_string() -> None:
    """Verify that PIPELINE_TEST_1 is a string."""
    assert isinstance(PIPELINE_TEST_1, str)


def test_pipeline_test_2_exists() -> None:
    """Verify that PIPELINE_TEST_2 constant exists."""
    from gobby.workflows import constants

    assert hasattr(constants, "PIPELINE_TEST_2")


def test_pipeline_test_2_value() -> None:
    """Verify that PIPELINE_TEST_2 has the correct value."""
    assert PIPELINE_TEST_2 == "coordinator-run-2"


def test_pipeline_test_2_is_string() -> None:
    """Verify that PIPELINE_TEST_2 is a string."""
    assert isinstance(PIPELINE_TEST_2, str)
