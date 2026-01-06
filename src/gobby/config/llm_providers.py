"""
LLM providers configuration module.

Contains LLM-related Pydantic config models:
- LLMProviderConfig: Single provider config (models, auth_mode)
- LLMProvidersConfig: Multi-provider config (claude, codex, gemini, litellm)
- TitleSynthesisConfig: Session title generation settings
- CodeExecutionConfig: LLM code execution settings
- RecommendToolsConfig: Tool recommendation settings
- ToolSummarizerConfig: Tool description summarization settings
- ImportMCPServerConfig: MCP server config extraction settings

Extracted from app.py using Strangler Fig pattern for code decomposition.
"""

# Placeholder module - configs will be migrated from app.py
# Following Strangler Fig pattern: wrap don't rewrite

__all__: list[str] = []
