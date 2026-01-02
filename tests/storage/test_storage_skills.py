import pytest

from gobby.storage.database import LocalDatabase
from gobby.storage.skills import LocalSkillManager


@pytest.fixture
def skill_manager(temp_db: LocalDatabase):
    return LocalSkillManager(temp_db)


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


def test_list_skills(skill_manager, temp_db):
    # Seed projects for foreign keys
    temp_db.execute("INSERT INTO projects (id, name) VALUES ('p1', 'Project 1')")
    temp_db.execute("INSERT INTO projects (id, name) VALUES ('p2', 'Project 2')")

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
    assert len(skills) == 2
    assert {s.name for s in skills} == {"skill-a", "skill-b"}


def test_create_duplicate_skill(skill_manager, sample_project):
    """Test creating duplicate skill returns existing."""
    project_id = sample_project["id"]
    original = skill_manager.create_skill(name="dup", instructions="orig", project_id=project_id)

    # Same name + project = same ID
    duplicate = skill_manager.create_skill(name="dup", instructions="new", project_id=project_id)

    assert duplicate.id == original.id
    # Assert it returns the *existing* skill without update
    assert duplicate.instructions == "orig"


def test_listeners_notified(skill_manager):
    """Test listeners are notified on changes."""
    full_call_count = 0

    def listener():
        nonlocal full_call_count
        full_call_count += 1

    skill_manager.add_change_listener(listener)

    # Create
    skill = skill_manager.create_skill(name="event", instructions="...")
    assert full_call_count == 1

    # Update
    skill_manager.update_skill(skill.id, instructions="updated")
    assert full_call_count == 2

    # Increment usage
    skill_manager.increment_usage(skill.id)
    assert full_call_count == 3

    # Delete
    skill_manager.delete_skill(skill.id)
    assert full_call_count == 4


def test_increment_usage(skill_manager):
    """Test incrementing usage count."""
    skill = skill_manager.create_skill(name="usage", instructions="...")
    assert skill.usage_count == 0

    assert skill_manager.increment_usage(skill.id)

    updated = skill_manager.get_skill(skill.id)
    assert updated.usage_count == 1


def test_increment_usage_nonexistent(skill_manager):
    """Test incrementing usage for nonexistent skill."""
    assert not skill_manager.increment_usage("nonexistent")


def test_malformed_tags(skill_manager, temp_db):
    """Test handling of malformed tags JSON in DB."""
    # Insert manually
    temp_db.execute(
        "INSERT INTO skills (id, name, instructions, created_at, updated_at, tags) "
        "VALUES ('bad-tags', 'bad', '...', 'now', 'now', 'invalid-json')"
    )

    skill = skill_manager.get_skill("bad-tags")
    assert skill.tags == []


def test_list_skills_with_tag(skill_manager):
    """Test listing skills by tag."""
    skill_manager.create_skill(name="s1", instructions="...", tags=["t1", "t2"])
    skill_manager.create_skill(name="s2", instructions="...", tags=["t2"])
    skill_manager.create_skill(name="s3", instructions="...", tags=["t3"])

    skills = skill_manager.list_skills(tag="t2")
    assert len(skills) == 2
    names = {s.name for s in skills}
    assert names == {"s1", "s2"}
