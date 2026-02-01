# CLI Hardening Test Plan

## Overview
Systematic testing of all CLI commands with corresponding MCP tools to ensure consistency and identify issues. Excludes: `start`, `stop`, `restart`, `init`, `install`.

## Test Environment Setup
1. Ensure daemon is running: `gobby start --verbose`
2. Working directory: `/Users/josh/Projects/gobby` (initialized gobby project)
3. Create test data as needed (tasks, sessions, memories, etc.)

---

## 1. Tasks CLI (`gobby tasks`)

### 1.1 `tasks list`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby tasks list` | Lists tasks with tree structure |
| `--status/-s` | `gobby tasks list --status open` | Filters by status |
| `--status` multi | `gobby tasks list --status open,in_progress` | Comma-separated filter works |
| `--active` | `gobby tasks list --active` | Shows open + in_progress |
| `--project/-p` | `gobby tasks list -p gobby` | Filters by project |
| `--assignee/-a` | `gobby tasks list -a session123` | Filters by assignee |
| `--ready` | `gobby tasks list --ready` | Shows unblocked tasks |
| `--blocked` | `gobby tasks list --blocked` | Shows blocked tasks |
| `--limit/-l` | `gobby tasks list -l 5` | Limits output count |
| `--json` | `gobby tasks list --json` | Valid JSON output |
| MCP equivalent | `list_tasks` on gobby-tasks | Compare output structure |

### 1.2 `tasks ready`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby tasks ready` | Lists ready tasks |
| `--limit/-n` | `gobby tasks ready -n 5` | Limits results |
| `--project/-p` | `gobby tasks ready -p gobby` | Filters by project |
| `--priority` | `gobby tasks ready --priority 1` | Filters by priority |
| `--type/-t` | `gobby tasks ready -t bug` | Filters by type |
| `--json` | `gobby tasks ready --json` | Valid JSON output |
| `--flat` | `gobby tasks ready --flat` | No tree hierarchy |
| MCP equivalent | `list_ready_tasks` | Compare results |

### 1.3 `tasks blocked`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby tasks blocked` | Lists blocked tasks |
| `--limit/-n` | `gobby tasks blocked -n 5` | Limits results |
| `--project/-p` | `gobby tasks blocked -p gobby` | Filters by project |
| `--json` | `gobby tasks blocked --json` | Valid JSON with blockers |
| MCP equivalent | `list_blocked_tasks` | Compare results |

### 1.4 `tasks stats`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby tasks stats` | Shows statistics |
| `--project/-p` | `gobby tasks stats -p gobby` | Project-filtered stats |
| `--json` | `gobby tasks stats --json` | Valid JSON output |

### 1.5 `tasks create`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| TITLE arg | `gobby tasks create "Test task"` | Creates task, shows ref |
| `--description/-d` | `gobby tasks create "Test" -d "Description"` | Includes description |
| `--priority/-p` | `gobby tasks create "Test" -p 1` | Sets priority |
| `--type/-t` | `gobby tasks create "Test" -t bug` | Sets task type |
| `--depends-on/-D` | `gobby tasks create "Test" -D "#1"` | Adds dependency |
| `--depends-on` multi | `gobby tasks create "Test" -D "#1" -D "#2"` | Multiple deps |
| MCP equivalent | `create_task` | Compare behavior |

### 1.6 `tasks show`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| TASK arg (#N) | `gobby tasks show #1` | Shows task details |
| TASK arg (UUID) | `gobby tasks show <uuid>` | UUID lookup works |
| MCP equivalent | `get_task` | Compare output fields |

### 1.7 `tasks update`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| TASK arg | `gobby tasks update #1` | No error with no changes |
| `--title/-T` | `gobby tasks update #1 -T "New title"` | Updates title |
| `--status/-s` | `gobby tasks update #1 -s in_progress` | Updates status |
| `--priority` | `gobby tasks update #1 --priority 1` | Updates priority |
| `--assignee/-a` | `gobby tasks update #1 -a sess123` | Updates assignee |
| `--parent` | `gobby tasks update #2 --parent #1` | Sets parent |
| MCP equivalent | `update_task` | Compare behavior |

