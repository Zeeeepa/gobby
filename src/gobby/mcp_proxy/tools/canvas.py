"""
Internal MCP tools for Gobby Canvas and Artifact systems.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import shutil
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from gobby.cli.utils import get_gobby_home
from gobby.mcp_proxy.tools.internal import InternalToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class CanvasState:
    canvas_id: str
    mode: str  # "a2ui" or "html"
    surface: dict[str, Any]  # component map {id: component_def}
    data_model: dict[str, Any]  # bound data
    root_component_id: str | None
    html_url: str | None  # URL for html mode
    conversation_id: str
    pending_event: asyncio.Event | None
    interaction_result: dict[str, Any] | None
    created_at: datetime
    expires_at: datetime
    completed: bool = False


MAX_CANVASES_PER_CONVERSATION = 50
MAX_TOTAL_CANVASES = 1000
MAX_COMPONENT_COUNT = 200
MAX_DATA_MODEL_SIZE = 64 * 1024  # 64KB
MAX_RENDER_RATE = 10  # per minute per conversation
CANVAS_DEFAULT_TIMEOUT = 300.0  # 5 minutes
CANVAS_MAX_TIMEOUT = 600.0  # 10 minutes
A2UI_CATALOG = {
    "Text",
    "Button",
    "TextField",
    "CheckBox",
    "Row",
    "Column",
    "Card",
    "List",
    "Image",
    "Icon",
    "Badge",
}

_canvases: dict[str, CanvasState] = {}
_canvas_locks: dict[str, asyncio.Lock] = {}
_rate_counters: dict[str, list[float]] = {}
_broadcaster_ref: dict[str, Any] = {"func": None}
_artifact_broadcaster_ref: dict[str, Any] = {"func": None}

# File size limits for show_file
MAX_TEXT_FILE_SIZE = 1 * 1024 * 1024  # 1MB
MAX_IMAGE_FILE_SIZE = 5 * 1024 * 1024  # 5MB

# Extension → (artifact_type, language)
EXTENSION_MAP: dict[str, tuple[str, str | None]] = {
    ".md": ("text", "markdown"),
    ".txt": ("text", "plaintext"),
    ".rst": ("text", "plaintext"),
    ".adoc": ("text", "plaintext"),
    ".py": ("code", "python"),
    ".js": ("code", "javascript"),
    ".ts": ("code", "typescript"),
    ".tsx": ("code", "tsx"),
    ".jsx": ("code", "jsx"),
    ".rs": ("code", "rust"),
    ".go": ("code", "go"),
    ".java": ("code", "java"),
    ".json": ("code", "json"),
    ".yaml": ("code", "yaml"),
    ".yml": ("code", "yaml"),
    ".toml": ("code", "toml"),
    ".html": ("code", "html"),
    ".css": ("code", "css"),
    ".sql": ("code", "sql"),
    ".sh": ("code", "shell"),
    ".bash": ("code", "shell"),
    ".zsh": ("code", "shell"),
    ".c": ("code", "c"),
    ".cpp": ("code", "cpp"),
    ".h": ("code", "c"),
    ".rb": ("code", "ruby"),
    ".php": ("code", "php"),
    ".swift": ("code", "swift"),
    ".kt": ("code", "kotlin"),
    ".scala": ("code", "scala"),
    ".r": ("code", "r"),
    ".lua": ("code", "lua"),
    ".xml": ("code", "xml"),
    ".csv": ("sheet", None),
    ".tsv": ("sheet", None),
    ".png": ("image", None),
    ".jpg": ("image", None),
    ".jpeg": ("image", None),
    ".gif": ("image", None),
    ".webp": ("image", None),
    ".svg": ("image", None),
}


def set_broadcaster(callback: Callable[..., Awaitable[None]] | None) -> None:
    """Set the canvas broadcaster after creation (wired in HTTP lifespan)."""
    _broadcaster_ref["func"] = callback


def set_artifact_broadcaster(callback: Callable[..., Awaitable[None]] | None) -> None:
    """Set the artifact broadcaster after creation (wired in HTTP lifespan)."""
    _artifact_broadcaster_ref["func"] = callback


def get_canvas(canvas_id: str) -> CanvasState | None:
    """Get canvas state by ID."""
    return _canvases.get(canvas_id)


def get_active_canvases(conversation_id: str) -> list[CanvasState]:
    """Get all active canvases for a conversation (for WebSocket connect rehydration)."""
    return [
        c for c in _canvases.values() if c.conversation_id == conversation_id and not c.completed
    ]


async def resolve_interaction(canvas_id: str, action: dict[str, Any]) -> bool:
    """Resolve an interaction for a canvas (first-wins semantics)."""
    if canvas_id not in _canvas_locks:
        _canvas_locks[canvas_id] = asyncio.Lock()

    async with _canvas_locks[canvas_id]:
        canvas = _canvases.get(canvas_id)
        if not canvas or canvas.completed:
            return False

        canvas.interaction_result = action
        canvas.completed = True
        if canvas.pending_event:
            canvas.pending_event.set()
        return True


def cancel_conversation_canvases(conversation_id: str) -> int:
    """Cancel all canvases for a conversation (for WebSocket disconnect)."""
    count = 0
    for canvas in _canvases.values():
        if canvas.conversation_id == conversation_id and not canvas.completed:
            canvas.completed = True
            canvas.interaction_result = {"error": "conversation_cancelled"}
            if canvas.pending_event:
                canvas.pending_event.set()
            count += 1
    return count


def sweep_expired() -> int:
    """Remove expired canvases."""
    now = datetime.now(UTC)
    expired_ids = [cid for cid, canvas in _canvases.items() if canvas.expires_at < now]
    for cid in expired_ids:
        canvas = _canvases.pop(cid)
        _cleanup_html_file(canvas)
        if not canvas.completed:
            canvas.completed = True
            canvas.interaction_result = {"error": "timeout"}
            if canvas.pending_event:
                canvas.pending_event.set()
        _canvas_locks.pop(cid, None)
    return len(expired_ids)


def _cleanup_html_file(canvas: CanvasState) -> None:
    """Delete the copied HTML file for an html-mode canvas."""
    if canvas.mode != "html" or not canvas.html_url:
        return
    # html_url is like /__gobby__/canvas/{uuid}.html — extract the filename
    filename = canvas.html_url.rsplit("/", 1)[-1]
    file_path = get_gobby_home() / "canvas" / filename
    try:
        file_path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning(f"Failed to clean up canvas HTML file {file_path}: {e}")


def _check_rate_limit(conversation_id: str) -> bool:
    now = time.time()
    timestamps = _rate_counters.get(conversation_id, [])
    # prune older than 60s
    timestamps = [t for t in timestamps if now - t < 60]
    _rate_counters[conversation_id] = timestamps

    if len(timestamps) >= MAX_RENDER_RATE:
        return False

    timestamps.append(now)
    return True


def _validate_components(components: dict[str, Any]) -> None:
    if len(components) > MAX_COMPONENT_COUNT:
        raise ValueError(f"Too many components: {len(components)} > {MAX_COMPONENT_COUNT}")
    for cid, comp in components.items():
        if "type" not in comp:
            raise ValueError(f"Component {cid} missing 'type'")
        if comp["type"] not in A2UI_CATALOG:
            raise ValueError(f"Unknown component type: {comp['type']}")


def _validate_data_model(data_model: dict[str, Any]) -> None:
    size = len(json.dumps(data_model))
    if size > MAX_DATA_MODEL_SIZE:
        raise ValueError(f"Data model too large: {size} bytes > {MAX_DATA_MODEL_SIZE} bytes")


def create_canvas_registry(
    broadcaster: Callable[..., Awaitable[None]] | None = None,
) -> InternalToolRegistry:
    if broadcaster:
        set_broadcaster(broadcaster)

    registry = InternalToolRegistry(
        name="gobby-canvas",
        description="Canvas UI management - render_surface, update_surface, close_canvas, wait_for_interaction, canvas_present",
    )

    @registry.tool(
        name="render_surface",
        description="Render an inline A2UI surface with declarative JSON components.",
    )
    async def render_surface(
        components: dict[str, Any],
        root_id: str,
        canvas_id: str | None = None,
        data_model: dict[str, Any] | None = None,
        blocking: bool = True,
        timeout: float = 300.0,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Render an inline A2UI surface."""
        from gobby.utils.session_context import get_session_context

        actual_convo_id = conversation_id
        if not actual_convo_id:
            ctx = get_session_context()
            if ctx:
                actual_convo_id = ctx.conversation_id or ctx.session_id

        if not actual_convo_id:
            return {"success": False, "error": "conversation_id (or session context) is required"}

        if not _check_rate_limit(actual_convo_id):
            return {"success": False, "error": "Rate limit exceeded"}

        if len(_canvases) >= MAX_TOTAL_CANVASES:
            # simple cleanup attempt
            sweep_expired()
            if len(_canvases) >= MAX_TOTAL_CANVASES:
                return {"success": False, "error": "Too many active canvases system-wide"}

        try:
            _validate_components(components)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        actual_data_model = data_model or {}
        try:
            _validate_data_model(actual_data_model)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        actual_canvas_id = canvas_id or str(uuid.uuid4())
        actual_timeout = min(timeout, CANVAS_MAX_TIMEOUT)

        # Create state
        state = CanvasState(
            canvas_id=actual_canvas_id,
            mode="a2ui",
            surface=components,
            data_model=actual_data_model,
            root_component_id=root_id,
            html_url=None,
            conversation_id=actual_convo_id,
            pending_event=asyncio.Event() if blocking else None,
            interaction_result=None,
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(seconds=actual_timeout),
            completed=False,
        )
        _canvases[actual_canvas_id] = state

        # Broadcast
        bc = _broadcaster_ref["func"]
        if bc:
            await bc(
                event="surface_update",
                canvas_id=actual_canvas_id,
                conversation_id=actual_convo_id,
                surface=components,
                dataModel=actual_data_model,
                rootComponentId=root_id,
            )

        if blocking and state.pending_event:
            try:
                await asyncio.wait_for(state.pending_event.wait(), timeout=actual_timeout)
                return {
                    "success": True,
                    "canvas_id": actual_canvas_id,
                    "action": state.interaction_result,
                }
            except TimeoutError:
                state.completed = True
                return {
                    "success": False,
                    "error": "Interaction timeout",
                    "canvas_id": actual_canvas_id,
                }

        return {"success": True, "canvas_id": actual_canvas_id}

    @registry.tool(
        name="update_surface",
        description="Update an existing A2UI surface with new components or data.",
    )
    async def update_surface(
        canvas_id: str,
        components: dict[str, Any] | None = None,
        data_model: dict[str, Any] | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing A2UI surface."""
        from gobby.utils.session_context import get_session_context

        actual_convo_id = conversation_id
        if not actual_convo_id:
            ctx = get_session_context()
            if ctx:
                actual_convo_id = ctx.conversation_id or ctx.session_id

        if not actual_convo_id:
            return {"success": False, "error": "conversation_id (or session context) is required"}

        state = _canvases.get(canvas_id)
        if not state:
            return {"success": False, "error": "Canvas not found"}
        if state.completed:
            return {"success": False, "error": "Canvas is already completed"}

        if not _check_rate_limit(actual_convo_id):
            return {"success": False, "error": "Rate limit exceeded"}

        # Copy dicts and merge
        new_surface = dict(state.surface)
        if components:
            new_surface.update(components)
            try:
                _validate_components(new_surface)
            except ValueError as e:
                return {"success": False, "error": str(e)}

        new_data_model = dict(state.data_model)
        if data_model:
            new_data_model.update(data_model)
            try:
                _validate_data_model(new_data_model)
            except ValueError as e:
                return {"success": False, "error": str(e)}

        state.surface = new_surface
        state.data_model = new_data_model

        bc = _broadcaster_ref["func"]
        if bc:
            await bc(
                event="surface_update",
                canvas_id=canvas_id,
                conversation_id=actual_convo_id,
                surface=new_surface,
                dataModel=new_data_model,
                rootComponentId=state.root_component_id,
            )

        return {"success": True}

    @registry.tool(
        name="close_canvas",
        description="Close a canvas, removing it from the UI.",
    )
    async def close_canvas(canvas_id: str) -> dict[str, Any]:
        """Close a canvas."""
        state = _canvases.get(canvas_id)
        if not state:
            return {"success": False, "error": "Canvas not found"}

        state.completed = True
        if state.pending_event:
            state.pending_event.set()

        _cleanup_html_file(state)

        bc = _broadcaster_ref["func"]
        if bc:
            await bc(
                event="close_canvas",
                canvas_id=canvas_id,
                conversation_id=state.conversation_id,
            )

        _canvases.pop(canvas_id, None)
        _canvas_locks.pop(canvas_id, None)

        return {"success": True}

    @registry.tool(
        name="wait_for_interaction",
        description="Wait for user interaction on a canvas.",
    )
    async def wait_for_interaction(
        canvas_id: str,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        """Wait for user interaction on a canvas."""
        state = _canvases.get(canvas_id)
        if not state:
            return {"success": False, "error": "Canvas not found"}
        if state.completed:
            return {"success": True, "action": state.interaction_result}

        if not state.pending_event:
            state.pending_event = asyncio.Event()

        actual_timeout = min(timeout, CANVAS_MAX_TIMEOUT)
        try:
            await asyncio.wait_for(state.pending_event.wait(), timeout=actual_timeout)
            return {"success": True, "action": state.interaction_result}
        except TimeoutError:
            state.completed = True
            return {"success": False, "error": "Interaction timeout"}

    @registry.tool(
        name="canvas_present",
        description="Present a local HTML file in the Canvas panel sandbox.",
    )
    async def canvas_present(
        file_path: str,
        canvas_id: str | None = None,
        title: str | None = None,
        width: int | None = None,
        height: int | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Present a local HTML file in the Canvas panel sandbox."""
        from gobby.utils.session_context import get_session_context

        actual_convo_id = conversation_id
        if not actual_convo_id:
            ctx = get_session_context()
            if ctx:
                actual_convo_id = ctx.conversation_id or ctx.session_id

        if not actual_convo_id:
            return {"success": False, "error": "conversation_id (or session context) is required"}

        source_path = Path(file_path)
        if not source_path.is_absolute() or not source_path.is_file():
            return {"success": False, "error": f"Invalid absolute file path: {file_path}"}

        actual_canvas_id = canvas_id or str(uuid.uuid4())

        # Copy to the canvas_dir (we'll implement this mounting in http.py)
        # usually ~/.gobby/canvas
        # but since we are copying, we'll need to know where it is or use /tmp and have HTTP mount it.
        # Let's use ~/.gobby/canvas
        gobby_canvas_dir = get_gobby_home() / "canvas"
        gobby_canvas_dir.mkdir(parents=True, exist_ok=True)

        target_name = f"{uuid.uuid4().hex}.html"
        target_path = gobby_canvas_dir / target_name
        try:
            shutil.copy2(source_path, target_path)
        except Exception as e:
            return {"success": False, "error": f"Failed to expose file: {e}"}

        html_url = f"/__gobby__/canvas/{target_name}"

        state = CanvasState(
            canvas_id=actual_canvas_id,
            mode="html",
            surface={},
            data_model={},
            root_component_id=None,
            html_url=html_url,
            conversation_id=actual_convo_id,
            pending_event=None,
            interaction_result=None,
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(seconds=CANVAS_DEFAULT_TIMEOUT),
            completed=False,
        )
        _canvases[actual_canvas_id] = state

        bc = _broadcaster_ref["func"]
        if bc:
            await bc(
                event="panel_present",
                canvas_id=actual_canvas_id,
                conversation_id=actual_convo_id,
                title=title or source_path.name,
                url=html_url,
                width=width,
                height=height,
            )

        return {"success": True, "canvas_id": actual_canvas_id, "url": html_url}

    @registry.tool(
        name="show_file",
        description="Show a file in the web chat artifacts panel with syntax highlighting (code) or rendered markdown (text). Supports code, markdown, images, and CSV files.",
    )
    async def show_file(
        file_path: str,
        title: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Show a file in the artifacts panel."""
        from gobby.utils.session_context import get_session_context

        actual_convo_id = conversation_id
        if not actual_convo_id:
            ctx = get_session_context()
            if ctx:
                actual_convo_id = ctx.conversation_id or ctx.session_id

        if not actual_convo_id:
            return {"success": False, "error": "conversation_id (or session context) is required"}

        source = Path(file_path)
        if not source.is_absolute():
            return {"success": False, "error": f"file_path must be absolute: {file_path}"}
        if not source.is_file():
            return {"success": False, "error": f"File not found: {file_path}"}

        ext = source.suffix.lower()
        artifact_type, language = EXTENSION_MAP.get(ext, ("code", ext.lstrip(".") or "text"))

        # Check file size
        file_size = source.stat().st_size
        if artifact_type == "image":
            if file_size > MAX_IMAGE_FILE_SIZE:
                return {
                    "success": False,
                    "error": f"Image file too large: {file_size} bytes (max {MAX_IMAGE_FILE_SIZE})",
                }
        elif file_size > MAX_TEXT_FILE_SIZE:
            return {
                "success": False,
                "error": f"File too large: {file_size} bytes (max {MAX_TEXT_FILE_SIZE})",
            }

        # Read content (use to_thread to avoid blocking the event loop)
        if artifact_type == "image":
            raw = await asyncio.to_thread(source.read_bytes)
            mime_type = mimetypes.guess_type(str(source))[0] or "application/octet-stream"
            content = f"data:{mime_type};base64,{base64.b64encode(raw).decode('ascii')}"
        else:
            try:
                content = await asyncio.to_thread(source.read_text, encoding="utf-8")
            except UnicodeDecodeError:
                return {"success": False, "error": f"File is not valid UTF-8: {file_path}"}

        actual_title = title or source.name

        bc = _artifact_broadcaster_ref["func"]
        if bc:
            await bc(
                event="show_file",
                conversation_id=actual_convo_id,
                artifact_type=artifact_type,
                content=content,
                language=language,
                title=actual_title,
            )

        return {
            "success": True,
            "type": artifact_type,
            "language": language,
            "title": actual_title,
        }

    return registry
