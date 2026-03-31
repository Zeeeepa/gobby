"""Background maintenance loop for code indexing.

Periodically walks indexed projects, triggers re-indexing via gcode,
and generates AI summaries for unsummarized symbols.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.code_index.indexer import CodeIndexer
    from gobby.code_index.summarizer import SymbolSummarizer

logger = logging.getLogger(__name__)


async def code_index_maintenance_loop(
    indexer: CodeIndexer,
    shutdown_flag: asyncio.Event | None = None,
    interval: int = 300,
    summarizer: SymbolSummarizer | None = None,
) -> None:
    """Background loop that checks for stale indexed files.

    Args:
        indexer: CodeIndexer instance (used for storage access).
        shutdown_flag: Event that signals shutdown.
        interval: Seconds between maintenance runs.
        summarizer: Optional SymbolSummarizer for generating AI summaries.
    """
    logger.info(f"Code index maintenance loop started (interval={interval}s)")

    while True:
        # Check shutdown
        if shutdown_flag is not None and shutdown_flag.is_set():
            break

        try:
            await _run_maintenance(indexer, summarizer)
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


async def _run_maintenance(
    indexer: CodeIndexer,
    summarizer: SymbolSummarizer | None = None,
) -> None:
    """Single maintenance pass: re-index via gcode, then generate summaries."""
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

        # Generate summaries (Python only — needs LLM)
        if summarizer is not None:
            try:
                unsummarized = indexer.storage.get_symbols_without_summaries(
                    project_id=project.id, limit=50
                )
                if unsummarized:
                    root = project.root_path

                    def source_reader(fp: str, bs: int, be: int, _root: str = root) -> str | None:
                        full = Path(_root) / fp
                        try:
                            with open(full, "rb") as f:
                                f.seek(bs)
                                data = f.read(be - bs)
                                if not data:
                                    return None
                                return data.decode("utf-8", errors="replace")
                        except (OSError, ValueError):
                            return None

                    summaries = await summarizer.generate_summaries(unsummarized, source_reader)
                    for sym_id, text in summaries.items():
                        indexer.storage.update_symbol_summary(sym_id, text)
                    if summaries:
                        logger.debug(f"Generated {len(summaries)} summaries for {project.id}")
            except Exception as e:
                logger.warning(f"Summary generation failed for {project.id}: {e}")