### 1.8 `tasks close`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| TASK arg | `gobby tasks close #1` | Closes task |
| multi TASK | `gobby tasks close #1 #2 #3` | Closes multiple |
| comma-sep | `gobby tasks close #1,#2,#3` | Comma parsing works |
| `--reason/-r` | `gobby tasks close #1 -r wont_fix` | Sets close reason |
| `--skip-validation` | `gobby tasks close #1 --skip-validation` | Skips checks |
| `--force/-f` | `gobby tasks close #1 -f` | Alias for skip-validation |
| MCP equivalent | `close_task` | Compare behavior |

### 1.9 `tasks reopen`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| TASK arg | `gobby tasks reopen #1` | Reopens closed task |
| `--reason/-r` | `gobby tasks reopen #1 -r "needs more work"` | Sets reason |
| MCP equivalent | `reopen_task` | Compare behavior |

### 1.10 `tasks delete`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| TASK arg | `gobby tasks delete #1` | Prompts, then deletes |
| multi TASK | `gobby tasks delete #1 #2` | Deletes multiple |
| `--cascade/-c` | `gobby tasks delete #1 --cascade` | Deletes children |
| `--unlink/-u` | `gobby tasks delete #1 --unlink` | Removes deps only |
| `--yes/-y` | `gobby tasks delete #1 -y` | Skips confirmation |
| MCP equivalent | `delete_task` | Compare cascade behavior |

### 1.11 `tasks search`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| QUERY arg | `gobby tasks search "auth"` | Returns ranked results |
| `--status/-s` | `gobby tasks search "auth" -s open` | Filters by status |
| `--type/-t` | `gobby tasks search "auth" -t bug` | Filters by type |
| `--priority/-p` | `gobby tasks search "auth" -p 1` | Filters by priority |
| `--project` | `gobby tasks search "auth" --project gobby` | Project filter |
| `--all-projects/-a` | `gobby tasks search "auth" -a` | Searches all |
| `--limit/-n` | `gobby tasks search "auth" -n 5` | Limits results |
| `--min-score` | `gobby tasks search "auth" --min-score 0.3` | Score threshold |
| `--json` | `gobby tasks search "auth" --json` | Valid JSON with scores |
| MCP equivalent | `search_tasks` | Compare ranking |

### 1.12 `tasks reindex`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby tasks reindex` | Rebuilds index |
| `--all-projects/-a` | `gobby tasks reindex -a` | Indexes all projects |
| MCP equivalent | `reindex_tasks` | Compare stats |

### 1.13 `tasks dep add`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| TASK BLOCKER | `gobby tasks dep add #3 #1` | Creates dependency |
| `--type/-t` | `gobby tasks dep add #3 #1 -t related` | Sets dep type |
| MCP equivalent | `add_dependency` | Compare behavior |

### 1.14 `tasks dep remove`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| TASK BLOCKER | `gobby tasks dep remove #3 #1` | Removes dependency |
| MCP equivalent | `remove_dependency` | Compare behavior |

### 1.15 `tasks dep tree`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| TASK arg | `gobby tasks dep tree #1` | Shows blockers/blocking |
| MCP equivalent | `get_dependency_tree` | Compare structure |

### 1.16 `tasks dep cycles`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby tasks dep cycles` | Detects cycles |
| MCP equivalent | `check_dependency_cycles` | Compare results |

### 1.17 `tasks validate`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| TASK arg | `gobby tasks validate #1` | Prompts for summary |
| `--summary/-s` | `gobby tasks validate #1 -s "Fixed bug"` | Uses provided summary |
| `--file/-f` | `gobby tasks validate #1 -f summary.txt` | Reads from file |
| `--max-iterations/-i` | `gobby tasks validate #1 -i 3` | Sets max retries |
| `--external` | `gobby tasks validate #1 --external` | Uses external validator |
| `--skip-build` | `gobby tasks validate #1 --skip-build` | Skips build check |
| `--history` | `gobby tasks validate #1 --history` | Shows history |
| `--recurring` | `gobby tasks validate #1 --recurring` | Shows recurring issues |
| MCP equivalent | `validate_task` | Compare validation |

### 1.18 `tasks generate-criteria`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| TASK arg | `gobby tasks generate-criteria #1` | Generates criteria |
| `--all` | `gobby tasks generate-criteria --all` | Batch generation |
| MCP equivalent | `generate_validation_criteria` | Compare output |

