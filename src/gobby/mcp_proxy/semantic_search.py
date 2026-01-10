"""
Semantic tool search using embeddings.

Provides infrastructure for embedding-based tool discovery:
- Tool embedding storage and retrieval
- Cosine similarity search
- Integration with OpenAI text-embedding-3-small model
"""

import hashlib
import logging
import math
import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)

# Default embedding model
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIM = 1536


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Cosine similarity score between -1 and 1
    """
    if len(vec1) != len(vec2):
        raise ValueError(f"Vector dimension mismatch: {len(vec1)} vs {len(vec2)}")

    dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=True))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


@dataclass
class SearchResult:
    """Represents a tool search result with similarity score."""

    tool_id: str
    server_name: str
    tool_name: str
    description: str | None
    similarity: float
    embedding_id: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tool_id": self.tool_id,
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "description": self.description,
            "similarity": round(self.similarity, 4),
        }


@dataclass
class ToolEmbedding:
    """Represents a tool's embedding vector with metadata."""

    id: int
    tool_id: str
    server_name: str
    project_id: str
    embedding: list[float]
    embedding_model: str
    embedding_dim: int
    text_hash: str
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: Any) -> "ToolEmbedding":
        """Create ToolEmbedding from database row."""
        # Decode embedding from BLOB
        embedding_blob = row["embedding"]
        embedding = list(struct.unpack(f"{row['embedding_dim']}f", embedding_blob))

        return cls(
            id=row["id"],
            tool_id=row["tool_id"],
            server_name=row["server_name"],
            project_id=row["project_id"],
            embedding=embedding,
            embedding_model=row["embedding_model"],
            embedding_dim=row["embedding_dim"],
            text_hash=row["text_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (excludes embedding for serialization)."""
        return {
            "id": self.id,
            "tool_id": self.tool_id,
            "server_name": self.server_name,
            "project_id": self.project_id,
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
            "text_hash": self.text_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _embedding_to_blob(embedding: list[float]) -> bytes:
    """Convert embedding list to binary BLOB."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def _compute_text_hash(text: str) -> str:
    """Compute SHA-256 hash of text for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _build_tool_text(
    name: str, description: str | None, input_schema: dict[str, Any] | None
) -> str:
    """
    Build text representation of a tool for embedding.

    Combines name, description, and parameter info into a single string
    that captures the tool's semantic meaning.
    """
    parts = [f"Tool: {name}"]

    if description:
        parts.append(f"Description: {description}")

    if input_schema:
        # Extract parameter names and descriptions
        properties = input_schema.get("properties", {})
        if properties:
            param_parts = []
            for param_name, param_def in properties.items():
                param_desc = param_def.get("description", "")
                param_type = param_def.get("type", "any")
                if param_desc:
                    param_parts.append(f"{param_name} ({param_type}): {param_desc}")
                else:
                    param_parts.append(f"{param_name} ({param_type})")
            if param_parts:
                parts.append("Parameters: " + ", ".join(param_parts))

    return "\n".join(parts)


class SemanticToolSearch:
    """
    Manages semantic search over MCP tools using embeddings.

    Provides:
    - Embedding storage and retrieval (tool_embeddings table)
    - Text hashing for change detection
    - Cosine similarity search (to be implemented)
    - Integration with embedding providers (to be implemented)
    """

    def __init__(
        self,
        db: DatabaseProtocol,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        embedding_dim: int = DEFAULT_EMBEDDING_DIM,
        openai_api_key: str | None = None,
    ):
        """
        Initialize semantic search manager.

        Args:
            db: Database connection
            embedding_model: Model name for embeddings (default: text-embedding-3-small)
            embedding_dim: Dimension of embedding vectors (default: 1536)
            openai_api_key: OpenAI API key (from config or environment)
        """
        self.db = db
        self.embedding_model = embedding_model
        self.embedding_dim = embedding_dim
        self._openai_api_key = openai_api_key

    def store_embedding(
        self,
        tool_id: str,
        server_name: str,
        project_id: str,
        embedding: list[float],
        text_hash: str,
    ) -> ToolEmbedding:
        """
        Store or update a tool embedding.

        Args:
            tool_id: ID of the tool in the tools table
            server_name: Name of the MCP server
            project_id: Project ID
            embedding: Embedding vector as list of floats
            text_hash: Hash of the text used to generate the embedding

        Returns:
            ToolEmbedding instance
        """
        now = datetime.now(UTC).isoformat()
        embedding_blob = _embedding_to_blob(embedding)

        self.db.execute(
            """
            INSERT INTO tool_embeddings (
                tool_id, server_name, project_id, embedding,
                embedding_model, embedding_dim, text_hash, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tool_id) DO UPDATE SET
                server_name = excluded.server_name,
                project_id = excluded.project_id,
                embedding = excluded.embedding,
                embedding_model = excluded.embedding_model,
                embedding_dim = excluded.embedding_dim,
                text_hash = excluded.text_hash,
                updated_at = excluded.updated_at
            """,
            (
                tool_id,
                server_name,
                project_id,
                embedding_blob,
                self.embedding_model,
                len(embedding),
                text_hash,
                now,
                now,
            ),
        )

        result = self.get_embedding(tool_id)
        if result is None:
            raise RuntimeError(f"Failed to retrieve embedding for tool {tool_id} after store")
        return result

    def get_embedding(self, tool_id: str) -> ToolEmbedding | None:
        """
        Get embedding for a tool.

        Args:
            tool_id: Tool ID

        Returns:
            ToolEmbedding or None if not found
        """
        row = self.db.fetchone(
            "SELECT * FROM tool_embeddings WHERE tool_id = ?",
            (tool_id,),
        )
        return ToolEmbedding.from_row(row) if row else None

    def get_embeddings_for_project(self, project_id: str) -> list[ToolEmbedding]:
        """
        Get all embeddings for a project.

        Args:
            project_id: Project ID

        Returns:
            List of ToolEmbedding instances
        """
        rows = self.db.fetchall(
            "SELECT * FROM tool_embeddings WHERE project_id = ?",
            (project_id,),
        )
        return [ToolEmbedding.from_row(row) for row in rows]

    def get_embeddings_for_server(self, server_name: str, project_id: str) -> list[ToolEmbedding]:
        """
        Get all embeddings for a server in a project.

        Args:
            server_name: Server name
            project_id: Project ID

        Returns:
            List of ToolEmbedding instances
        """
        rows = self.db.fetchall(
            "SELECT * FROM tool_embeddings WHERE server_name = ? AND project_id = ?",
            (server_name, project_id),
        )
        return [ToolEmbedding.from_row(row) for row in rows]

    def delete_embedding(self, tool_id: str) -> bool:
        """
        Delete embedding for a tool.

        Args:
            tool_id: Tool ID

        Returns:
            True if deleted, False if not found
        """
        cursor = self.db.execute(
            "DELETE FROM tool_embeddings WHERE tool_id = ?",
            (tool_id,),
        )
        return cursor.rowcount > 0

    def delete_embeddings_for_server(self, server_name: str, project_id: str) -> int:
        """
        Delete all embeddings for a server.

        Args:
            server_name: Server name
            project_id: Project ID

        Returns:
            Number of embeddings deleted
        """
        cursor = self.db.execute(
            "DELETE FROM tool_embeddings WHERE server_name = ? AND project_id = ?",
            (server_name, project_id),
        )
        return cursor.rowcount

    def needs_reembedding(
        self,
        tool_id: str,
        name: str,
        description: str | None,
        input_schema: dict[str, Any] | None,
    ) -> bool:
        """
        Check if a tool needs (re)embedding.

        Computes hash of the tool's text representation and compares
        to stored hash.

        Args:
            tool_id: Tool ID
            name: Tool name
            description: Tool description
            input_schema: Tool input schema

        Returns:
            True if embedding is missing or outdated
        """
        existing = self.get_embedding(tool_id)
        if not existing:
            return True

        current_hash = _compute_text_hash(_build_tool_text(name, description, input_schema))
        return existing.text_hash != current_hash

    def get_embedding_stats(self, project_id: str | None = None) -> dict[str, Any]:
        """
        Get statistics about stored embeddings.

        Args:
            project_id: Optional project filter

        Returns:
            Dict with count, servers, and model info
        """
        if project_id:
            count_row = self.db.fetchone(
                "SELECT COUNT(*) as count FROM tool_embeddings WHERE project_id = ?",
                (project_id,),
            )
            servers_rows = self.db.fetchall(
                """
                SELECT server_name, COUNT(*) as count
                FROM tool_embeddings
                WHERE project_id = ?
                GROUP BY server_name
                """,
                (project_id,),
            )
        else:
            count_row = self.db.fetchone("SELECT COUNT(*) as count FROM tool_embeddings", ())
            servers_rows = self.db.fetchall(
                """
                SELECT server_name, COUNT(*) as count
                FROM tool_embeddings
                GROUP BY server_name
                """,
                (),
            )

        return {
            "total_embeddings": count_row["count"] if count_row else 0,
            "by_server": {row["server_name"]: row["count"] for row in servers_rows},
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
        }

    @staticmethod
    def build_tool_text(
        name: str, description: str | None, input_schema: dict[str, Any] | None
    ) -> str:
        """
        Build text representation of a tool for embedding.

        Public wrapper for the module-level function.

        Args:
            name: Tool name
            description: Tool description
            input_schema: Tool input schema

        Returns:
            Text suitable for embedding
        """
        return _build_tool_text(name, description, input_schema)

    @staticmethod
    def compute_text_hash(text: str) -> str:
        """
        Compute hash of text for change detection.

        Public wrapper for the module-level function.

        Args:
            text: Text to hash

        Returns:
            16-character hex hash
        """
        return _compute_text_hash(text)

    async def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding for text using OpenAI.

        Requires OPENAI_API_KEY in environment (set by LiteLLM provider from config).

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats (1536 dimensions)

        Raises:
            RuntimeError: If OPENAI_API_KEY not set or embedding fails
        """
        import os

        api_key = self._openai_api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not configured. Add it to llm_providers.api_keys in config.yaml"
            )
        return await self._embed_text_litellm(text, api_key=api_key)

    async def _embed_text_litellm(self, text: str, api_key: str) -> list[float]:
        """Generate embedding using LiteLLM (OpenAI API).

        Args:
            text: Text to embed
            api_key: OpenAI API key (from Codex auth or environment)

        Returns:
            Embedding vector as list of floats
        """
        try:
            import litellm
        except ImportError as e:
            raise RuntimeError("litellm package not installed. Run: pip install litellm") from e

        try:
            response = await litellm.aembedding(
                model=self.embedding_model,
                input=[text],
                api_key=api_key,
            )
            embedding: list[float] = response.data[0]["embedding"]
            logger.debug(f"Generated embedding via LiteLLM with {len(embedding)} dimensions")
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding with LiteLLM: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}") from e

    async def embed_tool(
        self,
        tool_id: str,
        name: str,
        description: str | None,
        input_schema: dict[str, Any] | None,
        server_name: str,
        project_id: str,
        force: bool = False,
    ) -> ToolEmbedding | None:
        """
        Generate and store embedding for a tool.

        Checks if re-embedding is needed based on content hash.

        Args:
            tool_id: Tool ID
            name: Tool name
            description: Tool description
            input_schema: Tool input schema
            server_name: MCP server name
            project_id: Project ID
            force: Force re-embedding even if content unchanged

        Returns:
            ToolEmbedding if generated, None if skipped (already up-to-date)
        """
        # Check if we need to generate embedding
        if not force and not self.needs_reembedding(tool_id, name, description, input_schema):
            logger.debug(f"Tool {name} embedding is up-to-date, skipping")
            return None

        # Build text and generate embedding
        text = _build_tool_text(name, description, input_schema)
        text_hash = _compute_text_hash(text)

        embedding = await self.embed_text(text)

        # Store embedding
        return self.store_embedding(
            tool_id=tool_id,
            server_name=server_name,
            project_id=project_id,
            embedding=embedding,
            text_hash=text_hash,
        )

    async def embed_all_tools(
        self,
        project_id: str,
        mcp_manager: Any,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Generate embeddings for all tools in a project.

        Iterates through all MCP servers and their tools, generating
        embeddings for tools that need them.

        Args:
            project_id: Project ID
            mcp_manager: LocalMCPManager instance for accessing tools
            force: Force re-embedding all tools

        Returns:
            Dict with statistics: embedded, skipped, failed, by_server
        """
        from gobby.storage.mcp import LocalMCPManager

        if not isinstance(mcp_manager, LocalMCPManager):
            raise TypeError("mcp_manager must be a LocalMCPManager instance")

        stats: dict[str, Any] = {
            "embedded": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
            "by_server": {},
        }

        # Get all servers for the project
        servers = mcp_manager.list_servers(project_id=project_id, enabled_only=False)

        for server in servers:
            server_stats = {"embedded": 0, "skipped": 0, "failed": 0}

            # Get tools for this server
            tools = mcp_manager.get_cached_tools(server.name, project_id=project_id)

            for tool in tools:
                try:
                    result = await self.embed_tool(
                        tool_id=tool.id,
                        name=tool.name,
                        description=tool.description,
                        input_schema=tool.input_schema,
                        server_name=server.name,
                        project_id=project_id,
                        force=force,
                    )

                    if result:
                        server_stats["embedded"] += 1
                        stats["embedded"] += 1
                        logger.info(f"Embedded tool: {server.name}/{tool.name}")
                    else:
                        server_stats["skipped"] += 1
                        stats["skipped"] += 1

                except Exception as e:
                    server_stats["failed"] += 1
                    stats["failed"] += 1
                    error_msg = f"{server.name}/{tool.name}: {e}"
                    stats["errors"].append(error_msg)
                    logger.error(f"Failed to embed tool {error_msg}")

            stats["by_server"][server.name] = server_stats

        return stats

    async def search_tools(
        self,
        query: str,
        project_id: str,
        top_k: int = 10,
        min_similarity: float = 0.0,
        server_filter: str | None = None,
    ) -> list[SearchResult]:
        """
        Search for tools semantically similar to a query.

        Embeds the query and computes cosine similarity against all
        stored tool embeddings, returning ranked results.

        Args:
            query: Search query text
            project_id: Project ID to search within
            top_k: Maximum number of results to return
            min_similarity: Minimum similarity threshold (0.0 to 1.0)
            server_filter: Optional server name to filter results

        Returns:
            List of SearchResult sorted by similarity (descending)
        """
        # Embed the query
        query_embedding = await self.embed_text(query)

        # Get all embeddings for the project
        if server_filter:
            embeddings = self.get_embeddings_for_server(server_filter, project_id)
        else:
            embeddings = self.get_embeddings_for_project(project_id)

        if not embeddings:
            logger.debug(f"No embeddings found for project {project_id}")
            return []

        # Get tool metadata for results
        tool_info = self._get_tool_info_map(project_id, server_filter)

        # Compute similarities
        results: list[SearchResult] = []
        for emb in embeddings:
            similarity = _cosine_similarity(query_embedding, emb.embedding)

            if similarity >= min_similarity:
                tool_data = tool_info.get(emb.tool_id, {})
                results.append(
                    SearchResult(
                        tool_id=emb.tool_id,
                        server_name=emb.server_name,
                        tool_name=tool_data.get("name", "unknown"),
                        description=tool_data.get("description"),
                        similarity=similarity,
                        embedding_id=emb.id,
                    )
                )

        # Sort by similarity descending and limit
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:top_k]

    def _get_tool_info_map(
        self, project_id: str, server_filter: str | None = None
    ) -> dict[str, dict[str, Any]]:
        """
        Get tool metadata map for search results.

        Args:
            project_id: Project ID
            server_filter: Optional server name filter

        Returns:
            Dict mapping tool_id to {name, description}
        """
        if server_filter:
            query = """
                SELECT t.id, t.name, t.description
                FROM tools t
                JOIN mcp_servers s ON t.mcp_server_id = s.id
                WHERE s.project_id = ? AND s.name = ?
            """
            rows = self.db.fetchall(query, (project_id, server_filter))
        else:
            query = """
                SELECT t.id, t.name, t.description
                FROM tools t
                JOIN mcp_servers s ON t.mcp_server_id = s.id
                WHERE s.project_id = ?
            """
            rows = self.db.fetchall(query, (project_id,))

        return {row["id"]: {"name": row["name"], "description": row["description"]} for row in rows}
