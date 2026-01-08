import asyncio
import logging

from gobby.storage.skills import LocalSkillManager

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skill-cleanup")

# Import Gobby components


async def cleanup_db():
    print("Initializing Skill Manager...")
    # Assuming default DB location or similar defaults
    from gobby.storage.database import LocalDatabase

    db = LocalDatabase()
    manager = LocalSkillManager(db=db)

    print("Listing all skills...")
    all_skills = manager.list_skills(limit=1000)
    print(f"Found {len(all_skills)} skills in total.")

    keepers = {"task-cleanup", "roadmap-reorganization", "large-file-decomposition"}

    deleted_count = 0
    kept_count = 0

    for skill in all_skills:
        if skill.name in keepers:
            print(f"KEEPING: {skill.name} ({skill.id})")
            kept_count += 1
        else:
            # print(f"DELETING: {skill.name} ({skill.id})")
            success = manager.delete_skill(skill.id)
            if success:
                deleted_count += 1
            else:
                print(f"FAILED to delete: {skill.name} ({skill.id})")

    print("-" * 30)
    print("Cleanup Complete.")
    print(f"Deleted: {deleted_count}")
    print(f"Kept: {kept_count}")
    print(f"Total processed: {deleted_count + kept_count}")


if __name__ == "__main__":
    asyncio.run(cleanup_db())
