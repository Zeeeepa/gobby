# Skill Hub Registry Abstraction

## Summary

Add a generic hub/registry abstraction to Gobby's skill system that supports multiple skill sources.

## Skill Hub Ecosystem (2026)

| Hub | CLI | Skills | Notes |
|-----|-----|--------|-------|
| [ClawdHub](https://clawdhub.com) | `npx clawdhub` | 500+ | Moltbot's registry, REST API |
| [SkillHub](https://skillhub.club) | `npx @skill-hub/cli` | 7,000+ | AI-evaluated, S/A rankings |
| [SkillCreator.ai](https://skillcreator.ai) | `npx ai-agent-skills` | Dynamic | Creates skills from URLs/docs |
| [n-skills](https://github.com/numman-ali/n-skills) | `openskills` | Curated | GitHub-based marketplace |
| GitHub Collections | git | Varies | Repos like `moltbot/skills` |

## Supported Hubs (Initial Release)

- **ClawdHub** (pre-configured default)
- **SkillHub** (pre-configured default)
- **GitHub Collections** (user-configured)

## API Reference

### ClawdHub API
- **Base**: `https://clawdhub.com`
- **Discovery**: `GET /.well-known/clawdhub.json` → `{apiBase, authBase}`
- **Search**: `GET /api/v1/search?q=<query>&limit=<n>` → `{results: [{slug, displayName, version, score}]}`
- **Details**: `GET /api/v1/skills/<slug>`
- **Download**: `GET /api/v1/download?slug=<slug>&version=<version>` → ZIP
- **Auth**: Bearer token (optional for read, required for publish)

### SkillHub API
- **Base**: `https://www.skillhub.club/api/v1`
- **Search**: `POST /skills/search` body: `{query, limit, category, method}` → `{skills: [...]}`
- **Catalog**: `GET /skills/catalog?limit=<n>&sort=score|stars|recent`
- **Auth**: `x-api-key: sk-sh-...` header (required)
- **Rate limit**: 60 req/min per key

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
|------|---------|
| `src/gobby/skills/hubs/__init__.py` | Module exports |
| `src/gobby/skills/hubs/base.py` | `HubProvider` ABC, data classes |
| `src/gobby/skills/hubs/manager.py` | `HubManager` (multi-hub orchestration) |
| `src/gobby/skills/hubs/clawdhub.py` | ClawdHub REST API provider |
| `src/gobby/skills/hubs/skillhub.py` | SkillHub REST API provider |
| `src/gobby/skills/hubs/github_collection.py` | GitHub repo provider |

## Files to Modify

| Path | Changes |
|------|---------|
| `src/gobby/config/app.py` | Add `HubConfig` model, extend `SkillsConfig` |
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

### Phase 3: ClawdHub Provider
- Implement well-known discovery (`/.well-known/clawdhub.json`)
- Implement search, details, download endpoints
- Handle auth tokens

### Phase 4: SkillHub Provider
- Implement search (`POST /skills/search`)
- Implement catalog listing (`GET /skills/catalog`)
- Handle API key authentication (`x-api-key` header)

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

1. **Unit tests**: Mock HTTP responses for ClawdHub and SkillHub APIs
2. **Integration test**: Install a skill from ClawdHub
3. **CLI test**: `gobby skills search "git"` returns results
4. **MCP test**: `search_hub` tool via Claude Code

## Design Decisions

1. **Default hubs**: ClawdHub and SkillHub pre-configured (enabled, no auth required for search/install)
2. **Hub syntax**: Short form `hubname:slug` (e.g., `clawdhub:commit-message`)
3. **Credentials**: Store in `api_keys` section of `config.yaml` with `${ENV_VAR}` expansion
