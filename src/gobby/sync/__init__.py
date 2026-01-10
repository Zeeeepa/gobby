"""Sync services for external integrations.

This module provides sync services that orchestrate between gobby tasks
and external services like GitHub and Linear.
"""

from gobby.sync.github import GitHubSyncService

__all__ = ["GitHubSyncService"]
