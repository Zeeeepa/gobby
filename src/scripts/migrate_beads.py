import json
import os
from pathlib import Path
from datetime import datetime, timezone


def migrate():
    beads_path = Path(".beads/issues.jsonl")
    gobby_path = Path(".gobby/tasks.jsonl")

    if not beads_path.exists():
        print("No .beads/issues.jsonl found.")
        return

    print(f"Reading from {beads_path}...")
    with open(beads_path, "r") as f:
        lines = f.readlines()

    tasks = []
    for line in lines:
        if not line.strip():
            continue

        data = json.loads(line)

        # Transform dependencies
        deps = []
        if "dependencies" in data:
            for dep in data["dependencies"]:
                # beads: {"issue_id": "A", "depends_on_id": "B"} -> A blocks B?
                # Wait, "depends_on_id" usually means A depends on B.
                # My system uses 'deps_on' list in jsonl which means "this task depends on these IDs".
                if "depends_on_id" in dep:
                    deps.append(dep["depends_on_id"])

        # Transform to Gobby format
        task = {
            "id": data.get("id"),
            "project_id": "default",  # Required by my new import schema
            "title": data.get("title"),
            "description": data.get("description"),
            "status": data.get("status", "open"),
            "priority": data.get("priority", 2),
            "task_type": data.get("issue_type", "task"),
            "created_at": data.get("created_at", datetime.now(timezone.utc).isoformat()),
            "updated_at": data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            "parent_id": None,  # Beads didn't have explicit parent field in top level usually
            "deps_on": deps,
        }
        tasks.append(task)

    # Ensure .gobby dir exists
    gobby_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing {len(tasks)} tasks to {gobby_path}...")
    with open(gobby_path, "w") as f:
        for task in tasks:
            f.write(json.dumps(task) + "\n")

    print("Migration file created. Triggering sync via daemon restart or MCP tool...")


if __name__ == "__main__":
    migrate()