### 1.19 `tasks suggest`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby tasks suggest` | Suggests best task |
| `--type/-t` | `gobby tasks suggest -t bug` | Filters by type |
| `--no-prefer-subtasks` | `gobby tasks suggest --no-prefer-subtasks` | Different scoring |
| `--json` | `gobby tasks suggest --json` | Valid JSON with score |
| MCP equivalent | `suggest_next_task` | Compare suggestion |

### 1.20 `tasks sync`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby tasks sync` | Syncs bidirectionally |
| `--import` | `gobby tasks sync --import` | Import only |
| `--export` | `gobby tasks sync --export` | Export only |
| `--quiet/-q` | `gobby tasks sync -q` | Suppresses output |
| MCP equivalent | `sync_tasks` | Compare behavior |

---

## 2. Sessions CLI (`gobby sessions`)

### 2.1 `sessions list`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby sessions list` | Lists sessions |
| `--project/-p` | `gobby sessions list -p gobby` | Filters by project |
| `--status/-s` | `gobby sessions list -s active` | Filters by status |
| `--source` | `gobby sessions list --source claude_code` | Filters by source |
| `--limit/-n` | `gobby sessions list -n 5` | Limits results |
| `--json` | `gobby sessions list --json` | Valid JSON output |
| MCP equivalent | `list_sessions` | Compare output |

### 2.2 `sessions show`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| SESSION_ID | `gobby sessions show #1` | Shows session details |
| `--json` | `gobby sessions show #1 --json` | Valid JSON output |
| MCP equivalent | `get_session` | Compare fields |

### 2.3 `sessions messages`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| SESSION_ID | `gobby sessions messages #1` | Shows messages |
| `--limit/-n` | `gobby sessions messages #1 -n 10` | Limits messages |
| `--role/-r` | `gobby sessions messages #1 -r user` | Filters by role |
| `--offset/-o` | `gobby sessions messages #1 -o 5` | Skips messages |
| `--json` | `gobby sessions messages #1 --json` | Valid JSON output |
| MCP equivalent | `get_session_messages` | Compare output |

### 2.4 `sessions search`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| QUERY | `gobby sessions search "error"` | Searches messages |
| `--session/-s` | `gobby sessions search "error" -s #1` | Within session |
| `--project/-p` | `gobby sessions search "error" -p gobby` | Within project |
| `--limit/-n` | `gobby sessions search "error" -n 5` | Limits results |
| `--json` | `gobby sessions search "error" --json` | Valid JSON |
| MCP equivalent | `search_messages` | Compare results |

### 2.5 `sessions delete`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| SESSION_ID | `gobby sessions delete #1` | Prompts, deletes |
| MCP equivalent | N/A (no direct MCP) | CLI-only operation |

### 2.6 `sessions stats`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby sessions stats` | Shows statistics |
| `--project/-p` | `gobby sessions stats -p gobby` | Project stats |
| MCP equivalent | `session_stats` | Compare output |

### 2.7 `sessions create-handoff`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby sessions create-handoff` | Creates handoff |
| `--session-id/-s` | `gobby sessions create-handoff -s #1` | Specific session |
| `--compact/-c` | `gobby sessions create-handoff -c` | Compact only |
| `--full` | `gobby sessions create-handoff --full` | Full summary |
| `--output` | `gobby sessions create-handoff --output db` | Output destination |
| `--path` | `gobby sessions create-handoff --path ~/tmp` | File path |
| NOTES arg | `gobby sessions create-handoff "notes"` | Adds notes |
| MCP equivalent | `create_handoff` | Compare output |

---

## 3. Memory CLI (`gobby memory`)

### 3.1 `memory create`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| CONTENT | `gobby memory create "Test fact"` | Creates memory |
| `--type/-t` | `gobby memory create "Test" -t preference` | Sets type |
| `--importance/-i` | `gobby memory create "Test" -i 0.9` | Sets importance |
| `--project/-p` | `gobby memory create "Test" -p gobby` | Sets project |
| MCP equivalent | `create_memory` | Compare behavior |

### 3.2 `memory recall`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| QUERY | `gobby memory recall "test"` | Searches memories |
| `--project/-p` | `gobby memory recall "test" -p gobby` | Project filter |
| `--limit/-n` | `gobby memory recall "test" -n 5` | Limits results |
| `--tags-all` | `gobby memory recall "test" --tags-all "a,b"` | All tags match |
| `--tags-any` | `gobby memory recall "test" --tags-any "a,b"` | Any tag match |
| `--tags-none` | `gobby memory recall --tags-none "exclude"` | Excludes tags |
| MCP equivalent | `search_memories` | Compare results |

