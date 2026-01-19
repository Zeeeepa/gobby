# Plan: Externalize Task Expansion Prompts to Template Files

## Summary

Move the 3 task expansion prompts from hardcoded Python to markdown template files in `~/.gobby/prompts/`, with YAML frontmatter for metadata.

**Scope**: Expansion prompts only (system, user, TDD mode). Remaining ~16 prompts will be addressed in a follow-up plan.

## Migration Strategy: Strangler Fig Pattern

This migration uses the strangler fig pattern to ensure zero breakage:

1. **Add new capability**: Create `PromptLoader` and file-based prompts
2. **Parallel operation**: Both old (Python constants) and new (files) work simultaneously
3. **Gradual migration**: File-based takes precedence when present, falls back to Python
4. **Future deprecation**: Remove Python constants after file-based is proven stable

```
Phase 1 (This PR):
┌─────────────────────────────────────────────────────────────┐
│ Request → Config Path? → File exists? → Bundled default?   │
│              ↓ no           ↓ no            ↓ no            │
│         Python constant (existing behavior preserved)       │
└─────────────────────────────────────────────────────────────┘

Phase 2 (Future):
- Remove Python constants from expand.py
- Remove deprecated inline config fields from config.yaml
```

## Design Decisions

| Decision | Choice |
|----------|--------|
| File format | Markdown with YAML frontmatter |
| Extension | `.md` (Jinja2 rendering implicit) |
| Config compat | YAML config fields become paths to template files |
| Jinja2 | Yes, using existing `TemplateEngine` |

## Template File Format

```markdown
---
name: expansion-system
description: System prompt for task expansion LLM
variables:
  tdd_mode:
    type: bool
    description: Whether TDD mode is enabled
    default: false
---
You are a senior technical project manager and architect.
Your goal is to break down a high-level task into clear, actionable, and atomic subtasks.

{% if tdd_mode %}
## TDD Mode Enabled
...
{% endif %}

## Output Format
...
```

## Directory Structure

```
~/.gobby/prompts/
└── expansion/
    ├── system.md       # Task expansion system prompt
    ├── user.md         # Task expansion user prompt template
    └── tdd.md          # TDD mode instructions (optional, can be embedded in system.md)

.gobby/prompts/         # Project-specific overrides (optional)
└── expansion/
    └── system.md       # Override for this project
```

## Implementation Steps

### Step 1: Create PromptLoader Class

**New file:** `src/gobby/prompts/loader.py`

```python
class PromptLoader:
    """Load prompt templates from ~/.gobby/prompts/ with project overrides."""

    def __init__(self, project_dir: Path | None = None):
        self.search_paths = [
            project_dir / ".gobby/prompts" if project_dir else None,
            Path.home() / ".gobby/prompts",
            Path(__file__).parent / "defaults",  # Bundled defaults
        ]
        self.cache: dict[str, PromptTemplate] = {}

    def load(self, category: str, name: str) -> PromptTemplate:
        """Load prompt by category/name (e.g., 'expansion', 'system')."""

    def render(self, category: str, name: str, context: dict) -> str:
        """Load and render prompt with Jinja2 context."""
```

**New file:** `src/gobby/prompts/models.py`

```python
@dataclass
class PromptTemplate:
    name: str
    description: str
    variables: dict[str, VariableSpec]
    content: str
    source_path: Path | None  # For debugging
```

### Step 2: Create Default Prompt Templates

**New directory:** `src/gobby/prompts/defaults/expansion/`

Move content from `src/gobby/tasks/prompts/expand.py`:
- `system.md` - `DEFAULT_SYSTEM_PROMPT` + `TDD_MODE_INSTRUCTIONS` (with Jinja2 conditional)
- `user.md` - `DEFAULT_USER_PROMPT` template

### Step 3: Update Config to Support Paths

**File:** `src/gobby/config/tasks.py`

Update `TaskExpansionConfig` fields:
```python
class TaskExpansionConfig(BaseModel):
    # Existing fields...

    # Change from inline prompt to path reference
    system_prompt_path: str | None = Field(
        default=None,
        description="Path to custom system prompt template (relative to prompts dir)"
    )
    user_prompt_path: str | None = Field(
        default=None,
        description="Path to custom user prompt template"
    )

    # Keep existing fields for backwards compatibility but deprecate
    system_prompt: str | None = Field(
        default=None,
        description="[DEPRECATED] Use system_prompt_path instead. Inline system prompt."
    )
```

