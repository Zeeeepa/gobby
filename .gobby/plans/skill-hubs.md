# Skill Hub Registry Abstraction

## Overview

Add a generic hub/registry abstraction to Gobby's skill system supporting ClawdHub, SkillHub, and GitHub Collections. This enables searching and installing skills from 7,500+ skills across multiple registries.

## Constraints

- Must follow existing patterns (LLMProvider, MCPServerConfig)
- ClawdHub and SkillHub pre-configured as defaults
- Short-form syntax: `hubname:slug` (e.g., `clawdhub:commit-message`)
- Credentials in `api_keys` section of config.yaml

## Phase 1: Configuration & Data Models

**Goal**: Add hub configuration schema and update skill storage for hub tracking.

**Tasks:**
- [ ] Add HubConfig pydantic model to config/app.py (category: code)
- [ ] Extend SkillsConfig with hubs dict (category: code)
- [ ] Add hub tracking fields to Skill dataclass (category: code)
- [ ] Update SkillSourceType to include "hub" (category: code)

## Phase 2: Provider Abstraction

**Goal**: Create the hub provider interface and manager.

**Tasks:**
- [ ] Create HubProvider ABC in skills/hubs/base.py (category: code)
- [ ] Add HubSkillInfo and HubSkillDetails dataclasses (category: code)
- [ ] Create HubManager in skills/hubs/manager.py (category: code)
- [ ] Add provider factory method for hub types (category: code)

## Phase 3: ClawdHub Provider

**Goal**: Implement ClawdHub REST API provider.

**Tasks:**
- [ ] Implement ClawdHubProvider class (category: code)
- [ ] Add well-known discovery endpoint (category: code)
- [ ] Implement search method with query params (category: code)
- [ ] Implement download_skill with ZIP extraction (category: code)

## Phase 4: SkillHub Provider

**Goal**: Implement SkillHub REST API provider.

**Tasks:**
- [ ] Implement SkillHubProvider class (category: code)
- [ ] Implement search via POST /skills/search (category: code)
- [ ] Implement catalog listing via GET /skills/catalog (category: code)
- [ ] Handle x-api-key authentication (category: code)

## Phase 5: GitHub Collection Provider

**Goal**: Implement GitHub repo-based skill collections.

**Tasks:**
- [ ] Implement GitHubCollectionProvider class (category: code)
- [ ] Use existing clone_skill_repo for downloads (category: code)
- [ ] Implement client-side search via listing + filtering (category: code)

## Phase 6: MCP Tools

**Goal**: Add hub MCP tools and update install_skill.

**Tasks:**
- [ ] Add search_hub tool to skills/__init__.py (category: code)
- [ ] Add list_hubs tool (category: code)
- [ ] Update install_skill for hub:slug syntax (category: code)
- [ ] Wire HubManager into skills registry (category: code)

## Phase 7: CLI Commands

**Goal**: Add CLI commands for hub search and management.

**Tasks:**
- [ ] Add gobby skills search command (category: code)
- [ ] Add gobby skills hub list command (category: code)
- [ ] Add gobby skills hub add command (category: code)
- [ ] Update gobby skills install for hub syntax (category: code)

## Task Mapping

<!-- Updated after task creation via /g expand -->
| Plan Item | Task Ref | Status |
|-----------|----------|--------|