### 3.3 `memory list`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby memory list` | Lists memories |
| `--type/-t` | `gobby memory list -t fact` | Filters by type |
| `--min-importance/-i` | `gobby memory list -i 0.5` | Importance threshold |
| `--limit/-n` | `gobby memory list -n 10` | Limits results |
| `--project/-p` | `gobby memory list -p gobby` | Project filter |
| `--tags-all` | `gobby memory list --tags-all "a,b"` | Tag filters |
| MCP equivalent | `list_memories` | Compare output |

### 3.4 `memory show`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| MEMORY_REF | `gobby memory show <id>` | Shows memory details |
| MCP equivalent | `get_memory` | Compare fields |

### 3.5 `memory update`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| MEMORY_REF | `gobby memory update <id>` | No error |
| `--content/-c` | `gobby memory update <id> -c "new"` | Updates content |
| `--importance/-i` | `gobby memory update <id> -i 0.8` | Updates importance |
| `--tags/-t` | `gobby memory update <id> -t "a,b"` | Updates tags |
| MCP equivalent | `update_memory` | Compare behavior |

### 3.6 `memory delete`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| MEMORY_REF | `gobby memory delete <id>` | Deletes memory |
| MCP equivalent | `delete_memory` | Compare behavior |

### 3.7 `memory stats`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby memory stats` | Shows statistics |
| `--project/-p` | `gobby memory stats -p gobby` | Project stats |
| MCP equivalent | `memory_stats` | Compare output |

### 3.8 `memory export`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby memory export` | Exports to stdout |
| `--output/-o` | `gobby memory export -o mem.md` | Exports to file |
| `--no-metadata` | `gobby memory export --no-metadata` | Excludes metadata |
| `--no-stats` | `gobby memory export --no-stats` | Excludes stats |
| `--project/-p` | `gobby memory export -p gobby` | Project filter |

---

## 4. Workflows CLI (`gobby workflows`)

### 4.1 `workflows list`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby workflows list` | Lists workflows |
| `--all/-a` | `gobby workflows list -a` | Includes step-based |
| `--global/-g` | `gobby workflows list -g` | Global only |
| `--json` | `gobby workflows list --json` | Valid JSON |
| MCP equivalent | `list_workflows` | Compare output |

### 4.2 `workflows show`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| NAME | `gobby workflows show plan-mode` | Shows workflow |
| `--json` | `gobby workflows show plan-mode --json` | Valid JSON |
| MCP equivalent | `get_workflow` | Compare output |

### 4.3 `workflows status`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby workflows status` | Shows current state |
| `--session/-s` | `gobby workflows status -s #1` | Specific session |
| `--json` | `gobby workflows status --json` | Valid JSON |
| MCP equivalent | `get_workflow_status` | Compare state |

### 4.4 `workflows set`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| NAME | `gobby workflows set plan-mode` | Activates workflow |
| `--session/-s` | `gobby workflows set plan-mode -s #1` | Specific session |
| `--step/-p` | `gobby workflows set plan-mode -p research` | Initial step |
| MCP equivalent | `activate_workflow` | Compare behavior |

### 4.5 `workflows clear`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby workflows clear` | Prompts, clears |
| `--session/-s` | `gobby workflows clear -s #1` | Specific session |
| `--force/-f` | `gobby workflows clear -f` | Skips confirmation |
| MCP equivalent | `end_workflow` | Compare behavior |

### 4.6 `workflows step`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| STEP_NAME | `gobby workflows step implement` | Transitions step |
| `--session/-s` | `gobby workflows step implement -s #1` | Specific session |
| `--force/-f` | `gobby workflows step implement -f` | Skip checks |
| MCP equivalent | `request_step_transition` | Compare behavior |

### 4.7 `workflows set-var`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| NAME VALUE | `gobby workflows set-var epic "#47"` | Sets variable |
| `--session/-s` | `gobby workflows set-var epic "#47" -s #1` | Specific session |
| `--json` | `gobby workflows set-var epic "#47" --json` | Valid JSON |
| MCP equivalent | `set_variable` | Compare behavior |

### 4.8 `workflows get-var`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| NAME | `gobby workflows get-var epic` | Gets variable |
| (no NAME) | `gobby workflows get-var` | Gets all variables |
| `--session/-s` | `gobby workflows get-var epic -s #1` | Specific session |
| `--json` | `gobby workflows get-var epic --json` | Valid JSON |
| MCP equivalent | `get_variable` | Compare value |

