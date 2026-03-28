"""Tests for _set_project_context_for_request in execution.py.

Verifies that #N session references are resolved to UUIDs before
setting project context, preventing cross-project resolution.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from gobby.servers.routes.mcp.endpoints.execution import _set_project_context_for_request

pytestmark = pytest.mark.unit

SESSION_UUID = str(uuid.uuid4())
PROJECT_ID = str(uuid.uuid4())


def _make_server(db: MagicMock | None = None) -> MagicMock:
    server = MagicMock()
    server.session_manager = MagicMock()
    if db is not None:
        server.session_manager.db = db
    return server


def _make_request(
    project_id: str | None = None,
    session_id: str | None = None,
) -> MagicMock:
    request = MagicMock()
    headers: dict[str, str] = {}
    if project_id:
        headers["x-gobby-project-id"] = project_id
    if session_id:
        headers["x-gobby-session-id"] = session_id
    request.headers = headers
    return request


class TestSetProjectContextForRequest:
    """Tests for _set_project_context_for_request."""

    def test_hash_n_ref_resolved_before_context_set(self) -> None:
        """#N reference should be resolved to UUID via resolve_session_reference."""
        server = _make_server()
        request = _make_request(project_id=PROJECT_ID)

        with (
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.resolve_session_reference",
                return_value=SESSION_UUID,
            ) as mock_resolve,
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.set_project_context_from_session",
                return_value="token",
            ) as mock_set_ctx,
        ):
            token = _set_project_context_for_request(server, {"session_id": "#5"}, request)

        mock_resolve.assert_called_once_with(server.session_manager.db, "#5", PROJECT_ID)
        mock_set_ctx.assert_called_once_with(
            SESSION_UUID, server.session_manager, server.session_manager.db
        )
        assert token == "token"

    def test_numeric_string_ref_resolved(self) -> None:
        """Plain numeric string '5' should be treated as #N reference."""
        server = _make_server()
        request = _make_request(project_id=PROJECT_ID)

        with (
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.resolve_session_reference",
                return_value=SESSION_UUID,
            ) as mock_resolve,
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.set_project_context_from_session",
                return_value="token",
            ),
        ):
            _set_project_context_for_request(server, {"session_id": "5"}, request)

        mock_resolve.assert_called_once_with(server.session_manager.db, "5", PROJECT_ID)

    def test_hash_n_ref_no_header_uses_none_project(self) -> None:
        """#N ref without X-Gobby-Project-Id header uses project_id=None."""
        server = _make_server()
        request = _make_request()  # no project_id header

        with (
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.resolve_session_reference",
                return_value=SESSION_UUID,
            ) as mock_resolve,
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.set_project_context_from_session",
                return_value="token",
            ),
        ):
            _set_project_context_for_request(server, {"session_id": "#5"}, request)

        mock_resolve.assert_called_once_with(server.session_manager.db, "#5", None)

    def test_hash_n_resolution_failure_falls_through_to_header(self) -> None:
        """If #N resolution fails, fall through to X-Gobby-Project-Id header."""
        server = _make_server()
        request = _make_request(project_id=PROJECT_ID)

        with (
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.resolve_session_reference",
                side_effect=ValueError("Session #99 not found"),
            ),
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.set_project_context_from_session",
            ) as mock_set_ctx,
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.set_project_context",
                return_value="header_token",
            ),
        ):
            token = _set_project_context_for_request(server, {"session_id": "#99"}, request)

        # Should NOT have tried set_project_context_from_session
        mock_set_ctx.assert_not_called()
        # Should have fallen through to header-based fallback
        assert token == "header_token"

    def test_uuid_session_id_skips_resolution(self) -> None:
        """UUID session_id should bypass resolve_session_reference entirely."""
        server = _make_server()
        request = _make_request(project_id=PROJECT_ID)

        with (
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.resolve_session_reference",
            ) as mock_resolve,
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.set_project_context_from_session",
                return_value="token",
            ) as mock_set_ctx,
        ):
            _set_project_context_for_request(server, {"session_id": SESSION_UUID}, request)

        mock_resolve.assert_not_called()
        mock_set_ctx.assert_called_once_with(
            SESSION_UUID, server.session_manager, server.session_manager.db
        )

    def test_no_session_id_falls_through_to_header(self) -> None:
        """No session_id in arguments or headers falls through to project header."""
        server = _make_server()
        request = _make_request(project_id=PROJECT_ID)

        with (
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.resolve_session_reference",
            ) as mock_resolve,
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.set_project_context_from_session",
            ) as mock_set_ctx,
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.set_project_context",
                return_value="header_token",
            ),
        ):
            token = _set_project_context_for_request(server, {}, request)

        mock_resolve.assert_not_called()
        mock_set_ctx.assert_not_called()
        assert token == "header_token"

    def test_uuid_prefix_not_treated_as_seq_num(self) -> None:
        """UUID prefix like 'a1b2c3' should not be treated as a #N ref."""
        server = _make_server()
        request = _make_request(project_id=PROJECT_ID)

        with (
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.resolve_session_reference",
            ) as mock_resolve,
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.set_project_context_from_session",
                return_value="token",
            ),
        ):
            _set_project_context_for_request(server, {"session_id": "a1b2c3"}, request)

        # UUID prefix is not all digits — should NOT go through resolve_session_reference
        mock_resolve.assert_not_called()

    def test_header_session_id_also_resolved(self) -> None:
        """#N ref from X-Gobby-Session-Id header should also be resolved."""
        server = _make_server()
        request = _make_request(project_id=PROJECT_ID, session_id="#7")

        with (
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.resolve_session_reference",
                return_value=SESSION_UUID,
            ) as mock_resolve,
            patch(
                "gobby.servers.routes.mcp.endpoints.execution.set_project_context_from_session",
                return_value="token",
            ),
        ):
            # No session_id in arguments — falls to header
            _set_project_context_for_request(server, {}, request)

        mock_resolve.assert_called_once_with(server.session_manager.db, "#7", PROJECT_ID)
