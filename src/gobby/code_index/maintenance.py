"""Background maintenance loop for code indexing.

Periodically walks indexed projects, triggers re-indexing via gcode,
and recovers files with incomplete graph/vector sync.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.code_index.indexer import CodeIndexer

logger = logging.getLogger(__name__)


async def code_index_maintenance_loop(
    indexer: CodeIndexer,
    shutdown_flag: asyncio.Event | None = None,
    interval: int = 300,
) -> None:
    """Background loop that checks for stale indexed files.

    Args:
        indexer: CodeIndexer instance (used for storage access).
        shutdown_flag: Event that signals shutdown.
        interval: Seconds between maintenance runs.
    """
    logger.info(f"Code index maintenance loop started (interval={interval}s)")

    while True:
        # Check shutdown
        if shutdown_flag is not None and shutdown_flag.is_set():
            break

        try:
            await _run_maintenance(indexer)
        except Exception as e:
            logger.error(f"Code index maintenance error: {e}", exc_info=True)

        # Wait for interval or shutdown
        if shutdown_flag is not None:
            try:
                await asyncio.wait_for(shutdown_flag.wait(), timeout=interval)
                break  # Shutdown signaled
            except TimeoutError:
                pass  # Normal timeout, loop again
        else:
            await asyncio.sleep(interval)

    logger.info("Code index maintenance loop stopped")


async def _run_maintenance(indexer: CodeIndexer) -> None:
    """Single maintenance pass: re-index via gcode, then recover unsynced files."""
    projects = indexer.storage.list_indexed_projects()
    gcode_bin = Path.home() / ".gobby" / "bin" / "gcode"

    gcode_available = gcode_bin.exists()
    if not gcode_available:
        logger.warning("gcode not installed — skipping maintenance index. Run `gobby install`.")

    for project in projects:
        if not project.root_path:
            continue

        if gcode_available:
            try:
                proc = await asyncio.create_subprocess_exec(
                    str(gcode_bin),
                    "index",
                    str(project.root_path),
                    "--quiet",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
                if proc.returncode != 0:
                    detail = stderr.decode().strip() if stderr else "<no stderr>"
                    logger.warning(
                        f"Maintenance reindex failed for {project.id} "
                        f"(exit code {proc.returncode}): {detail}"
                    )
            except TimeoutError:
                logger.warning(f"Maintenance reindex timed out for {project.id}")
            except Exception as e:
                logger.warning(f"Maintenance reindex failed for {project.id}: {e}")

        # Recover files where graph/vector sync was incomplete
        if gcode_available:
            await _recover_unsynced_files(indexer, project, gcode_bin)


async def _recover_unsynced_files(
    indexer: CodeIndexer,
    project: Any,
    gcode_bin: Path,
) -> None:
    """Re-trigger gcode for files with graph_synced=0."""
    try:
        unsynced = indexer.storage.get_unsynced_files(project.id, limit=100)
    except Exception:
        # Column may not exist yet (pre-migration 178)
        return

    if not unsynced:
        return

    logger.info(f"Recovering {len(unsynced)} unsynced files for {project.id}")
    root = Path(project.root_path)
    unsynced_paths = []
    for f in unsynced:
        full_path = root / f.file_path
        if full_path.exists():
            unsynced_paths.append(str(full_path))
        else:
            indexer.storage.delete_file(project.id, f.file_path)

    if not unsynced_paths:
        return

    try:
        proc = await asyncio.create_subprocess_exec(
            str(gcode_bin),
            "index",
            "--files",
            *unsynced_paths,
            "--quiet",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode == 0:
            logger.info(f"Recovered {len(unsynced_paths)} unsynced files for {project.id}")
        else:
            detail = stderr.decode().strip() if stderr else ""
            logger.warning(f"Graph sync recovery failed (exit {proc.returncode}): {detail}")
    except TimeoutError:
        logger.warning("Graph sync recovery timed out")
    except Exception as e:
        logger.warning(f"Graph sync recovery failed: {e}")
