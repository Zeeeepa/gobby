"""
FastAPI route modules for Gobby HTTP server.

Each module contains an APIRouter with related endpoints.
"""

from gobby.servers.routes.admin import create_admin_router
from gobby.servers.routes.agents import create_agents_router
from gobby.servers.routes.artifacts import create_artifacts_router
from gobby.servers.routes.configuration import create_configuration_router
from gobby.servers.routes.cron import create_cron_router
from gobby.servers.routes.files import create_files_router
from gobby.servers.routes.mcp import (
    create_hooks_router,
    create_mcp_router,
    create_plugins_router,
    create_webhooks_router,
)
from gobby.servers.routes.memory import create_memory_router
from gobby.servers.routes.pipelines import create_pipelines_router
from gobby.servers.routes.projects import create_projects_router
from gobby.servers.routes.sessions import create_sessions_router
from gobby.servers.routes.skills import create_skills_router
from gobby.servers.routes.tasks import create_tasks_router
from gobby.servers.routes.voice import create_voice_router

__all__ = [
    "create_admin_router",
    "create_agents_router",
    "create_artifacts_router",
    "create_configuration_router",
    "create_cron_router",
    "create_files_router",
    "create_hooks_router",
    "create_mcp_router",
    "create_memory_router",
    "create_pipelines_router",
    "create_plugins_router",
    "create_projects_router",
    "create_sessions_router",
    "create_skills_router",
    "create_tasks_router",
    "create_voice_router",
    "create_webhooks_router",
]
