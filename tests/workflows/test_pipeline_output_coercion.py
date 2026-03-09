"""Tests for pipeline output value coercion.

Jinja2 renders all values as strings. _coerce_rendered_value converts
string representations of booleans, None, and numbers back to native types.
This prevents "False" (truthy non-empty string) from being treated as True
in pipeline condition evaluation.
"""

import pytest

from gobby.workflows.pipeline_executor import _coerce_rendered_value

pytestmark = pytest.mark.unit


class TestCoerceRenderedValue:
    """Tests for _coerce_rendered_value helper."""

    def test_false_string_becomes_false(self) -> None:
        assert _coerce_rendered_value("False") is False

    def test_true_string_becomes_true(self) -> None:
        assert _coerce_rendered_value("True") is True

    def test_case_insensitive_false(self) -> None:
        assert _coerce_rendered_value("false") is False
        assert _coerce_rendered_value("FALSE") is False

    def test_case_insensitive_true(self) -> None:
        assert _coerce_rendered_value("true") is True
        assert _coerce_rendered_value("TRUE") is True

    def test_none_string_becomes_none(self) -> None:
        assert _coerce_rendered_value("None") is None
        assert _coerce_rendered_value("none") is None

    def test_integer_string_becomes_int(self) -> None:
        assert _coerce_rendered_value("42") == 42
        assert isinstance(_coerce_rendered_value("42"), int)

    def test_negative_integer_string(self) -> None:
        assert _coerce_rendered_value("-1") == -1
        assert isinstance(_coerce_rendered_value("-1"), int)

    def test_float_string_becomes_float(self) -> None:
        assert _coerce_rendered_value("3.14") == pytest.approx(3.14)
        assert isinstance(_coerce_rendered_value("3.14"), float)

    def test_regular_string_preserved(self) -> None:
        assert _coerce_rendered_value("hello") == "hello"

    def test_empty_string_preserved(self) -> None:
        assert _coerce_rendered_value("") == ""

    def test_whitespace_around_bool(self) -> None:
        assert _coerce_rendered_value(" False ") is False
        assert _coerce_rendered_value(" True ") is True

    def test_non_string_passthrough(self) -> None:
        assert _coerce_rendered_value(42) == 42
        assert _coerce_rendered_value(False) is False
        assert _coerce_rendered_value(None) is None
        assert _coerce_rendered_value([1, 2]) == [1, 2]

    def test_zero_string_becomes_int(self) -> None:
        assert _coerce_rendered_value("0") == 0
        assert isinstance(_coerce_rendered_value("0"), int)

    def test_string_with_spaces_not_number(self) -> None:
        """Strings like 'hello world' stay as strings."""
        assert _coerce_rendered_value("hello world") == "hello world"
