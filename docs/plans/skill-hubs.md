# Skill Hub Registry Abstraction

## Summary

Add a generic hub/registry abstraction to Gobby's skill system that supports multiple skill sources.

## Skill Hub Ecosystem (2026)

| Hub | CLI | Skills | Notes |
| ----- | ----- | -------- | ------- |
| [ClawdHub](https://clawdhub.com) | `npm i -g clawdhub` | 500+ | Moltbot's registry, **CLI only** (no public REST API) |
| [SkillHub](https://skillhub.club) | `npx @skill-hub/cli` | 7,000+ | AI-evaluated, S/A rankings, has REST API |
| [SkillCreator.ai](https://skillcreator.ai) | `npx ai-agent-skills` | Dynamic | Creates skills from URLs/docs |
| [n-skills](https://github.com/numman-ali/n-skills) | `openskills` | Curated | GitHub-based marketplace |
| GitHub Collections | git | Varies | Repos like `moltbot/skills` |

## Supported Hubs (Initial Release)

- **ClawdHub** (pre-configured default)
- **SkillHub** (pre-configured default)
- **GitHub Collections** (user-configured)

## API Reference

### ClawdHub API (CLI-Based)

> **Verified**: ClawdHub does NOT expose a public REST API. Use the official CLI tool.

**CLI Tool**: `npm i -g clawdhub` ([docs](https://docs.molt.bot/tools/clawdhub))

**Available Commands:**

- `clawdhub search "query"` - Vector search for skills
- `clawdhub install <slug>` - Install a skill to workspace
- `clawdhub update <slug>` / `--all` - Update installed skills
- `clawdhub list` - View installed skills
- `clawdhub publish <path>` - Publish a skill
- `clawdhub sync` - Batch publish/update local skills
- `clawdhub login` / `logout` / `whoami` - Authentication

**Environment Variables:**

- `CLAWDHUB_SITE` - Override site URL
- `CLAWDHUB_REGISTRY` - Override registry API URL
- `CLAWDHUB_CONFIG_PATH` - Token/config storage location
- `CLAWDHUB_WORKDIR` - Default working directory

**Authentication:**

- Browser-based: `clawdhub login`
- Token-based: `clawdhub login --token <token>`

**Implementation Approach:**
Wrap CLI commands via subprocess, parse output into `HubSkillInfo` objects.

### SkillHub API

> **Verified**: SkillHub has both REST API and CLI.

**CLI Tool**: `npx @skill-hub/cli`

- `npx @skill-hub/cli search "query"`
- `npx @skill-hub/cli install <slug>`

**REST API:**

- **Base**: `https://www.skillhub.club/api/v1`
- **Search**: `POST /skills/search` body: `{query, limit, category, method}` → `{skills: [...]}`
- **Catalog**: `GET /skills/catalog?limit=<n>&sort=score|stars|recent`
- **Auth**: `Authorization: Bearer <SKILLHUB_API_KEY>` header (required for all requests)

**Rate Limits:**

- Free tier: 2 queries/day
- Pro: 50 queries/day

## Hub Configuration (`~/.gobby/config.yaml`)

```yaml
skills:
  hubs:
    clawdhub:
      type: clawdhub
      enabled: true
      # base_url defaults to https://clawdhub.com
      auth_key_name: CLAWDHUB_TOKEN

    skillhub:
      type: skillhub
      enabled: true
      # base_url defaults to https://www.skillhub.club/api/v1
      auth_key_name: SKILLHUB_API_KEY

    moltbot-skills:
      type: github-collection
      enabled: true
      repo: moltbot/skills
      branch: main

api_keys:
  CLAWDHUB_TOKEN: ${CLAWDHUB_TOKEN:-}
  SKILLHUB_API_KEY: ${SKILLHUB_API_KEY:-}
  GITHUB_TOKEN: ${GITHUB_TOKEN:-}
```

## Hub Provider Interface

```python
class HubProvider(ABC):
    async def discover(self) -> dict[str, Any]
    async def search(self, query: str, limit: int = 20) -> list[HubSkillInfo]
    async def list_skills(self, limit: int = 50) -> list[HubSkillInfo]
    async def get_skill_details(self, slug: str) -> HubSkillDetails | None
    async def download_skill(self, slug: str, version: str | None) -> HubDownloadResult
```

## Usage Examples

```bash
# Search across all hubs
gobby skills search "git commit"

# Search specific hub
gobby skills search "testing" --hub clawdhub

# Install from hub
gobby skills install clawdhub:commit-message
gobby skills install --hub clawdhub commit-message --version 1.2.0

# Manage hubs
gobby skills hub list
gobby skills hub add enterprise --type clawdhub --url https://skills.company.com
```

## Files to Create

| Path | Purpose |
| ------ | --------- |
| `src/gobby/skills/hubs/__init__.py` | Module exports |
| `src/gobby/skills/hubs/base.py` | `HubProvider` ABC, data classes |
| `src/gobby/skills/hubs/manager.py` | `HubManager` (multi-hub orchestration) |
| `src/gobby/skills/hubs/clawdhub.py` | ClawdHub CLI wrapper provider |
| `src/gobby/skills/hubs/skillhub.py` | SkillHub REST API provider |
| `src/gobby/skills/hubs/github_collection.py` | GitHub repo provider |

## Files to Modify

| Path | Changes |
| ------ | --------- |
| `src/gobby/skills/hubs/base.py` | Add `HubConfig` model (referenced by `SkillsConfig`) |
| `src/gobby/storage/skills.py` | Add hub tracking fields to `Skill` dataclass |
| `src/gobby/mcp_proxy/tools/skills/__init__.py` | Add `search_hub`, `list_hubs` tools; update `install_skill` |
| `src/gobby/cli/skills.py` | Add `search` command, `hub` subcommand group |

## Implementation Phases

### Phase 1: Configuration & Data Models

- Add `HubConfig` pydantic model
- Add hub tracking fields: `hub_name`, `hub_slug`, `hub_version`
- Update `SkillSourceType` to include `"hub"`

### Phase 2: Provider Abstraction

- Create `HubProvider` ABC with data classes
- Create `HubManager` for multi-hub orchestration

### Phase 3: ClawdHub Provider (CLI Wrapper)

- Check for `clawdhub` CLI availability on init
- Implement search via `clawdhub search` subprocess
- Implement download via `clawdhub install` subprocess
- Parse CLI output into `HubSkillInfo` objects

### Phase 4: SkillHub Provider

- Implement search (`POST /skills/search`)
- Implement catalog listing (`GET /skills/catalog`)
- Handle API key authentication (`Authorization: Bearer <SKILLHUB_API_KEY>` header)

### Phase 5: GitHub Collection Provider

- Parse repo structure for skills
- Use existing `clone_skill_repo()` for downloads
- Client-side search via listing + filtering

### Phase 6: MCP Tools

- `search_hub(query, hub?, limit)` - Cross-hub search
- `list_hubs()` - Show configured hubs and health
- Update `install_skill` for hub references

### Phase 7: CLI Commands

- `gobby skills search <query> [--hub NAME]`
- `gobby skills hub list|add|remove`
- Update `gobby skills install` for `hubname:slug` syntax

## Verification

1. **Unit tests**: Mock subprocess calls for ClawdHub CLI, mock HTTP responses for SkillHub API
2. **Integration test**: Install a skill from ClawdHub (requires `clawdhub` CLI installed)
3. **CLI test**: `gobby skills search "git"` returns results
4. **MCP test**: `search_hub` tool via Claude Code

## Design Decisions

1. **Default hubs**: ClawdHub and SkillHub pre-configured (enabled, no auth required for search/install)
2. **Hub syntax**: Short form `hubname:slug` (e.g., `clawdhub:commit-message`)
3. **Credentials**: Store in `api_keys` section of `config.yaml` with `${ENV_VAR}` expansion
