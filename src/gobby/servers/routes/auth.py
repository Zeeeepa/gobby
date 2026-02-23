"""
Authentication routes for Gobby web UI.

Provides login/logout/status endpoints with cookie-based sessions.
Auth is optional — disabled when no username/password is configured.
"""

import logging
import os
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gobby.storage.auth import AuthStore, hash_password, verify_password
from gobby.storage.config_store import ConfigStore, config_key_to_secret_name
from gobby.storage.secrets import SecretStore

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)

COOKIE_NAME = "gobby_session"


class LoginRequest(BaseModel):
    """Request body for POST /api/auth/login."""

    username: str
    password: str
    remember_me: bool = False


def _get_auth_credentials(server: "HTTPServer") -> tuple[str, str]:
    """Get configured username and password hash.

    Returns:
        Tuple of (username, password_hash). Both empty if auth not configured.
    """
    config = server.services.config
    if not config:
        return "", ""

    username = config.auth.username
    if not username:
        return "", ""

    # Resolve password from secrets
    from gobby.storage.database import LocalDatabase

    db = server.services.database
    if not isinstance(db, LocalDatabase):
        return "", ""

    secret_store = SecretStore(db)
    config_store = ConfigStore(db)

    # The password is stored as a bcrypt/pbkdf2 hash in the secrets table
    # under the key derived from "auth.password"
    secret_name = config_key_to_secret_name("auth.password")
    password_hash = secret_store.get(secret_name)

    if not password_hash:
        return "", ""

    return username, password_hash


def is_auth_enabled(server: "HTTPServer") -> bool:
    """Check if auth is configured (both username and password set)."""
    username, password_hash = _get_auth_credentials(server)
    return bool(username and password_hash)


def _get_auth_store(server: "HTTPServer") -> AuthStore:
    """Get or create AuthStore instance."""
    from gobby.storage.database import LocalDatabase

    db = server.services.database
    if not isinstance(db, LocalDatabase):
        raise RuntimeError("Database not available")
    return AuthStore(db)


def validate_session_cookie(request: Request, server: "HTTPServer") -> bool:
    """Validate the session cookie from a request.

    Used by auth middleware.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    auth_store = _get_auth_store(server)
    return auth_store.validate_session(token)


def create_auth_router(server: "HTTPServer") -> APIRouter:
    """Create the authentication API router."""
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.post("/login")
    async def login(req: LoginRequest) -> JSONResponse:
        """Authenticate with username/password, set session cookie."""
        username, password_hash = _get_auth_credentials(server)

        if not username or not password_hash:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Authentication not configured"},
            )

        # Validate credentials
        if req.username != username or not verify_password(req.password, password_hash):
            logger.warning(f"Failed login attempt for user: {req.username}")
            return JSONResponse(
                status_code=401,
                content={"ok": False, "error": "Invalid username or password"},
            )

        # Create session
        auth_store = _get_auth_store(server)
        token, expires_at = auth_store.create_session(remember_me=req.remember_me)

        response = JSONResponse(content={"ok": True})
        cookie_kwargs: dict[str, Any] = {
            "key": COOKIE_NAME,
            "value": token,
            "httponly": True,
            "samesite": "lax",
            "path": "/",
        }

        if req.remember_me:
            cookie_kwargs["max_age"] = 30 * 24 * 60 * 60  # 30 days in seconds

        response.set_cookie(**cookie_kwargs)
        logger.info(f"User '{req.username}' logged in (remember_me={req.remember_me})")
        return response

    @router.post("/logout")
    async def logout(request: Request) -> JSONResponse:
        """Clear session cookie and delete session."""
        token = request.cookies.get(COOKIE_NAME)
        if token:
            auth_store = _get_auth_store(server)
            auth_store.delete_session(token)

        response = JSONResponse(content={"ok": True})
        response.delete_cookie(key=COOKIE_NAME, path="/")
        return response

    @router.get("/status")
    async def auth_status(request: Request) -> JSONResponse:
        """Check current auth state.

        Returns whether auth is required and if the current session is valid.
        """
        auth_required = is_auth_enabled(server)

        if not auth_required:
            return JSONResponse(
                content={
                    "auth_required": False,
                    "authenticated": True,  # No auth needed = always authenticated
                }
            )

        token = request.cookies.get(COOKIE_NAME)
        authenticated = False
        if token:
            auth_store = _get_auth_store(server)
            authenticated = auth_store.validate_session(token)

        return JSONResponse(
            content={
                "auth_required": True,
                "authenticated": authenticated,
            }
        )

    return router
