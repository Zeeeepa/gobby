"""Tests for skill hints in hook error messages.

Verifies that hook error messages include actionable instructions
when blocking actions (e.g., create/claim task instructions when edit blocked).

Note: require_active_task tests were removed when the deprecated action
was deleted. Task enforcement is now handled by block_tools with declarative rules.
"""
