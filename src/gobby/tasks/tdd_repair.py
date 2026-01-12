import logging

from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import LocalTaskManager

logger = logging.getLogger(__name__)


class TDDRepair:
    """Repair utility to upgrade TDD pairs to triplets."""

    def __init__(self, task_manager: LocalTaskManager):
        self.task_manager = task_manager
        self.dep_manager = TaskDependencyManager(task_manager.db)

    def upgrade_pairs_to_triplets(self, project_id: str) -> list[str]:
        """
        Identify existing TDD pairs (Test -> Impl) and upgrade them to triplets
        by adding a 'Refactor' task.

        Legacy Pattern detected:
        Test Task ("Write tests for X")
          └── Impl Task ("X" or "Implement X")

        Action:
        Create Refactor Task ("Refactor: X") as child of Test Task,
        dependent on Impl Task.

        Returns:
            List of IDs of created Refactor tasks.
        """
        created_ids = []

        # Get all tasks for project
        all_tasks = self.task_manager.list_tasks(project_id=project_id, limit=1000)

        # 1. Identify Test tasks
        test_tasks = [t for t in all_tasks if t.title.lower().startswith("write tests for")]

        for test_task in test_tasks:
            # Extract feature name X from "Write tests for X" or "Write tests for: X"
            if ":" in test_task.title:
                feature_name = test_task.title.split(":", 1)[1].strip()
            else:
                feature_name = test_task.title[len("Write tests for") :].strip()

            # Find children (Impl candidates)
            children = [t for t in all_tasks if t.parent_task_id == test_task.id]

            if not children:
                continue

            # Look for existing Refactor task to avoid duplication
            has_refactor = any(c.title.lower().startswith("refactor") for c in children)
            if has_refactor:
                continue

            # Assume the non-refactor child is the implementation
            # In legacy, it was just "X", or maybe "Implement X"
            impl_tasks = [c for c in children if not c.title.lower().startswith("refactor")]

            if not impl_tasks:
                continue

            # Take the first one as implementation
            impl_task = impl_tasks[0]

            logger.info(
                f"Upgrading TDD pair for '{feature_name}': Test={test_task.id}, Impl={impl_task.id}"
            )

            # Create Refactor task
            refactor_title = f"Refactor: {feature_name}"
            refactor_desc = (
                f"Refactor the implementation of: {feature_name}\n\n"
                "Test strategy: All tests must continue to pass after refactoring"
            )

            refactor_task = self.task_manager.create_task(
                title=refactor_title,
                description=refactor_desc,
                project_id=project_id,
                priority=impl_task.priority,  # Inherit priority
                task_type="task",
                parent_task_id=test_task.id,  # Keep as child of Test task (sibling of Impl)
            )

            # Add dependency: Refactor depends on Impl
            try:
                self.dep_manager.add_dependency(
                    task_id=refactor_task.id, depends_on=impl_task.id, dep_type="blocks"
                )
                created_ids.append(refactor_task.id)
                logger.info(f"Created Refactor task {refactor_task.id}")
            except Exception as e:
                logger.warning(f"Failed to wire dependency for {refactor_task.id}: {e}")
                # Still track the task so caller knows it was created
                created_ids.append(refactor_task.id)

        return created_ids
