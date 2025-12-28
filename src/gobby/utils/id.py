"""ID generation utilities."""

import hashlib
import uuid


def generate_prefixed_id(prefix: str, content: str | None = None, length: int = 8) -> str:
    """
    Generate a prefixed ID (e.g., 'mm-a1b2c3d4').

    If content is provided, the ID is deterministic based on the content hash.
    If content is None, a random UUID is used.

    Args:
        prefix: The prefix for the ID (e.g., 'mm', 'sk')
        content: Optional content to hash for deterministic IDs
        length: Length of the hash part (default: 8)

    Returns:
        Formatted ID string
        Raises:
        ValueError: If prefix is empty or length is invalid
    """
    if not prefix:
        raise ValueError("prefix cannot be empty")
    if length <= 0:
        raise ValueError("length must be positive")
    if length > 64:  # SHA-256 produces 64 hex characters
        raise ValueError("length cannot exceed 64")

    if content is not None:
        hash_obj = hashlib.sha256(content.encode("utf-8"))
        hash_hex = hash_obj.hexdigest()[:length]
    else:
        # Use random UUID if no content provided
        hash_hex = uuid.uuid4().hex[:length]

    return f"{prefix}-{hash_hex}"
