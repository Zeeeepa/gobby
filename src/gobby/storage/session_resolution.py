"""Session reference resolution.

Resolves session references (#N, N, UUID, prefix) to UUIDs.
Extracted from LocalSessionManager.resolve_session_reference()
as part of the Strangler Fig decomposition.
"""

from __future__ import annotations

import uuid

from gobby.storage.database import DatabaseProtocol


def resolve_session_reference(db: DatabaseProtocol, ref: str, project_id: str | None = None) -> str:
    """
    Resolve a session reference to a UUID.

    Supports:
    - #N: Project-scoped Sequence Number (e.g., #1) - requires project_id
    - N: Integer string treated as #N (e.g., "1")
    - UUID: Full UUID
    - Prefix: UUID prefix (must be unambiguous)

    Args:
        db: Database connection.
        ref: Session reference string.
        project_id: Project ID for project-scoped #N lookup.
            Required when ref is #N format (raises ValueError if missing).

    Returns:
        Resolved Session UUID

    Raises:
        ValueError: If not found or ambiguous
    """
    if not ref:
        raise ValueError("Empty session reference")

    # #N or N format: seq_num lookup
    seq_num_ref = ref
    if ref.startswith("#"):
        seq_num_ref = ref[1:]

    if seq_num_ref.isdigit():
        seq_num = int(seq_num_ref)
        if not project_id:
            raise ValueError(
                f"Cannot resolve session #{seq_num}: project context is required "
                f"for #N lookups. Pass a full UUID or ensure project context is set."
            )
        row = db.fetchone(
            "SELECT id FROM sessions WHERE project_id = ? AND seq_num = ?",
            (project_id, seq_num),
        )
        if not row:
            raise ValueError(f"Session #{seq_num} not found in project")
        return str(row["id"])

    # Full UUID check
    try:
        uuid_obj = uuid.UUID(ref)
        is_valid_uuid = True
    except ValueError:
        is_valid_uuid = False

    if is_valid_uuid:
        # Verify the session exists in the database
        row = db.fetchone("SELECT id FROM sessions WHERE id = ?", (str(uuid_obj),))
        if not row:
            raise ValueError(f"Session '{ref}' not found")
        return str(uuid_obj)

    # Prefix matching

    # Prefix matching
    rows = db.fetchall("SELECT id FROM sessions WHERE id LIKE ? LIMIT 5", (f"{ref}%",))
    if not rows:
        raise ValueError(f"Session '{ref}' not found")
    if len(rows) > 1:
        matches = [str(r["id"]) for r in rows]
        raise ValueError(f"Ambiguous session '{ref}' matches: {', '.join(matches[:3])}...")

    return str(rows[0]["id"])
