"""
File browser routes for Gobby HTTP server.

Provides file tree browsing, reading, and image serving endpoints.
"""

import logging
import mimetypes
import subprocess  # nosec B404 — subprocess needed for git commands
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from gobby.storage.projects import LocalProjectManager

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)

# Max file size to read (1MB default)
DEFAULT_MAX_SIZE = 1_048_576

# Extensions treated as images
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp"}

# Extensions treated as binary (skip reading content)
BINARY_EXTENSIONS = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".o",
    ".a",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
    ".mkv",
    ".flac",
    ".pyc",
    ".class",
    ".wasm",
}


def _resolve_safe_path(project_path: str, relative_path: str) -> Path:
    """Resolve a relative path within a project, preventing path traversal.

    Args:
        project_path: Absolute path to the project root.
        relative_path: Relative path within the project.

    Returns:
        Resolved absolute Path.

    Raises:
        HTTPException: If path traversal is detected.
    """
    base = Path(project_path).resolve()
    target = (base / relative_path).resolve()
    if not target.is_relative_to(base):
        raise HTTPException(403, "Path traversal not allowed")
    return target


def _get_project_manager(server: "HTTPServer") -> LocalProjectManager:
    """Get a LocalProjectManager from the server's database."""
    if server.session_manager is None:
        raise HTTPException(503, "Session manager not available")
    return LocalProjectManager(server.session_manager.db)


