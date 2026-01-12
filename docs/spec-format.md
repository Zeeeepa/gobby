# Spec Format Reference

This document explains how to write specification documents that Gobby can parse into tasks using `expand_from_spec`.

## Overview

Gobby supports three modes for parsing specs:

| Mode | Description | When to Use |
|------|-------------|-------------|
| `structured` | Parses headings and checkboxes directly (no LLM) | Well-formatted specs with clear hierarchy |
| `llm` | Uses LLM to interpret the document | Prose requirements, complex decomposition |
| `auto` | Detects structure, falls back to LLM | Default - let system decide |

## Structured Mode (Recommended)

Structured mode is fast, deterministic, and doesn't require LLM calls. Use it when your spec has clear hierarchy.

### Heading Levels

Headings map to task types:

| Level | Task Type | Description |
|-------|-----------|-------------|
| `##` | Epic | Top-level container (Phase, Module) |
| `###` | Feature/Epic | Sub-epic or standalone feature |
| `####` | Task | Individual work item |

Example:
```markdown
## Phase 1: Foundation

### User Authentication
Implementation of user auth system.

#### Session Management
Handle user sessions and tokens.

#### Password Hashing
Implement secure password storage.
```

### Checkbox Formats

All of these checkbox formats are supported:

```markdown
- [ ] Bullet checkbox (dash)
* [ ] Bullet checkbox (asterisk)
1. [ ] Numbered checkbox
10. [ ] Multi-digit numbered checkbox
```

Checkbox states:
- `[ ]` - Open/pending task
- `[x]` or `[X]` - Completed (skipped during parsing)

### Hierarchy via Indentation

Indent checkboxes to create parent-child relationships:

```markdown
## Authentication

- [ ] User registration
  - [ ] Email validation
  - [ ] Password requirements
- [ ] Login flow
  - [ ] Rate limiting
```

This creates:
- "User registration" epic with 2 child tasks
- "Login flow" epic with 1 child task

## TDD Mode

When `tdd_mode=True` (the default), coding tasks automatically become TDD triplets:

```
Feature title →
  1. Write tests for: Feature title
  2. Implement: Feature title
  3. Refactor: Feature title
```

### Non-Coding Tasks

These tasks do NOT get TDD triplet expansion:
- Epics (task_type="epic")
- Tasks with titles starting with: "Document", "Research", "Design", "Plan", "Review"

To create a non-coding task explicitly:
```markdown
#### Document the API  <!-- Won't become TDD triplet -->
#### Design the schema  <!-- Won't become TDD triplet -->
```

### Already-TDD Titles

If your spec already has TDD-formatted titles, they're preserved:
```markdown
- [ ] Write tests for: Auth  <!-- Stays as single test task -->
- [ ] Implement: Auth        <!-- Stays as single impl task -->
- [ ] Refactor: Auth         <!-- Stays as single refactor task -->
```

## LLM Mode

For unstructured specs, LLM mode interprets the document and outputs JSON:

```python
# Use LLM mode explicitly
expand_from_spec(spec_path="requirements.txt", mode="llm")
```

With the simplified TDD prompt, the LLM outputs feature names (not test/impl/refactor titles), and the code creates TDD triplets deterministically.

### LLM Output Schema

The LLM returns JSON with this structure:
```json
{
  "subtasks": [
    {
      "title": "Feature name",
      "description": "Implementation details",
      "priority": 2,
      "task_type": "feature",
      "test_strategy": "How to verify",
      "depends_on": [0, 1]
    }
  ]
}
```

## Best Practices

### 1. Use Meaningful Headings

```markdown
<!-- Good -->
## Phase 1: Backend Services

### Database Layer
Implementation of the persistence layer.

<!-- Avoid -->
## Part 1

### Stuff
Do the thing.
```

### 2. Keep Tasks Atomic

Each task should be completable in 10-30 minutes:

```markdown
<!-- Good - atomic tasks -->
- [ ] Create User model with fields
- [ ] Add database migration for users table
- [ ] Create UserRepository class

<!-- Avoid - too broad -->
- [ ] Implement entire user management system
```

### 3. Specify Dependencies via Order

Tasks are created in order. Use `depends_on` indices for explicit dependencies:

```markdown
## Setup
- [ ] Create database schema
- [ ] Seed initial data (depends on schema)

## Features
- [ ] User CRUD (depends on database)
```

### 4. Mix Structured and Prose

You can combine checkboxes with descriptive content:

```markdown
## Authentication

This module handles user authentication using JWT tokens.

### Implementation Tasks
- [ ] Create JWT service
- [ ] Add token validation middleware
- [ ] Implement refresh token flow

### Notes
- Use RS256 for token signing
- Token expiry: 1 hour
```

## Actionable vs Non-Actionable Sections

The parser skips these section keywords (case-insensitive):
- Overview, Introduction, Background
- Example, Examples, Configuration Example
- Notes, References, See Also
- Appendix, Glossary

Only sections with actionable keywords are parsed:
- Implementation, Tasks, Steps
- Phase, Work Items, TODO
- Action Items, Deliverables
- Changes, Modifications, Requirements

## Example Spec

```markdown
# Memory V3: Backend Abstraction

## Overview
This spec defines the backend abstraction layer for the memory system.

## Phase 1: Core Protocol

### Protocol Definition
- [ ] Create MemoryBackend protocol
- [ ] Define core types (MemoryItem, SearchResult)
- [ ] Add async method signatures

### Null Backend
- [ ] Create NullMemoryBackend for testing
- [ ] Return empty results for all methods

## Phase 2: Implementations

### SQLite Backend
- [ ] Refactor LocalMemoryManager into SqliteMemoryBackend
- [ ] Add media column migration

### External Backends
- [ ] Create MemU backend implementation
- [ ] Create Mem0 backend implementation

## Notes
- All backends must be async
- Use factory pattern for instantiation
```

This creates:
- 2 phase epics
- Multiple features under each phase
- TDD triplets for each checkbox task (when tdd_mode=True)
