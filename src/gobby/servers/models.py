"""
Pydantic models for HTTP server request/response schemas.
"""

from pydantic import BaseModel, Field


class SessionRegisterRequest(BaseModel):
    """Request model for session registration endpoint."""

    external_id: str = Field(
        ..., description="External session identifier (e.g., from Claude Code)"
    )
    machine_id: str | None = Field(None, description="Unique machine identifier")

    # Session metadata
    jsonl_path: str | None = Field(None, description="Path to JSONL transcript file")
    title: str | None = Field(None, description="Natural language session summary/title")
    source: str | None = Field(
        None, description="Session source (e.g., 'Claude Code', 'Agent SDK')"
    )
    parent_session_id: str | None = Field(
        None, description="Parent session ID for session lineage tracking"
    )
    status: str | None = Field(None, description="Session status (active, paused, etc.)")
    project_id: str | None = Field(None, description="Project ID to associate with session")
    project_path: str | None = Field(
        None, description="Project root directory path (for git extraction)"
    )
    git_branch: str | None = Field(None, description="Current git branch name")
    cwd: str | None = Field(None, description="Current working directory")
