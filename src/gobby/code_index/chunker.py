"""File content chunker for full-text search indexing.

Splits file content into overlapping line-based chunks suitable for
FTS5 indexing. Each chunk captures ~100 lines with 10-line overlap
so search hits near chunk boundaries aren't lost.
"""

from __future__ import annotations

from gobby.code_index.models import ContentChunk

# Chunk parameters
CHUNK_SIZE = 100  # lines per chunk
CHUNK_OVERLAP = 10  # overlap between consecutive chunks


def chunk_file_content(
    source: bytes,
    rel_path: str,
    project_id: str,
    language: str | None = None,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[ContentChunk]:
    """Split file content into overlapping chunks.

    Args:
        source: Raw file bytes.
        rel_path: File path relative to project root.
        project_id: Project identifier.
        language: Language name (e.g., "python", "typescript").
        chunk_size: Lines per chunk.
        overlap: Lines of overlap between consecutive chunks.

    Returns:
        List of ContentChunk objects ready for storage.
    """
    try:
        text = source.decode("utf-8", errors="replace")
    except Exception:
        return []

    lines = text.splitlines(keepends=True)
    if not lines:
        return []

    chunks: list[ContentChunk] = []
    step = max(1, chunk_size - overlap)
    chunk_index = 0

    for start in range(0, len(lines), step):
        end = min(start + chunk_size, len(lines))
        chunk_content = "".join(lines[start:end])

        # Skip empty chunks
        if not chunk_content.strip():
            if end >= len(lines):
                break
            continue

        chunks.append(
            ContentChunk(
                id=ContentChunk.make_id(project_id, rel_path, chunk_index),
                project_id=project_id,
                file_path=rel_path,
                chunk_index=chunk_index,
                line_start=start + 1,  # 1-indexed
                line_end=end,  # 1-indexed inclusive
                content=chunk_content,
                language=language,
            )
        )
        chunk_index += 1

        if end >= len(lines):
            break

    return chunks