---

## 5. Agents CLI (`gobby agents`)

### 5.1 `agents list`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby agents list` | Lists agent runs |
| `--session/-s` | `gobby agents list -s #1` | By session |
| `--status` | `gobby agents list --status running` | By status |
| `--limit/-n` | `gobby agents list -n 5` | Limits results |
| `--json` | `gobby agents list --json` | Valid JSON |
| MCP equivalent | `list_agents` | Compare output |

### 5.2 `agents show`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| RUN_REF | `gobby agents show <id>` | Shows run details |
| `--json` | `gobby agents show <id> --json` | Valid JSON |
| MCP equivalent | `get_agent_result` | Compare output |

### 5.3 `agents status`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| RUN_REF | `gobby agents status <id>` | Shows status |
| MCP equivalent | `list_running_agents` | Compare state |

### 5.4 `agents stop`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| RUN_REF | `gobby agents stop <id>` | Prompts, stops |
| MCP equivalent | `stop_agent` | Compare behavior |

### 5.5 `agents kill`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| RUN_REF | `gobby agents kill <id>` | Prompts, kills |
| `--force/-f` | `gobby agents kill <id> -f` | SIGKILL |
| `--stop/-s` | `gobby agents kill <id> -s` | Ends workflow |
| `--yes/-y` | `gobby agents kill <id> -y` | Skips confirmation |
| MCP equivalent | `kill_agent` | Compare behavior |

### 5.6 `agents stats`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby agents stats` | Shows statistics |
| `--session/-s` | `gobby agents stats -s #1` | By session |
| MCP equivalent | `running_agent_stats` | Compare output |

---

## 6. Worktrees CLI (`gobby worktrees`)

### 6.1 `worktrees list`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby worktrees list` | Lists worktrees |
| `--status/-s` | `gobby worktrees list -s active` | By status |
| `--project/-p` | `gobby worktrees list -p gobby` | By project |
| `--json` | `gobby worktrees list --json` | Valid JSON |
| MCP equivalent | `list_worktrees` | Compare output |

### 6.2 `worktrees create`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| BRANCH | `gobby worktrees create feature/test` | Creates worktree |
| `--base/-b` | `gobby worktrees create feature/test -b dev` | Base branch |
| `--task/-t` | `gobby worktrees create feature/test -t #1` | Links task |
| `--json` | `gobby worktrees create feature/test --json` | Valid JSON |
| MCP equivalent | `create_worktree` | Compare behavior |

### 6.3 `worktrees show`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| WORKTREE_REF | `gobby worktrees show <id>` | Shows details |
| `--json` | `gobby worktrees show <id> --json` | Valid JSON |
| MCP equivalent | `get_worktree` | Compare output |

### 6.4 `worktrees delete`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| WORKTREE_REF | `gobby worktrees delete <id>` | Prompts, deletes |
| `--force/-f` | `gobby worktrees delete <id> -f` | Force delete |
| `--yes/-y` | `gobby worktrees delete <id> -y` | Skips confirmation |
| MCP equivalent | `delete_worktree` | Compare behavior |

### 6.5 `worktrees sync`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| WORKTREE_REF | `gobby worktrees sync <id>` | Syncs worktree |
| `--source/-s` | `gobby worktrees sync <id> -s main` | Source branch |
| `--json` | `gobby worktrees sync <id> --json` | Valid JSON |
| MCP equivalent | `sync_worktree` | Compare behavior |

### 6.6 `worktrees stale`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby worktrees stale` | Detects stale |
| `--days/-d` | `gobby worktrees stale -d 3` | Custom threshold |
| `--json` | `gobby worktrees stale --json` | Valid JSON |
| MCP equivalent | `detect_stale_worktrees` | Compare output |

### 6.7 `worktrees cleanup`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby worktrees cleanup` | Prompts, cleans |
| `--days/-d` | `gobby worktrees cleanup -d 3` | Custom threshold |
| `--dry-run` | `gobby worktrees cleanup --dry-run` | Preview only |
| `--yes/-y` | `gobby worktrees cleanup -y` | Skips confirmation |
| MCP equivalent | `cleanup_stale_worktrees` | Compare behavior |

