import asyncio
import logging

from gobby.storage.skills import LocalSkillManager

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skill-cleanup")

# Import Gobby components


async def cleanup_db(dry_run: bool = False):
    try:
        print("Initializing Skill Manager...")
        # Assuming default DB location or similar defaults
        from gobby.storage.database import LocalDatabase

        db = LocalDatabase()
        manager = LocalSkillManager(db=db)

        print("Listing all skills...")
        all_skills = manager.list_skills(limit=1000)
        print(f"Found {len(all_skills)} skills in total.")
    except Exception as e:
        print(f"Error initializing database or listing skills: {e}")
        import sys

        sys.exit(1)

    keepers = {"task-cleanup", "roadmap-reorganization", "large-file-decomposition"}

    to_delete = []
    for skill in all_skills:
        if skill.name not in keepers:
            to_delete.append(skill)

    print(f"Summary: Found {len(to_delete)} skills to delete out of {len(all_skills)} total.")

    if not dry_run and to_delete:
        print("The following skills will be deleted:")
        for s in to_delete:
            print(f" - {s.name} ({s.id})")
        confirm = input("Are you sure you want to delete these skills? (y/N): ")
        if confirm.lower() != "y":
            print("Aborted by user.")
            return

    deleted_count = 0
    kept_count = 0

    for skill in all_skills:
        if skill.name in keepers:
            print(f"KEEPING: {skill.name} ({skill.id})")
            kept_count += 1
        else:
            if dry_run:
                print(f"[DRY RUN] Would DELETE: {skill.name} ({skill.id})")
                deleted_count += 1
            else:
                success = manager.delete_skill(skill.id)
                if success:
                    print(f"DELETED: {skill.name} ({skill.id})")
                    deleted_count += 1
                else:
                    print(f"FAILED to delete: {skill.name} ({skill.id})")

    print("-" * 30)
    print("Cleanup Complete.")
    print(f"Deleted: {deleted_count}")
    print(f"Kept: {kept_count}")
    print(f"Total processed: {deleted_count + kept_count}")


if __name__ == "__main__":
    import sys

    dry_run = "--dry-run" in sys.argv
    asyncio.run(cleanup_db(dry_run=dry_run))
