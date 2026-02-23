"""Authentication store for web UI sessions.

Manages auth sessions in SQLite for cookie-based login.
Passwords are hashed with PBKDF2-SHA256 (stdlib, no external deps).
Sessions are random tokens with expiry.
"""

import hashlib
import logging
import os
from datetime import UTC, datetime, timedelta

from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)

# Session durations
SESSION_DURATION = timedelta(hours=12)  # Default (no remember-me)
REMEMBER_ME_DURATION = timedelta(days=30)  # Remember me checked

# PBKDF2 params for password hashing
_HASH_ITERATIONS = 600_000
_HASH_ALGO = "sha256"
_SALT_LENGTH = 32


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-SHA256.

    Returns a string in the format: `pbkdf2:iterations:salt_hex:hash_hex`
    """
    salt = os.urandom(_SALT_LENGTH)
    dk = hashlib.pbkdf2_hmac(_HASH_ALGO, password.encode(), salt, _HASH_ITERATIONS)
    return f"pbkdf2:{_HASH_ITERATIONS}:{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a PBKDF2 hash string."""
    try:
        parts = stored_hash.split(":")
        if len(parts) != 4 or parts[0] != "pbkdf2":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected = bytes.fromhex(parts[3])
        dk = hashlib.pbkdf2_hmac(_HASH_ALGO, password.encode(), salt, iterations)
        return dk == expected
    except (ValueError, IndexError):
        return False


class AuthStore:
    """Manages auth sessions in SQLite.

    Table is created lazily on first use.
    """

    def __init__(self, db: DatabaseProtocol) -> None:
        self.db = db
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create the auth_sessions table if it doesn't exist."""
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS auth_sessions (
                token TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at TEXT NOT NULL,
                remember_me INTEGER NOT NULL DEFAULT 0
            )"""
        )

    def create_session(self, remember_me: bool = False) -> tuple[str, datetime]:
        """Create a new auth session.

        Returns:
            Tuple of (token, expires_at)
        """
        token = os.urandom(32).hex()
        duration = REMEMBER_ME_DURATION if remember_me else SESSION_DURATION
        expires_at = datetime.now(UTC) + duration

        self.db.execute(
            "INSERT INTO auth_sessions (token, expires_at, remember_me) VALUES (?, ?, ?)",
            (token, expires_at.isoformat(), 1 if remember_me else 0),
        )

        # Opportunistically clean up expired sessions
        self._cleanup_expired()

        return token, expires_at

    def validate_session(self, token: str) -> bool:
        """Check if a session token is valid (exists and not expired)."""
        if not token:
            return False

        row = self.db.fetchone(
            "SELECT expires_at FROM auth_sessions WHERE token = ?",
            (token,),
        )
        if not row:
            return False

        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if datetime.now(UTC) > expires_at:
            self.delete_session(token)
            return False

        return True

    def delete_session(self, token: str) -> bool:
        """Delete a session (logout)."""
        self.db.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
        return True

    def _cleanup_expired(self) -> None:
        """Remove expired sessions."""
        now = datetime.now(UTC).isoformat()
        self.db.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (now,))
