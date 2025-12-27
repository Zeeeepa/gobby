import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations
from gobby.storage.skills import LocalSkillManager


@pytest.fixture
def db(tmp_path):
    database = LocalDatabase(tmp_path / "gobby.db")
    run_migrations(database)
    yield database
    database.close()


@pytest.fixture
def skill_manager(db):
    return LocalSkillManager(db)


def test_create_skill(skill_manager):
    skill = skill_manager.create_skill(
        name="test-skill",
        instructions="Do this",
        tags=["tag1"],
    )
    assert skill.id.startswith("sk-")
    assert skill.name == "test-skill"
    assert skill.instructions == "Do this"
    assert skill.tags == ["tag1"]


def test_get_skill(skill_manager):
    created = skill_manager.create_skill(name="get-me", instructions="...")
    retrieved = skill_manager.get_skill(created.id)
    assert retrieved == created


def test_update_skill(skill_manager):
    created = skill_manager.create_skill(name="orig", instructions="orig")
    updated = skill_manager.update_skill(
        created.id,
        name="updated",
        instructions="updated",
    )
    assert updated.name == "updated"
    assert updated.instructions == "updated"
    assert updated.updated_at > created.updated_at


def test_delete_skill(skill_manager):
    created = skill_manager.create_skill(name="del", instructions="...")
    assert skill_manager.delete_skill(created.id)
    with pytest.raises(ValueError, match="not found"):
        skill_manager.get_skill(created.id)


def test_list_skills(skill_manager, db):
    # Seed projects for foreign keys
    db.execute("INSERT INTO projects (id, name) VALUES ('p1', 'Project 1')")
    db.execute("INSERT INTO projects (id, name) VALUES ('p2', 'Project 2')")

    skill_manager.create_skill(name="skill-a", instructions="...", project_id="p1")
    skill_manager.create_skill(name="skill-b", instructions="...", project_id="p2")
    skill_manager.create_skill(name="common", instructions="...")

    # Filter by project (should usually include globals too if logic dictates,
    # but skills logic is: if project_id -> (project_id = ? OR project_id IS NULL))

    skills = skill_manager.list_skills(project_id="p1")
    names = {s.name for s in skills}
    assert "skill-a" in names
    assert "common" in names
    assert "skill-b" not in names

    # Filter by name
    skills = skill_manager.list_skills(name_like="skill")
    assert len(skills) == 2  # skill-a, skill-b