### Step 4: Update ExpansionPromptBuilder

**File:** `src/gobby/tasks/prompts/expand.py`

Refactor to use `PromptLoader`:
```python
class ExpansionPromptBuilder:
    def __init__(self, config: TaskExpansionConfig, prompt_loader: PromptLoader):
        self.config = config
        self.loader = prompt_loader

    def get_system_prompt(self, tdd_mode: bool = False) -> str:
        # Priority: inline config > custom path > default
        if self.config.system_prompt:  # Deprecated but supported
            return self.config.system_prompt

        path = self.config.system_prompt_path or "expansion/system.md"
        return self.loader.render(path, {"tdd_mode": tdd_mode})
```

### Step 5: Wire Up PromptLoader

**File:** `src/gobby/tasks/expansion.py`

Update `TaskExpander` to create and use `PromptLoader`:
```python
class TaskExpander:
    def __init__(self, config, llm_service, ...):
        self.prompt_loader = PromptLoader(project_dir=project_dir)
        self.prompt_builder = ExpansionPromptBuilder(
            config.expansion,
            self.prompt_loader
        )
```

### Step 6: Add pyproject.toml Package Data

**File:** `pyproject.toml`

```toml
[tool.setuptools.package-data]
"gobby.prompts.defaults" = ["**/*.md"]
```

## Files to Modify

| File | Changes |
|------|---------|
| `src/gobby/prompts/__init__.py` | New - package init |
| `src/gobby/prompts/loader.py` | New - PromptLoader class |
| `src/gobby/prompts/models.py` | New - PromptTemplate dataclass |
| `src/gobby/prompts/defaults/expansion/system.md` | New - default system prompt |
| `src/gobby/prompts/defaults/expansion/user.md` | New - default user prompt |
| `src/gobby/config/tasks.py` | Add `*_path` fields, deprecate inline |
| `src/gobby/tasks/prompts/expand.py` | Use PromptLoader |
| `src/gobby/tasks/expansion.py` | Wire up PromptLoader |
| `pyproject.toml` | Add package-data for prompts |

## Precedence Order

1. **Inline config** (deprecated): `config.expansion.system_prompt`
2. **Config path**: `config.expansion.system_prompt_path`
3. **Project file**: `.gobby/prompts/expansion/system.md`
4. **Global file**: `~/.gobby/prompts/expansion/system.md`
5. **Bundled default**: `src/gobby/prompts/defaults/expansion/system.md`
6. **Python constant** (strangler fig fallback): `DEFAULT_SYSTEM_PROMPT` in `expand.py`

**Note**: Level 6 ensures existing behavior is preserved even if template files are missing or misconfigured. It will be removed in Phase 4 cleanup.

## Verification

1. **Unit tests**: Add tests for `PromptLoader` in `tests/prompts/test_loader.py`
2. **Integration test**: Run task expansion and verify prompts load correctly
3. **Override test**:
   - Create `~/.gobby/prompts/expansion/system.md` with custom content
   - Run expansion, verify custom prompt is used
4. **Project override test**:
   - Create `.gobby/prompts/expansion/system.md`
   - Verify it takes precedence over global

## Future Work (Separate Plans)

### Phase 2: Remaining Prompts
Externalize remaining prompts using same pattern:
- Validation prompts (5 prompts in `external_validator.py`, `validation.py`)
- Research prompts (1 prompt in `research.py`)
- Session prompts (2 prompts in `sessions.py`, `claude.py`)
- Feature prompts (4 prompts in `features.py`)

### Phase 3: CLI Tooling
- `gobby prompts list` - List all prompts and their sources
- `gobby prompts show <name>` - Show prompt content
- `gobby prompts edit <name>` - Open in $EDITOR
- `gobby prompts reset <name>` - Remove custom override

### Phase 4: Cleanup (After Stable)
- Remove Python constants from source files
- Remove deprecated inline config fields from `~/.gobby/config.yaml`
- Update documentation to reference file-based prompts only
