"""Bundled rule synchronization on daemon start.

Loads rule definition YAML files from install/shared/rules/ and syncs
them to the DB rules table with tier='bundled'. Removes stale entries
whose source files no longer exist.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import aiofiles
import yaml

from gobby.storage.database import DatabaseProtocol
from gobby.storage.rules import RuleStore

__all__ = ["sync_bundled_rules", "sync_bundled_rules_sync", "get_bundled_rules_path"]

logger = logging.getLogger(__name__)


def get_bundled_rules_path() -> Path:
    """Get the path to bundled rules directory.

    Returns:
        Path to src/gobby/install/shared/rules/
    """
    from gobby.paths import get_install_dir

    return get_install_dir() / "shared" / "rules"


async def sync_bundled_rules(
    db: DatabaseProtocol,
    rules_dir: Path | None = None,
) -> dict[str, Any]:
    """Sync bundled rules from YAML files to the database.

    For each .yaml file in the rules directory:
    1. Parse rule_definitions dict
    2. Upsert each rule into DB with tier='bundled'
    3. Remove DB entries whose source files no longer exist

    Args:
        db: Database connection.
        rules_dir: Override rules directory (for testing). Defaults to bundled path.

    Returns:
        Dict with success status and counts.
    """
    if rules_dir is None:
        rules_dir = get_bundled_rules_path()

    result: dict[str, Any] = {
        "success": True,
        "synced": 0,
        "updated": 0,
        "skipped": 0,
        "removed": 0,
        "errors": [],
    }

    if not rules_dir.exists():
        logger.debug(f"Rules directory not found: {rules_dir}")
        return result

    store = RuleStore(db)

    # Track which rules we see on disk (for stale removal)
    seen_rule_names: set[str] = set()

    # Process each YAML file
    for yaml_path in sorted(rules_dir.glob("*.yaml")):
        try:
            async with aiofiles.open(yaml_path) as f:
                content = await f.read()
            data = yaml.safe_load(content)

            if not data or not isinstance(data, dict):
                continue

            rule_defs = data.get("rule_definitions", {})
            if not isinstance(rule_defs, dict):
                result["errors"].append(
                    f"Invalid rule_definitions in {yaml_path.name}: expected dict"
                )
                continue

            source_file = str(yaml_path)

            for rule_name, rule_def in rule_defs.items():
                if not isinstance(rule_def, dict):
                    result["errors"].append(
                        f"Invalid rule '{rule_name}' in {yaml_path.name}: expected dict"
                    )
                    continue

                seen_rule_names.add(rule_name)

                # Check if rule already exists
                existing = await asyncio.to_thread(store.get_rule, rule_name, tier="bundled")

                if existing:
                    # Compare definitions to detect changes
                    if json.dumps(existing["definition"], sort_keys=True) == json.dumps(
                        rule_def, sort_keys=True
                    ):
                        result["skipped"] += 1
                        continue

                    # Update existing rule
                    await asyncio.to_thread(
                        store.save_rule,
                        name=rule_name,
                        tier="bundled",
                        definition=rule_def,
                        source_file=source_file,
                    )
                    result["updated"] += 1
                    logger.debug(f"Updated bundled rule: {rule_name}")
                else:
                    # Create new rule
                    await asyncio.to_thread(
                        store.save_rule,
                        name=rule_name,
                        tier="bundled",
                        definition=rule_def,
                        source_file=source_file,
                    )
                    result["synced"] += 1
                    logger.debug(f"Synced bundled rule: {rule_name}")

        except (yaml.YAMLError, OSError, json.JSONDecodeError, ValueError) as e:
            error_msg = f"Failed to process {yaml_path.name}: {e}"
            logger.warning(error_msg)
            result["errors"].append(error_msg)

    # Remove stale bundled rules (exist in DB but not on disk)
    existing_bundled = await asyncio.to_thread(store.list_rules, tier="bundled")
    for rule in existing_bundled:
        if rule["name"] not in seen_rule_names:
            await asyncio.to_thread(store.delete_rule, rule["id"])
            result["removed"] += 1
            logger.info(f"Removed stale bundled rule: {rule['name']}")

    total = result["synced"] + result["updated"] + result["skipped"]
    if total > 0 or result["removed"] > 0:
        logger.info(
            f"Rule sync complete: {result['synced']} synced, "
            f"{result['updated']} updated, {result['skipped']} skipped, "
            f"{result['removed']} removed"
        )

    return result


def sync_bundled_rules_sync(
    db: DatabaseProtocol,
    rules_dir: Path | None = None,
) -> dict[str, Any]:
    """Synchronous wrapper for sync_bundled_rules.

    Uses the same _run_sync pattern from WorkflowLoader for environments
    with or without a running event loop.
    """
    import concurrent.futures

    coro = sync_bundled_rules(db, rules_dir=rules_dir)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # Running inside existing event loop — offload to a new thread
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
