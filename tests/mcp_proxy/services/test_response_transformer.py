"""Tests for ResponseTransformerService."""

from unittest.mock import MagicMock

from gobby.mcp_proxy.services.response_transformer import (
    COMPRESSIBLE_FIELDS,
    ResponseTransformerService,
)


class TestResponseTransformerService:
    """Tests for ResponseTransformerService."""

    def test_disabled_without_compressor(self):
        """When no compressor, transformer is disabled."""
        transformer = ResponseTransformerService(compressor=None)
        assert transformer.is_enabled is False

    def test_disabled_when_compression_not_enabled(self):
        """When compressor config.enabled is False, transformer is disabled."""
        mock_compressor = MagicMock()
        mock_compressor.config.enabled = False
        transformer = ResponseTransformerService(compressor=mock_compressor)
        assert transformer.is_enabled is False

    def test_enabled_when_compression_enabled(self):
        """When compressor config.enabled is True, transformer is enabled."""
        mock_compressor = MagicMock()
        mock_compressor.config.enabled = True
        transformer = ResponseTransformerService(compressor=mock_compressor)
        assert transformer.is_enabled is True

    def test_transform_passthrough_when_disabled(self):
        """When disabled, responses pass through unchanged."""
        transformer = ResponseTransformerService(compressor=None)
        response = {"success": True, "output": "A" * 1000}
        result = transformer.transform_response(response)
        assert result == response

    def test_transform_dict_with_compressible_field(self):
        """Compresses large string in compressible field."""
        mock_compressor = MagicMock()
        mock_compressor.config.enabled = True
        mock_compressor.config.min_content_length = 100
        mock_compressor.compress.return_value = "compressed"

        transformer = ResponseTransformerService(compressor=mock_compressor)
        response = {"success": True, "output": "A" * 200}

        result = transformer.transform_response(response)

        assert result["success"] is True
        assert result["output"] == "compressed"
        mock_compressor.compress.assert_called_once()

    def test_skip_short_strings(self):
        """Strings below min_content_length are not compressed."""
        mock_compressor = MagicMock()
        mock_compressor.config.enabled = True
        mock_compressor.config.min_content_length = 500

        transformer = ResponseTransformerService(compressor=mock_compressor)
        response = {"success": True, "output": "short text"}

        result = transformer.transform_response(response)

        assert result["output"] == "short text"
        mock_compressor.compress.assert_not_called()

    def test_preserve_non_compressible_fields(self):
        """Non-compressible fields like 'success', 'id' are not modified."""
        mock_compressor = MagicMock()
        mock_compressor.config.enabled = True
        mock_compressor.config.min_content_length = 100

        transformer = ResponseTransformerService(compressor=mock_compressor)
        response = {
            "success": True,
            "id": "abc123",
            "count": 42,
            "enabled": False,
        }

        result = transformer.transform_response(response)

        assert result == response
        mock_compressor.compress.assert_not_called()

    def test_transform_nested_dict(self):
        """Compresses fields in nested dictionaries."""
        mock_compressor = MagicMock()
        mock_compressor.config.enabled = True
        mock_compressor.config.min_content_length = 100
        mock_compressor.compress.return_value = "compressed"

        transformer = ResponseTransformerService(compressor=mock_compressor)
        response = {
            "success": True,
            "data": {
                "content": "A" * 200,
            },
        }

        result = transformer.transform_response(response)

        assert result["data"]["content"] == "compressed"

    def test_transform_list_of_dicts(self):
        """Compresses fields in list items."""
        mock_compressor = MagicMock()
        mock_compressor.config.enabled = True
        mock_compressor.config.min_content_length = 100
        mock_compressor.compress.return_value = "compressed"

        transformer = ResponseTransformerService(compressor=mock_compressor)
        response = {
            "items": [
                {"output": "A" * 200},
                {"output": "B" * 200},
            ]
        }

        result = transformer.transform_response(response)

        assert result["items"][0]["output"] == "compressed"
        assert result["items"][1]["output"] == "compressed"
        assert mock_compressor.compress.call_count == 2

    def test_transform_string_response(self):
        """Compresses string-only responses if large enough."""
        mock_compressor = MagicMock()
        mock_compressor.config.enabled = True
        mock_compressor.config.min_content_length = 100
        mock_compressor.compress.return_value = "compressed"

        transformer = ResponseTransformerService(compressor=mock_compressor)
        response = "A" * 200

        result = transformer.transform_response(response)

        assert result == "compressed"

    def test_passthrough_non_string_primitives(self):
        """Non-string primitives pass through unchanged."""
        mock_compressor = MagicMock()
        mock_compressor.config.enabled = True
        mock_compressor.config.min_content_length = 100

        transformer = ResponseTransformerService(compressor=mock_compressor)

        assert transformer.transform_response(42) == 42
        assert transformer.transform_response(3.14) == 3.14
        assert transformer.transform_response(True) is True
        assert transformer.transform_response(None) is None

    def test_compression_error_falls_back_to_original(self):
        """When compression fails, returns original content."""
        mock_compressor = MagicMock()
        mock_compressor.config.enabled = True
        mock_compressor.config.min_content_length = 100
        mock_compressor.compress.side_effect = RuntimeError("Model error")

        transformer = ResponseTransformerService(compressor=mock_compressor)
        response = {"output": "A" * 200}

        result = transformer.transform_response(response)

        # Should return original on error
        assert result["output"] == "A" * 200

    def test_context_type_passthrough(self):
        """Context type is passed to compressor."""
        mock_compressor = MagicMock()
        mock_compressor.config.enabled = True
        mock_compressor.config.min_content_length = 100
        mock_compressor.compress.return_value = "compressed"

        transformer = ResponseTransformerService(compressor=mock_compressor)
        response = {"output": "A" * 200}

        transformer.transform_response(response, context_type="memory")

        mock_compressor.compress.assert_called_once()
        call_args = mock_compressor.compress.call_args
        assert call_args.kwargs.get("context_type") == "memory"

    def test_invalid_context_type_defaults_to_context(self):
        """Invalid context_type defaults to 'context'."""
        mock_compressor = MagicMock()
        mock_compressor.config.enabled = True
        mock_compressor.config.min_content_length = 100
        mock_compressor.compress.return_value = "compressed"

        transformer = ResponseTransformerService(compressor=mock_compressor)
        response = {"output": "A" * 200}

        transformer.transform_response(response, context_type="invalid")

        call_args = mock_compressor.compress.call_args
        assert call_args.kwargs.get("context_type") == "context"


class TestCompressibleFields:
    """Tests for COMPRESSIBLE_FIELDS constant."""

    def test_common_fields_included(self):
        """Common response field names are in the compressible set."""
        expected_fields = [
            "output",
            "result",
            "content",
            "data",
            "description",
            "text",
            "body",
            "message",
            "summary",
            "response",
        ]
        for field in expected_fields:
            assert field in COMPRESSIBLE_FIELDS, f"{field} should be compressible"

    def test_metadata_fields_excluded(self):
        """Metadata fields like id, count, status are not compressible."""
        excluded_fields = ["id", "count", "status", "success", "error", "timestamp"]
        for field in excluded_fields:
            assert field not in COMPRESSIBLE_FIELDS, f"{field} should not be compressible"
