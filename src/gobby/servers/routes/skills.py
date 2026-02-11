"""
Skills routes for Gobby HTTP server.

Provides CRUD, search, stats, import/export, safety scanning,
and hub browsing/install endpoints for the skill system.
"""

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from gobby.utils.metrics import get_metrics_collector

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


# =============================================================================
# Request/Response models
# =============================================================================


class SkillCreateRequest(BaseModel):
    """Request body for creating a skill."""

    name: str = Field(..., description="Skill name (max 64 chars, lowercase+hyphens)")
    description: str = Field(..., description="Skill description (max 1024 chars)")
    content: str = Field(..., description="Full markdown content")
    version: str | None = Field(default=None, description="Semantic version string")
    license: str | None = Field(default=None, description="License identifier")
    compatibility: str | None = Field(default=None, description="Compatibility notes")
    allowed_tools: list[str] | None = Field(default=None, description="Allowed tool patterns")
    metadata: dict[str, Any] | None = Field(default=None, description="Free-form metadata")
    enabled: bool = Field(default=True, description="Whether skill is active")
    always_apply: bool = Field(default=False, description="Always inject at session start")
    injection_format: str = Field(default="summary", description="Injection format")
    project_id: str | None = Field(default=None, description="Project scope (None for global)")


class SkillUpdateRequest(BaseModel):
    """Request body for updating a skill."""

    name: str | None = Field(default=None, description="New name")
    description: str | None = Field(default=None, description="New description")
    content: str | None = Field(default=None, description="New content")
    version: str | None = Field(default=None, description="New version")
    license: str | None = Field(default=None, description="New license")
    compatibility: str | None = Field(default=None, description="New compatibility")
    allowed_tools: list[str] | None = Field(default=None, description="New allowed tools")
    metadata: dict[str, Any] | None = Field(default=None, description="New metadata")
    enabled: bool | None = Field(default=None, description="New enabled state")
    always_apply: bool | None = Field(default=None, description="New always_apply state")
    injection_format: str | None = Field(default=None, description="New injection format")


class SkillImportRequest(BaseModel):
    """Request body for importing a skill from a source."""

    source: str = Field(..., description="GitHub URL, ZIP path, or local path")
    project_id: str | None = Field(default=None, description="Project scope")


class SkillScanRequest(BaseModel):
    """Request body for scanning skill content for safety."""

    content: str = Field(..., description="Skill markdown content to scan")
    name: str = Field(default="untitled", description="Skill name for reporting")


class HubInstallRequest(BaseModel):
    """Request body for installing a skill from a hub."""

    hub_name: str = Field(..., description="Hub name to install from")
    slug: str = Field(..., description="Skill slug on the hub")
    version: str | None = Field(default=None, description="Specific version")
    project_id: str | None = Field(default=None, description="Project scope")


# =============================================================================
# Router
# =============================================================================


