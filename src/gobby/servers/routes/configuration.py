"""
Configuration routes for Gobby HTTP server.

Provides endpoints for:
- Structured config form (schema + values)
- Secrets management (encrypted API keys)
- Prompt template management (view/override/revert)
- Raw YAML editing
- Export/import configuration bundles
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gobby.config.app import (
    DaemonConfig,
    deep_merge,
)
from gobby.prompts.loader import DEFAULTS_DIR, PromptLoader
from gobby.storage.config_store import ConfigStore, flatten_config, unflatten_config
from gobby.storage.secrets import VALID_CATEGORIES, SecretStore
from gobby.utils.metrics import get_metrics_collector

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)

GLOBAL_PROMPTS_DIR = Path("~/.gobby/prompts").expanduser()


# =============================================================================
# Request models
# =============================================================================


class SaveConfigRequest(BaseModel):
    """Request body for PUT /api/config/values."""

    values: dict[str, Any]


class SaveTemplateRequest(BaseModel):
    """Request body for PUT /api/config/template."""

    content: str


class SaveSecretRequest(BaseModel):
    """Request body for POST /api/config/secrets."""

    name: str
    value: str
    category: str = "general"
    description: str | None = None


class SavePromptOverrideRequest(BaseModel):
    """Request body for PUT /api/config/prompts/{path}."""

    content: str


class ImportConfigRequest(BaseModel):
    """Request body for POST /api/config/import."""

    config_store: dict[str, Any] | None = None
    config: dict[str, Any] | None = None  # Legacy: nested config dict (flattened on import)
    prompts: dict[str, str] | None = None


# =============================================================================
# Router
# =============================================================================


def create_configuration_router(server: "HTTPServer") -> APIRouter:
    """Create the configuration API router."""
    router = APIRouter(prefix="/api/config", tags=["configuration"])
    metrics = get_metrics_collector()

    def _get_secret_store() -> SecretStore:
        from gobby.storage.database import LocalDatabase

        db = server.services.database
        if not isinstance(db, LocalDatabase):
            raise HTTPException(status_code=503, detail="Database not available")
        return SecretStore(db)

    def _get_config_store() -> ConfigStore:
        store = getattr(server.services, "config_store", None)
        if store is None:
            from gobby.storage.database import LocalDatabase

            db = server.services.database
            if not isinstance(db, LocalDatabase):
                raise HTTPException(status_code=503, detail="Database not available")
            store = ConfigStore(db)
        return store

    def _get_prompt_loader() -> PromptLoader:
        return PromptLoader(global_dir=Path.home() / ".gobby")

    # =========================================================================
    # Schema + Config values
    # =========================================================================

    @router.get("/schema")
    async def get_config_schema() -> JSONResponse:
        """Return the JSON Schema for DaemonConfig."""
        metrics.inc_counter("http_requests_total")
        schema = DaemonConfig.model_json_schema()
        return JSONResponse(content=schema)

    @router.get("/values")
    async def get_config_values() -> JSONResponse:
        """Return current config as nested dict."""
        metrics.inc_counter("http_requests_total")
        config = server.services.config
        values = config.model_dump(mode="json", exclude_none=True)
        return JSONResponse(content=values)

    @router.put("/values")
    async def save_config_values(request: SaveConfigRequest) -> JSONResponse:
        """Validate partial update, merge with existing, persist to DB.

        Returns {ok: true, requires_restart: true} on success.
        """
        metrics.inc_counter("http_requests_total")
        try:
            # Load current config as dict
            current = server.services.config.model_dump(mode="json", exclude_none=True)

            # Deep merge: update current with new values
            deep_merge(current, request.values)

            # Validate the merged config
            new_config = DaemonConfig(**current)

            # Persist to DB: flatten the incoming partial update and store
            config_store = _get_config_store()
            flat_updates = flatten_config(request.values)
            count = config_store.set_many(flat_updates, source="user")
            logger.info(f"Config saved to DB ({count} keys)")

            # Update in-memory config so subsequent reads reflect the change
            server.services.config = new_config

            return JSONResponse(
                content={
                    "ok": True,
                    "requires_restart": True,
                }
            )
        except Exception as e:
            logger.error(f"Config save failed: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/values/validate")
    async def validate_config(request: SaveConfigRequest) -> JSONResponse:
        """Validate config without saving."""
        metrics.inc_counter("http_requests_total")
        try:
            current = server.services.config.model_dump(mode="json", exclude_none=True)
            deep_merge(current, request.values)
            DaemonConfig(**current)
            return JSONResponse(content={"valid": True, "errors": []})
        except Exception as e:
            return JSONResponse(content={"valid": False, "errors": [str(e)]})

    @router.post("/values/reset")
    async def reset_config() -> JSONResponse:
        """Reset config to defaults (clear DB config_store)."""
        metrics.inc_counter("http_requests_total")
        try:
            config_store = _get_config_store()
            deleted = config_store.delete_all()
            logger.info(f"Config reset: deleted {deleted} keys from config_store")
            server.services.config = DaemonConfig()
            return JSONResponse(content={"ok": True, "requires_restart": True})
        except Exception as e:
            logger.error(f"Config reset failed: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    # =========================================================================
    # Template (full defaults + DB overrides as YAML)
    # =========================================================================

    @router.get("/template")
    async def get_config_template() -> JSONResponse:
        """Return full Pydantic defaults merged with current DB overrides as YAML.

        Shows every available config option with current values highlighted.
        """
        metrics.inc_counter("http_requests_total")
        try:
            defaults = DaemonConfig().model_dump(mode="json", exclude_none=True)
            config_store = _get_config_store()
            db_overrides = unflatten_config(config_store.get_all())
            deep_merge(defaults, db_overrides)
            content = yaml.safe_dump(defaults, default_flow_style=False, sort_keys=False)
            return JSONResponse(content={"content": content})
        except Exception as e:
            logger.error(f"Failed to generate config template: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.put("/template")
    async def save_config_template(request: SaveTemplateRequest) -> JSONResponse:
        """Accept YAML, diff against defaults, store only non-default values to DB."""
        metrics.inc_counter("http_requests_total")
        try:
            parsed = yaml.safe_load(request.content)
            if parsed is None:
                parsed = {}
            if not isinstance(parsed, dict):
                raise ValueError("YAML must be a mapping (dict), not a scalar or list")

            # Validate as DaemonConfig
            new_config = DaemonConfig(**parsed)

            # Diff against defaults: only store non-default values
            defaults_flat = flatten_config(
                DaemonConfig().model_dump(mode="json", exclude_none=True)
            )
            parsed_flat = flatten_config(parsed)
            diff = {
                k: v
                for k, v in parsed_flat.items()
                if k not in defaults_flat or defaults_flat[k] != v
            }

            config_store = _get_config_store()
            with config_store.db.transaction():
                config_store.delete_all()
                count = config_store.set_many(diff, source="user") if diff else 0
            logger.info(f"Template saved: {count} non-default keys stored")

            server.services.config = new_config

            return JSONResponse(content={"ok": True, "requires_restart": True})
        except yaml.YAMLError as e:
            raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}") from e
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    # =========================================================================
    # Secrets
    # =========================================================================

    @router.get("/secrets")
    async def list_secrets() -> JSONResponse:
        """List all secrets (metadata only, never values)."""
        metrics.inc_counter("http_requests_total")
        try:
            store = _get_secret_store()
            secrets = store.list()
            return JSONResponse(
                content={
                    "secrets": [s.to_dict() for s in secrets],
                    "categories": sorted(VALID_CATEGORIES),
                }
            )
        except Exception as e:
            logger.error(f"Failed to list secrets: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/secrets")
    async def save_secret(request: SaveSecretRequest) -> JSONResponse:
        """Create or update a secret."""
        metrics.inc_counter("http_requests_total")
        try:
            store = _get_secret_store()
            info = store.set(
                name=request.name,
                plaintext_value=request.value,
                category=request.category,
                description=request.description,
            )
            return JSONResponse(content={"ok": True, "secret": info.to_dict()})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Failed to save secret: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.delete("/secrets/{name}")
    async def delete_secret(name: str) -> JSONResponse:
        """Delete a secret by name."""
        metrics.inc_counter("http_requests_total")
        try:
            store = _get_secret_store()
            if not store.delete(name):
                raise HTTPException(status_code=404, detail=f"Secret '{name}' not found")
            return JSONResponse(content={"ok": True})
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete secret: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    # =========================================================================
    # Prompts
    # =========================================================================

    @router.get("/prompts")
    async def list_prompts() -> JSONResponse:
        """List all prompts with category, source tier, override status."""
        metrics.inc_counter("http_requests_total")
        try:
            loader = _get_prompt_loader()
            template_paths = loader.list_templates()

            prompts = []
            for path in template_paths:
                template = loader.load(path)
                # Determine source tier
                source = "bundled"
                if template.source_path:
                    source_str = str(template.source_path)
                    if str(GLOBAL_PROMPTS_DIR) in source_str:
                        source = "overridden"

                # Extract category from path
                category = path.split("/")[0] if "/" in path else "general"

                prompts.append(
                    {
                        "path": path,
                        "description": template.description,
                        "category": category,
                        "source": source,
                        "has_override": source == "overridden",
                    }
                )

            # Build category counts
            categories: dict[str, int] = {}
            for p in prompts:
                cat = str(p["category"])
                categories[cat] = categories.get(cat, 0) + 1

            return JSONResponse(
                content={
                    "prompts": prompts,
                    "categories": categories,
                    "total": len(prompts),
                }
            )
        except Exception as e:
            logger.error(f"Failed to list prompts: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/prompts/{path:path}")
    async def get_prompt_detail(path: str) -> JSONResponse:
        """Get prompt content and frontmatter."""
        metrics.inc_counter("http_requests_total")
        try:
            loader = _get_prompt_loader()
            template = loader.load(path)

            # Determine source
            source = "bundled"
            override_path = GLOBAL_PROMPTS_DIR / f"{path}.md"
            has_override = override_path.exists()
            if (
                has_override
                and template.source_path
                and str(GLOBAL_PROMPTS_DIR) in str(template.source_path)
            ):
                source = "overridden"

            # Get bundled content for comparison if overridden
            bundled_content = None
            if has_override:
                bundled_path = DEFAULTS_DIR / f"{path}.md"
                if bundled_path.exists():
                    bundled_content = bundled_path.read_text(encoding="utf-8")

            return JSONResponse(
                content={
                    "path": path,
                    "description": template.description,
                    "content": template.content,
                    "source": source,
                    "has_override": has_override,
                    "bundled_content": bundled_content,
                    "variables": {
                        name: {
                            "type": spec.type,
                            "required": spec.required,
                            "default": spec.default,
                        }
                        for name, spec in template.variables.items()
                    },
                }
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=f"Prompt '{path}' not found") from e
        except Exception as e:
            logger.error(f"Failed to get prompt: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.put("/prompts/{path:path}")
    async def save_prompt_override(path: str, request: SavePromptOverrideRequest) -> JSONResponse:
        """Create/update a prompt override in ~/.gobby/prompts/."""
        metrics.inc_counter("http_requests_total")
        try:
            override_path = GLOBAL_PROMPTS_DIR / f"{path}.md"
            override_path.parent.mkdir(parents=True, exist_ok=True)
            override_path.write_text(request.content, encoding="utf-8")

            # Clear loader cache so next load picks up the override
            loader = _get_prompt_loader()
            loader.clear_cache()

            return JSONResponse(content={"ok": True})
        except Exception as e:
            logger.error(f"Failed to save prompt override: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.delete("/prompts/{path:path}")
    async def delete_prompt_override(path: str) -> JSONResponse:
        """Remove override (revert to bundled)."""
        metrics.inc_counter("http_requests_total")
        try:
            override_path = GLOBAL_PROMPTS_DIR / f"{path}.md"
            if not override_path.exists():
                raise HTTPException(status_code=404, detail=f"No override for '{path}'")
            override_path.unlink()

            # Clear loader cache
            loader = _get_prompt_loader()
            loader.clear_cache()

            return JSONResponse(content={"ok": True})
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete prompt override: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    # =========================================================================
    # Export / Import
    # =========================================================================

    @router.post("/export")
    async def export_config() -> JSONResponse:
        """Bundle config_store + prompt overrides + secret names (not values)."""
        metrics.inc_counter("http_requests_total")
        try:
            # Config from DB (flat key-value pairs)
            config_store = _get_config_store()
            flat_config = config_store.get_all()

            # Prompt overrides
            prompt_overrides: dict[str, str] = {}
            if GLOBAL_PROMPTS_DIR.exists():
                for md_file in GLOBAL_PROMPTS_DIR.rglob("*.md"):
                    rel = str(md_file.relative_to(GLOBAL_PROMPTS_DIR))
                    prompt_overrides[rel] = md_file.read_text(encoding="utf-8")

            # Secret names only
            store = _get_secret_store()
            secret_names = [s.to_dict() for s in store.list()]

            return JSONResponse(
                content={
                    "exported_at": datetime.now(UTC).isoformat(),
                    "config_store": flat_config,
                    "prompts": prompt_overrides,
                    "secrets": secret_names,  # Names and metadata only, never values
                }
            )
        except Exception as e:
            logger.error(f"Config export failed: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/import")
    async def import_config(request: ImportConfigRequest) -> JSONResponse:
        """Import config bundle (config_store + prompts, secrets must be re-entered).

        Accepts either:
        - config_store: flat key-value dict (preferred, from export)
        - config: nested config dict (legacy, flattened on import)
        """
        metrics.inc_counter("http_requests_total")
        summary_parts: list[str] = []
        config_imported = False
        try:
            config_store = _get_config_store()

            # Import flat config_store (preferred)
            if request.config_store:
                # Validate by unflattening and creating DaemonConfig
                nested = unflatten_config(request.config_store)
                DaemonConfig(**nested)
                with config_store.db.transaction():
                    config_store.delete_all()
                    count = config_store.set_many(request.config_store, source="import")
                summary_parts.append(f"config restored ({count} keys)")
                config_imported = True

            # Legacy: import nested config dict
            elif request.config:
                DaemonConfig(**request.config)  # Validate first
                flat = flatten_config(request.config)
                # Diff against defaults so we only store overrides
                defaults_flat = flatten_config(
                    DaemonConfig().model_dump(mode="json", exclude_none=True)
                )
                diff = {
                    k: v for k, v in flat.items() if k not in defaults_flat or defaults_flat[k] != v
                }
                with config_store.db.transaction():
                    config_store.delete_all()
                    count = config_store.set_many(diff, source="import") if diff else 0
                summary_parts.append(f"config restored ({count} keys)")
                config_imported = True

            # Import prompt overrides
            if request.prompts:
                for rel_path, content in request.prompts.items():
                    override_path = GLOBAL_PROMPTS_DIR / rel_path
                    override_path.parent.mkdir(parents=True, exist_ok=True)
                    override_path.write_text(content, encoding="utf-8")
                summary_parts.append(f"{len(request.prompts)} prompt override(s) restored")

            return JSONResponse(
                content={
                    "success": True,
                    "summary": ", ".join(summary_parts) if summary_parts else "nothing to import",
                    "requires_restart": config_imported,
                }
            )
        except Exception as e:
            logger.error(f"Config import failed: {e}")
            raise HTTPException(status_code=400, detail=str(e)) from e

    return router