def _get_git_tracked_files(project_path: str) -> set[str] | None:
    """Get set of git-tracked files, or None if not a git repo.

    Uses `git ls-files` for tracked files and `git ls-files --others --exclude-standard`
    for untracked but not ignored files.
    """
    try:
        # Get tracked files
        tracked = subprocess.run(  # nosec B603 B607 — hardcoded git command
            ["git", "ls-files"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if tracked.returncode != 0:
            return None

        # Get untracked but not ignored files
        untracked = subprocess.run(  # nosec B603 B607 — hardcoded git command
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        files: set[str] = set()
        for line in tracked.stdout.strip().splitlines():
            if line:
                files.add(line)
        if untracked.returncode == 0:
            for line in untracked.stdout.strip().splitlines():
                if line:
                    files.add(line)
        return files
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _is_path_visible(
    relative_path: str,
    git_files: set[str] | None,
    is_dir: bool,
) -> bool:
    """Check if a path should be visible in the file tree.

    Filters out .git directory and respects .gitignore via git ls-files.
    """
    parts = Path(relative_path).parts
    # Always hide .git directory
    if ".git" in parts:
        return False

    if git_files is None:
        # No git info — show everything except .git
        return True

    if is_dir:
        # Show directory if any tracked file is inside it
        prefix = relative_path.rstrip("/") + "/"
        return any(f.startswith(prefix) for f in git_files)

    return relative_path in git_files


def create_files_router(server: "HTTPServer") -> APIRouter:
    """Create files router with endpoints bound to server instance."""
    router = APIRouter(prefix="/api/files", tags=["files"])

    @router.get("/projects")
    async def list_projects() -> list[dict[str, Any]]:
        """List all registered projects."""
        pm = _get_project_manager(server)
        projects = pm.list()
        return [
            {
                "id": p.id,
                "name": p.name,
                "repo_path": p.repo_path,
            }
            for p in projects
            if p.repo_path and Path(p.repo_path).is_dir()
        ]

    @router.get("/tree")
    async def list_directory(
        project_id: str = Query(..., description="Project ID"),
        path: str = Query("", description="Relative path within project"),
    ) -> list[dict[str, Any]]:
        """List directory contents for the file tree.

        Returns entries sorted: directories first, then files, both alphabetical.
        Respects .gitignore via git ls-files.
        """
        pm = _get_project_manager(server)
        project = pm.get(project_id)
        if not project or not project.repo_path:
            raise HTTPException(404, "Project not found")

        target = _resolve_safe_path(project.repo_path, path)
        if not target.is_dir():
            raise HTTPException(400, "Path is not a directory")

        # Get git-tracked files for filtering
        git_files = _get_git_tracked_files(project.repo_path)

        entries: list[dict[str, Any]] = []
        try:
            for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
                rel = str(child.relative_to(Path(project.repo_path).resolve()))
                is_dir = child.is_dir()

                if not _is_path_visible(rel, git_files, is_dir):
                    continue

                entry: dict[str, Any] = {
                    "name": child.name,
                    "path": rel,
                    "is_dir": is_dir,
                }
                if not is_dir:
                    entry["size"] = child.stat().st_size
                    entry["extension"] = child.suffix.lower()
                entries.append(entry)
        except PermissionError as e:
            raise HTTPException(403, "Permission denied") from e

        # Sort: directories first, then files, alphabetical within each group
        entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
        return entries

    @router.get("/read")
    async def read_file(
        project_id: str = Query(..., description="Project ID"),
        path: str = Query(..., description="Relative path within project"),
        max_size: int = Query(DEFAULT_MAX_SIZE, description="Max bytes to read"),
    ) -> dict[str, Any]:
        """Read file content.

        Returns content with metadata. Large files are truncated.
        Binary files return metadata only.
        """
        pm = _get_project_manager(server)
        project = pm.get(project_id)
        if not project or not project.repo_path:
            raise HTTPException(404, "Project not found")

        target = _resolve_safe_path(project.repo_path, path)
        if not target.is_file():
            raise HTTPException(404, "File not found")

        stat = target.stat()
        extension = target.suffix.lower()
        mime_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"

        # Check if image
        is_image = extension in IMAGE_EXTENSIONS

        # Check if binary
        is_binary = extension in BINARY_EXTENSIONS or is_image

        result: dict[str, Any] = {
            "size": stat.st_size,
            "truncated": False,
            "binary": is_binary,
            "image": is_image,
            "mime_type": mime_type,
            "extension": extension,
            "name": target.name,
        }

        if is_binary:
            result["content"] = None
            return result

        # Read text content
        try:
            raw = target.read_bytes()
            truncated = len(raw) > max_size
            if truncated:
                raw = raw[:max_size]
            content = raw.decode("utf-8", errors="replace")
            result["content"] = content
            result["truncated"] = truncated
        except OSError as e:
            raise HTTPException(500, f"Failed to read file: {e}") from e

        return result

    @router.get("/image")
    async def serve_image(
        project_id: str = Query(..., description="Project ID"),
        path: str = Query(..., description="Relative path within project"),
    ) -> FileResponse:
        """Serve an image file directly for <img> tags."""
        pm = _get_project_manager(server)
        project = pm.get(project_id)
        if not project or not project.repo_path:
            raise HTTPException(404, "Project not found")

        target = _resolve_safe_path(project.repo_path, path)
        if not target.is_file():
            raise HTTPException(404, "File not found")

        extension = target.suffix.lower()
        if extension not in IMAGE_EXTENSIONS:
            raise HTTPException(400, "Not an image file")

        mime_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return FileResponse(target, media_type=mime_type)

    class WriteFileRequest(BaseModel):
        project_id: str
        path: str
        content: str

    @router.post("/write")
    async def write_file(request: WriteFileRequest) -> dict[str, Any]:
        """Write content to a file.

        Refuses writes to .git/ directory.
        """
        pm = _get_project_manager(server)
        project = pm.get(request.project_id)
        if not project or not project.repo_path:
            raise HTTPException(404, "Project not found")

        target = _resolve_safe_path(project.repo_path, request.path)

        # Refuse writes to .git/
        rel = str(target.relative_to(Path(project.repo_path).resolve()))
        if rel.startswith(".git") and (rel == ".git" or rel.startswith(".git/")):
            raise HTTPException(403, "Cannot write to .git directory")

        if not target.parent.exists():
            raise HTTPException(404, "Parent directory does not exist")

        try:
            target.write_text(request.content, encoding="utf-8")
        except OSError as e:
            raise HTTPException(500, f"Failed to write file: {e}") from e

        return {
            "success": True,
            "size": len(request.content.encode("utf-8")),
            "path": request.path,
        }

    @router.get("/git-status")
    async def git_status(
        project_id: str = Query(..., description="Project ID"),
    ) -> dict[str, Any]:
        """Get git status for a project.

        Returns branch name and file statuses using `git status --porcelain`.
        Status codes: M=modified, A=added, D=deleted, ?=untracked, R=renamed.
        """
        pm = _get_project_manager(server)
        project = pm.get(project_id)
        if not project or not project.repo_path:
            raise HTTPException(404, "Project not found")

        result: dict[str, Any] = {"branch": None, "files": {}}

        try:
            # Get branch name
            branch_proc = subprocess.run(  # nosec B603 B607 — hardcoded git command
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=project.repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if branch_proc.returncode == 0:
                result["branch"] = branch_proc.stdout.strip()

            # Get file statuses
            status_proc = subprocess.run(  # nosec B603 B607 — hardcoded git command
                ["git", "status", "--porcelain"],
                cwd=project.repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if status_proc.returncode == 0:
                files: dict[str, str] = {}
                for line in status_proc.stdout.splitlines():
                    if not line or len(line) < 4:  # noqa: PLR2004
                        continue
                    # Format: "XY PATH" — XY is exactly 2 chars, then space, then path
                    xy = line[0:2]
                    status_code = xy.strip() or "?"
                    file_path = line[3:]
                    # Handle renames: "R  old -> new"
                    if " -> " in file_path:
                        file_path = file_path.split(" -> ")[-1]
                    if file_path:
                        files[file_path] = status_code
                result["files"] = files
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return result

    @router.get("/git-diff")
    async def git_diff(
        project_id: str = Query(..., description="Project ID"),
        path: str = Query(..., description="Relative file path"),
    ) -> dict[str, str]:
        """Get git diff for a specific file."""
        pm = _get_project_manager(server)
        project = pm.get(project_id)
        if not project or not project.repo_path:
            raise HTTPException(404, "Project not found")

        # Validate path
        _resolve_safe_path(project.repo_path, path)

        try:
            diff_proc = subprocess.run(  # nosec B603 B607 — hardcoded git command
                ["git", "diff", "HEAD", "--", path],
                cwd=project.repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            diff = diff_proc.stdout if diff_proc.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            diff = ""

        return {"diff": diff, "path": path}

    return router