def create_skills_router(server: "HTTPServer") -> APIRouter:
    """Create skills router with endpoints bound to server instance."""
    router = APIRouter(prefix="/skills", tags=["skills"])
    metrics = get_metrics_collector()

    @router.get("")
    def list_skills(
        project_id: str | None = Query(None, description="Filter by project ID"),
        enabled: bool | None = Query(None, description="Filter by enabled state"),
        category: str | None = Query(None, description="Filter by category"),
        limit: int = Query(50, description="Maximum results"),
        offset: int = Query(0, description="Pagination offset"),
    ) -> dict[str, Any]:
        """List skills with optional filters."""
        metrics.inc_counter("http_requests_total")
        try:
            skills = server.skill_manager.list_skills(
                project_id=project_id,
                enabled=enabled,
                category=category,
                limit=limit,
                offset=offset,
            )
            return {"skills": [s.to_dict() for s in skills]}
        except Exception as e:
            logger.error(f"Failed to list skills: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("", status_code=201)
    def create_skill(request_data: SkillCreateRequest) -> Any:
        """Create a new skill."""
        metrics.inc_counter("http_requests_total")
        try:
            skill = server.skill_manager.create_skill(
                name=request_data.name,
                description=request_data.description,
                content=request_data.content,
                version=request_data.version,
                license=request_data.license,
                compatibility=request_data.compatibility,
                allowed_tools=request_data.allowed_tools,
                metadata=request_data.metadata,
                enabled=request_data.enabled,
                always_apply=request_data.always_apply,
                injection_format=request_data.injection_format,
                project_id=request_data.project_id,
                source_type="local",
            )
            return skill.to_dict()
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Failed to create skill: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/search")
    def search_skills(
        q: str = Query(..., description="Search query"),
        project_id: str | None = Query(None, description="Filter by project ID"),
        limit: int = Query(20, description="Maximum results"),
    ) -> dict[str, Any]:
        """Search skills by name and description."""
        metrics.inc_counter("http_requests_total")
        try:
            results = server.skill_manager.search_skills(
                query_text=q,
                project_id=project_id,
                limit=limit,
            )
            return {
                "query": q,
                "results": [s.to_dict() for s in results],
                "count": len(results),
            }
        except Exception as e:
            logger.error(f"Failed to search skills: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/stats")
    def skill_stats(
        project_id: str | None = Query(None, description="Filter by project ID"),
    ) -> Any:
        """Get skill statistics."""
        metrics.inc_counter("http_requests_total")
        try:
            total = server.skill_manager.count_skills(project_id=project_id)
            enabled = server.skill_manager.count_skills(project_id=project_id, enabled=True)
            disabled = server.skill_manager.count_skills(project_id=project_id, enabled=False)

            # Get all skills to compute by_category and by_source_type
            all_skills = server.skill_manager.list_skills(project_id=project_id, limit=1000)
            by_category: dict[str, int] = {}
            by_source_type: dict[str, int] = {}
            bundled_count = 0
            hub_count = 0
            for s in all_skills:
                cat = s.get_category() or "uncategorized"
                by_category[cat] = by_category.get(cat, 0) + 1
                st = s.source_type or "unknown"
                by_source_type[st] = by_source_type.get(st, 0) + 1
                if s.source_type == "filesystem":
                    bundled_count += 1
                if s.hub_name:
                    hub_count += 1

            return {
                "total": total,
                "enabled": enabled,
                "disabled": disabled,
                "bundled": bundled_count,
                "from_hubs": hub_count,
                "by_category": by_category,
                "by_source_type": by_source_type,
            }
        except Exception as e:
            logger.error(f"Failed to get skill stats: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/restore-defaults")
    def restore_defaults() -> dict[str, Any]:
        """Restore bundled skills to their default state."""
        metrics.inc_counter("http_requests_total")
        try:
            from gobby.skills.sync import sync_bundled_skills

            result = sync_bundled_skills(server.services.database)
            return result
        except Exception as e:
            logger.error(f"Failed to restore defaults: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/import")
    def import_skill(request_data: SkillImportRequest) -> dict[str, Any]:
        """Import a skill from GitHub, ZIP, or local path."""
        metrics.inc_counter("http_requests_total")
        try:
            from gobby.skills.loader import SkillLoader

            loader = SkillLoader()
            source = request_data.source.strip()

            # Detect source type and load
            if source.startswith(("github:", "https://github.com", "http://github.com")) or (
                "/" in source and not source.startswith("/") and not source.endswith(".zip")
            ):
                parsed = loader.load_from_github(source, validate=True)
            elif source.endswith(".zip"):
                parsed = loader.load_from_zip(source, validate=True)
            else:
                parsed = loader.load_skill(source, validate=True)

            # Handle single skill or list
            skills_list = parsed if isinstance(parsed, list) else [parsed]
            imported = []

            for ps in skills_list:
                try:
                    skill = server.skill_manager.create_skill(
                        name=ps.name,
                        description=ps.description,
                        content=ps.content,
                        version=ps.version,
                        license=ps.license,
                        compatibility=ps.compatibility,
                        allowed_tools=ps.allowed_tools,
                        metadata=ps.metadata,
                        source_path=ps.source_path,
                        source_type=ps.source_type or "local",
                        source_ref=ps.source_ref,
                        enabled=True,
                        always_apply=ps.always_apply,
                        injection_format=ps.injection_format,
                        project_id=request_data.project_id,
                    )
                    imported.append(skill.to_dict())
                except ValueError as e:
                    logger.warning(f"Skipping duplicate skill '{ps.name}': {e}")

            return {
                "imported": len(imported),
                "skills": imported,
            }
        except Exception as e:
            logger.error(f"Failed to import skill: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/scan")
    def scan_skill(request_data: SkillScanRequest) -> dict[str, Any]:
        """Run safety scan on skill content using Cisco skill-scanner."""
        metrics.inc_counter("http_requests_total")
        try:
            from gobby.skills.scanner import scan_skill_content

            result = scan_skill_content(
                content=request_data.content,
                name=request_data.name,
            )
            return result
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="skill-scanner package not installed. Install with: pip install skill-scanner",
            ) from None
        except Exception as e:
            logger.error(f"Failed to scan skill: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/hubs")
    def list_hubs() -> dict[str, Any]:
        """List configured skill hubs."""
        metrics.inc_counter("http_requests_total")
        if server.hub_manager is None:
            return {"hubs": []}
        try:
            hub_names = server.hub_manager.list_hubs()
            hubs = []
            for name in hub_names:
                try:
                    config = server.hub_manager.get_config(name)
                    hubs.append(
                        {
                            "name": name,
                            "type": config.type,
                            "base_url": config.base_url,
                            "repo": config.repo,
                        }
                    )
                except KeyError:
                    pass
            return {"hubs": hubs}
        except Exception as e:
            logger.error(f"Failed to list hubs: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/hubs/search")
    async def search_hubs(
        q: str = Query(..., description="Search query"),
        hub_name: str | None = Query(None, description="Specific hub to search"),
        limit: int = Query(20, description="Maximum results"),
    ) -> dict[str, Any]:
        """Search for skills across configured hubs."""
        metrics.inc_counter("http_requests_total")
        if server.hub_manager is None:
            return {"query": q, "results": [], "count": 0}
        try:
            hub_names = [hub_name] if hub_name else None
            results = await server.hub_manager.search_all(
                query=q,
                limit=limit,
                hub_names=hub_names,
            )
            return {
                "query": q,
                "results": results,
                "count": len(results),
            }
        except Exception as e:
            logger.error(f"Failed to search hubs: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/hubs/install")
    async def install_from_hub(request_data: HubInstallRequest) -> dict[str, Any]:
        """Download and install a skill from a hub."""
        metrics.inc_counter("http_requests_total")
        if server.hub_manager is None:
            raise HTTPException(status_code=404, detail="No hub manager configured")
        try:
            provider = server.hub_manager.get_provider(request_data.hub_name)
            download = await provider.download_skill(
                slug=request_data.slug,
                version=request_data.version,
            )

            if not download.success:
                raise HTTPException(
                    status_code=502,
                    detail=f"Download failed: {download.error}",
                )

            # Load the downloaded skill and store it
            from gobby.skills.loader import SkillLoader

            loader = SkillLoader(default_source_type="hub")
            parsed = loader.load_skill(download.path, validate=True, check_dir_name=False)

            skill = server.skill_manager.create_skill(
                name=parsed.name,
                description=parsed.description,
                content=parsed.content,
                version=parsed.version or download.version,
                license=parsed.license,
                compatibility=parsed.compatibility,
                allowed_tools=parsed.allowed_tools,
                metadata=parsed.metadata,
                source_path=f"hub:{request_data.hub_name}/{request_data.slug}",
                source_type="hub",
                hub_name=request_data.hub_name,
                hub_slug=request_data.slug,
                hub_version=download.version,
                enabled=True,
                always_apply=parsed.always_apply,
                injection_format=parsed.injection_format,
                project_id=request_data.project_id,
            )
            return {"installed": True, "skill": skill.to_dict()}
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Failed to install from hub: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/{skill_id}")
    def get_skill(skill_id: str) -> Any:
        """Get a specific skill by ID."""
        metrics.inc_counter("http_requests_total")
        try:
            skill = server.skill_manager.get_skill(skill_id)
            return skill.to_dict()
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Failed to get skill {skill_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.put("/{skill_id}")
    def update_skill(skill_id: str, request_data: SkillUpdateRequest) -> Any:
        """Update an existing skill."""
        metrics.inc_counter("http_requests_total")
        try:
            skill = server.skill_manager.update_skill(
                skill_id=skill_id,
                name=request_data.name,
                description=request_data.description,
                content=request_data.content,
                version=request_data.version,
                license=request_data.license,
                compatibility=request_data.compatibility,
                allowed_tools=request_data.allowed_tools,
                metadata=request_data.metadata,
                enabled=request_data.enabled,
                always_apply=request_data.always_apply,
                injection_format=request_data.injection_format,
            )
            return skill.to_dict()
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Failed to update skill {skill_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.delete("/{skill_id}")
    def delete_skill(skill_id: str) -> dict[str, Any]:
        """Delete a skill."""
        metrics.inc_counter("http_requests_total")
        result = server.skill_manager.delete_skill(skill_id)
        if not result:
            raise HTTPException(status_code=404, detail="Skill not found")
        return {"deleted": True, "id": skill_id}

    @router.get("/{skill_id}/export")
    def export_skill(skill_id: str) -> dict[str, Any]:
        """Export a skill as SKILL.md content with frontmatter."""
        metrics.inc_counter("http_requests_total")
        try:
            skill = server.skill_manager.get_skill(skill_id)

            # Build frontmatter
            import yaml

            frontmatter: dict[str, Any] = {
                "name": skill.name,
                "description": skill.description,
            }
            if skill.version:
                frontmatter["version"] = skill.version
            if skill.license:
                frontmatter["license"] = skill.license
            if skill.compatibility:
                frontmatter["compatibility"] = skill.compatibility
            if skill.allowed_tools:
                frontmatter["allowed_tools"] = skill.allowed_tools
            if skill.metadata:
                frontmatter["metadata"] = skill.metadata

            fm_str = yaml.dump(frontmatter, default_flow_style=False).strip()
            export_content = f"---\n{fm_str}\n---\n\n{skill.content}"

            return {
                "skill_id": skill.id,
                "name": skill.name,
                "filename": f"{skill.name}/SKILL.md",
                "content": export_content,
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Failed to export skill {skill_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    return router