### 6.8 `worktrees stats`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby worktrees stats` | Shows statistics |
| `--json` | `gobby worktrees stats --json` | Valid JSON |
| MCP equivalent | `get_worktree_stats` | Compare output |

---

## 7. Skills CLI (`gobby skills`)

### 7.1 `skills list`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby skills list` | Lists skills |
| `--category/-c` | `gobby skills list -c git` | By category |
| `--tags/-t` | `gobby skills list -t "workflow"` | By tags |
| `--enabled/--disabled` | `gobby skills list --enabled` | By status |
| `--limit/-n` | `gobby skills list -n 10` | Limits results |
| `--json` | `gobby skills list --json` | Valid JSON |
| MCP equivalent | `list_skills` | Compare output |

### 7.2 `skills show`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| NAME | `gobby skills show commit` | Shows skill |
| `--json` | `gobby skills show commit --json` | Valid JSON |
| MCP equivalent | `get_skill` | Compare output |

### 7.3 `skills install`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| SOURCE (path) | `gobby skills install ./my-skill` | Installs local |
| SOURCE (github) | `gobby skills install owner/repo` | Installs GitHub |
| `--project/-p` | `gobby skills install ./skill -p` | Project-scoped |
| MCP equivalent | `install_skill` | Compare behavior |

### 7.4 `skills remove`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| NAME | `gobby skills remove my-skill` | Removes skill |
| MCP equivalent | `remove_skill` | Compare behavior |

### 7.5 `skills update`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| NAME | `gobby skills update my-skill` | Updates skill |
| `--all` | `gobby skills update --all` | Updates all |
| MCP equivalent | `update_skill` | Compare behavior |

### 7.6 `skills validate`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| PATH | `gobby skills validate ./SKILL.md` | Validates skill |
| `--json` | `gobby skills validate ./SKILL.md --json` | Valid JSON |

---

## 8. Artifacts CLI (`gobby artifacts`)

### 8.1 `artifacts search`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| QUERY | `gobby artifacts search "error"` | Searches artifacts |
| `--session/-s` | `gobby artifacts search "error" -s #1` | By session |
| `--type/-t` | `gobby artifacts search "error" -t code` | By type |
| `--limit/-n` | `gobby artifacts search "error" -n 5` | Limits results |
| `--json` | `gobby artifacts search "error" --json` | Valid JSON |
| MCP equivalent | `search_artifacts` | Compare output |

### 8.2 `artifacts list`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby artifacts list` | Lists artifacts |
| `--session/-s` | `gobby artifacts list -s #1` | By session |
| `--type/-t` | `gobby artifacts list -t diff` | By type |
| `--limit/-n` | `gobby artifacts list -n 10` | Limits results |
| `--offset/-o` | `gobby artifacts list -o 5` | Pagination |
| `--json` | `gobby artifacts list --json` | Valid JSON |
| MCP equivalent | `list_artifacts` | Compare output |

### 8.3 `artifacts show`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| ARTIFACT_ID | `gobby artifacts show <id>` | Shows artifact |
| `--verbose/-v` | `gobby artifacts show <id> -v` | Shows metadata |
| `--json` | `gobby artifacts show <id> --json` | Valid JSON |
| MCP equivalent | `get_artifact` | Compare output |

### 8.4 `artifacts timeline`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| SESSION_ID | `gobby artifacts timeline #1` | Shows timeline |
| `--type/-t` | `gobby artifacts timeline #1 -t code` | By type |
| `--limit/-n` | `gobby artifacts timeline #1 -n 5` | Limits results |
| `--json` | `gobby artifacts timeline #1 --json` | Valid JSON |
| MCP equivalent | `get_timeline` | Compare output |

---

## 9. Clones CLI (`gobby clones`)

### 9.1 `clones list`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby clones list` | Lists clones |
| `--status/-s` | `gobby clones list -s active` | By status |
| `--project/-p` | `gobby clones list -p <proj>` | By project |
| `--json` | `gobby clones list --json` | Valid JSON |
| MCP equivalent | `list_clones` | Compare output |

### 9.2 `clones create`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| BRANCH PATH | `gobby clones create feature/x /tmp/clone` | Creates clone |
| `--base/-b` | `gobby clones create feature/x /tmp -b dev` | Base branch |
| `--task/-t` | `gobby clones create feature/x /tmp -t #1` | Links task |
| `--json` | `gobby clones create feature/x /tmp --json` | Valid JSON |
| MCP equivalent | `create_clone` | Compare behavior |

### 9.3 `clones sync`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| CLONE_REF | `gobby clones sync <id>` | Syncs clone |
| `--direction/-d` | `gobby clones sync <id> -d push` | Sync direction |
| `--json` | `gobby clones sync <id> --json` | Valid JSON |
| MCP equivalent | `sync_clone` | Compare behavior |

### 9.4 `clones merge`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| CLONE_REF | `gobby clones merge <id>` | Merges clone |
| `--target/-t` | `gobby clones merge <id> -t develop` | Target branch |
| `--json` | `gobby clones merge <id> --json` | Valid JSON |
| MCP equivalent | `merge_clone_to_target` | Compare behavior |

### 9.5 `clones delete`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| CLONE_REF | `gobby clones delete <id>` | Prompts, deletes |
| `--force/-f` | `gobby clones delete <id> -f` | Force delete |
| `--yes/-y` | `gobby clones delete <id> -y` | Skips confirmation |
| `--json` | `gobby clones delete <id> --json` | Valid JSON |
| MCP equivalent | `delete_clone` | Compare behavior |

---

## 10. Merge CLI (`gobby merge`)

### 10.1 `merge start`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| SOURCE_BRANCH | `gobby merge start feature/x` | Starts merge |
| `--target/-t` | `gobby merge start feature/x -t develop` | Target branch |
| `--strategy/-s` | `gobby merge start feature/x -s ai-only` | Strategy |
| `--json` | `gobby merge start feature/x --json` | Valid JSON |
| MCP equivalent | `merge_start` | Compare behavior |

### 10.2 `merge status`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby merge status` | Shows status |
| `--verbose/-v` | `gobby merge status -v` | Shows conflicts |
| `--json` | `gobby merge status --json` | Valid JSON |
| MCP equivalent | `merge_status` | Compare output |

### 10.3 `merge resolve`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| FILE_PATH | `gobby merge resolve src/main.py` | Resolves conflict |
| `--strategy/-s` | `gobby merge resolve src/main.py -s human` | Strategy |
| `--json` | `gobby merge resolve src/main.py --json` | Valid JSON |
| MCP equivalent | `merge_resolve` | Compare behavior |

### 10.4 `merge apply`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby merge apply` | Applies merge |
| `--force/-f` | `gobby merge apply -f` | Force with pending |
| `--json` | `gobby merge apply --json` | Valid JSON |
| MCP equivalent | `merge_apply` | Compare behavior |

### 10.5 `merge abort`
| Flag | Test Command | Success Criteria |
|------|-------------|------------------|
| (none) | `gobby merge abort` | Aborts merge |
| `--json` | `gobby merge abort --json` | Valid JSON |
| MCP equivalent | `merge_abort` | Compare behavior |

---

## Test Execution Order

1. **Setup Phase**
   - Start daemon with verbose logging
   - Create test tasks for task tests
   - Create test memories for memory tests

2. **Read-Only Tests First**
   - `list`, `show`, `stats`, `search` commands
   - Verify output formats (JSON/text)
   - Compare with MCP tool outputs

3. **Mutation Tests**
   - `create`, `update`, `close`, `delete` commands
   - Test flag combinations
   - Verify side effects match MCP behavior

4. **Edge Case Tests**
   - Invalid IDs/refs
   - Missing required args
   - Mutually exclusive flags
   - Empty results

5. **Cleanup**
   - Delete test data
   - Restore original state

---

## Issue Documentation Format

For each issue found, document:

```markdown
### Issue #N: [Brief Title]

**Command:** `gobby <command> <flags>`
**MCP Tool:** `<tool_name>` on `<server>`

**Expected:** <what should happen>
**Actual:** <what actually happens>

**Steps to Reproduce:**
1. ...
2. ...

**Severity:** Critical / High / Medium / Low
**Category:** Crash / Wrong Output / Missing Feature / Inconsistency
```

---

## Verification Checklist

- [ ] All commands execute without crash
- [ ] `--json` flag produces valid JSON for all commands
- [ ] `--help` shows correct flags for all commands
- [ ] MCP tool outputs match CLI outputs structurally
- [ ] Error messages are clear and actionable
- [ ] Exit codes are appropriate (0 success, non-zero error)
- [ ] Confirmations work correctly (`--yes`, `--force`)
- [ ] Filters combine correctly (multiple flags)
