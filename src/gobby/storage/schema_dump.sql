CREATE TABLE schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            repo_path TEXT,
            github_url TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        , github_repo TEXT, linear_team_id TEXT);
CREATE INDEX idx_projects_name ON projects(name);
CREATE TABLE tools (
            id TEXT PRIMARY KEY,
            mcp_server_id TEXT NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            input_schema TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(mcp_server_id, name)
        );
CREATE INDEX idx_tools_server_id ON tools(mcp_server_id);
CREATE INDEX idx_tools_name ON tools(name);
CREATE TABLE IF NOT EXISTS "mcp_servers" (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            transport TEXT NOT NULL,
            url TEXT,
            command TEXT,
            args TEXT,
            env TEXT,
            headers TEXT,
            enabled INTEGER DEFAULT 1,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
CREATE INDEX idx_mcp_servers_name ON mcp_servers(name);
CREATE INDEX idx_mcp_servers_project_id ON mcp_servers(project_id);
CREATE INDEX idx_mcp_servers_enabled ON mcp_servers(enabled);
CREATE UNIQUE INDEX idx_mcp_servers_name_project
            ON mcp_servers(name, project_id);
CREATE TABLE IF NOT EXISTS "sessions" (
            id TEXT PRIMARY KEY,
            external_id TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            source TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id),
            title TEXT,
            status TEXT DEFAULT 'active',
            jsonl_path TEXT,
            summary_path TEXT,
            summary_markdown TEXT,
            git_branch TEXT,
            parent_session_id TEXT REFERENCES sessions(id),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        , transcript_processed BOOLEAN DEFAULT FALSE, compact_markdown TEXT, agent_depth INTEGER DEFAULT 0, spawned_by_agent_id TEXT, workflow_name TEXT, agent_run_id TEXT REFERENCES agent_runs(id) ON DELETE SET NULL, context_injected INTEGER DEFAULT 0, original_prompt TEXT, usage_input_tokens INTEGER DEFAULT 0, usage_output_tokens INTEGER DEFAULT 0, usage_cache_creation_tokens INTEGER DEFAULT 0, usage_cache_read_tokens INTEGER DEFAULT 0, usage_total_cost_usd REAL DEFAULT 0.0, terminal_context TEXT, seq_num INTEGER, model TEXT, had_edits BOOLEAN DEFAULT 0);
CREATE INDEX idx_sessions_external_id ON sessions(external_id);
CREATE INDEX idx_sessions_machine_id ON sessions(machine_id);
CREATE INDEX idx_sessions_source ON sessions(source);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_project_id ON sessions(project_id);
CREATE TABLE task_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            depends_on TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            dep_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, depends_on, dep_type)
        );
CREATE TABLE sqlite_sequence(name,seq);
CREATE INDEX idx_deps_task ON task_dependencies(task_id);
CREATE INDEX idx_deps_depends_on ON task_dependencies(depends_on);
CREATE TABLE session_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(session_id, task_id, action)
        );
CREATE INDEX idx_session_tasks_session ON session_tasks(session_id);
CREATE INDEX idx_session_tasks_task ON session_tasks(task_id);
CREATE TABLE session_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            message_index INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            content_type TEXT DEFAULT 'text',
            tool_name TEXT,
            tool_input TEXT,
            tool_result TEXT,
            timestamp TEXT NOT NULL,
            raw_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(session_id, message_index)
        );
CREATE INDEX idx_session_messages_session ON session_messages(session_id);
CREATE INDEX idx_session_messages_role ON session_messages(role);
CREATE INDEX idx_session_messages_timestamp ON session_messages(timestamp);
CREATE INDEX idx_session_messages_tool ON session_messages(tool_name);
CREATE TABLE session_message_state (
            session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
            last_byte_offset INTEGER DEFAULT 0,
            last_message_index INTEGER DEFAULT 0,
            last_processed_at TEXT,
            processing_errors INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
CREATE INDEX idx_sessions_pending_transcript
            ON sessions(status, transcript_processed)
            WHERE status = 'expired' AND transcript_processed = FALSE;
CREATE TABLE memories (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES projects(id),
            memory_type TEXT NOT NULL,
            content TEXT NOT NULL,
            source_type TEXT,
            source_session_id TEXT REFERENCES sessions(id),
            importance REAL DEFAULT 0.5,
            access_count INTEGER DEFAULT 0,
            last_accessed_at TEXT,
            tags TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        , media TEXT);
CREATE INDEX idx_memories_project ON memories(project_id);
CREATE INDEX idx_memories_type ON memories(memory_type);
CREATE INDEX idx_memories_importance ON memories(importance DESC);
CREATE TABLE session_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(session_id, memory_id, action)
        );
CREATE INDEX idx_session_memories_session ON session_memories(session_id);
CREATE INDEX idx_session_memories_memory ON session_memories(memory_id);
CREATE TABLE tool_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id TEXT NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
            server_name TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            embedding BLOB NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding_dim INTEGER NOT NULL,
            text_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(tool_id)
        );
CREATE INDEX idx_tool_embeddings_tool ON tool_embeddings(tool_id);
CREATE INDEX idx_tool_embeddings_server ON tool_embeddings(server_name);
CREATE INDEX idx_tool_embeddings_project ON tool_embeddings(project_id);
CREATE INDEX idx_tool_embeddings_hash ON tool_embeddings(text_hash);
CREATE TABLE IF NOT EXISTS "tasks" (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id),
            parent_task_id TEXT REFERENCES tasks(id),
            created_in_session_id TEXT REFERENCES sessions(id),
            closed_in_session_id TEXT REFERENCES sessions(id),
            closed_commit_sha TEXT,
            closed_at TEXT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'open',
            priority INTEGER DEFAULT 2,
            task_type TEXT DEFAULT 'task',
            assignee TEXT,
            labels TEXT,
            closed_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            compacted_at TEXT,
            summary TEXT,
            validation_status TEXT CHECK(validation_status IN ('pending', 'valid', 'invalid')),
            validation_feedback TEXT,
            original_instruction TEXT,
            details TEXT,
            category TEXT,
            complexity_score INTEGER,
            estimated_subtasks INTEGER,
            expansion_context TEXT,
            validation_criteria TEXT,
            use_external_validator INTEGER DEFAULT 0,
            validation_fail_count INTEGER DEFAULT 0,
            workflow_name TEXT,
            verification TEXT,
            sequence_order INTEGER
        , validation_override_reason TEXT, commits TEXT, escalated_at TEXT, escalation_reason TEXT, github_issue_number INTEGER, github_pr_number INTEGER, github_repo TEXT, linear_issue_id TEXT, linear_team_id TEXT, seq_num INTEGER, path_cache TEXT, agent_name TEXT, reference_doc TEXT, is_expanded INTEGER DEFAULT 0, requires_user_review INTEGER DEFAULT 0, accepted_by_user INTEGER DEFAULT 0, expansion_status TEXT DEFAULT 'none');
CREATE INDEX idx_tasks_project ON tasks(project_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_parent ON tasks(parent_task_id);
CREATE INDEX idx_tasks_workflow ON tasks(workflow_name);
CREATE INDEX idx_tasks_sequence ON tasks(workflow_name, sequence_order);
CREATE INDEX idx_tasks_created_session ON tasks(created_in_session_id);
CREATE INDEX idx_tasks_closed_session ON tasks(closed_in_session_id);
CREATE TABLE IF NOT EXISTS "workflow_states" (
            session_id TEXT PRIMARY KEY,
            workflow_name TEXT NOT NULL,
            step TEXT NOT NULL,
            step_entered_at TEXT,
            step_action_count INTEGER DEFAULT 0,
            total_action_count INTEGER DEFAULT 0,
            artifacts TEXT,
            observations TEXT,
            reflection_pending INTEGER DEFAULT 0,
            context_injected INTEGER DEFAULT 0,
            variables TEXT,
            task_list TEXT,
            current_task_index INTEGER DEFAULT 0,
            files_modified_this_task INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
CREATE TABLE IF NOT EXISTS "workflow_audit_log" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            step TEXT NOT NULL,
            event_type TEXT NOT NULL,
            tool_name TEXT,
            rule_id TEXT,
            condition TEXT,
            result TEXT NOT NULL,
            reason TEXT,
            context TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
CREATE INDEX idx_audit_session ON workflow_audit_log(session_id);
CREATE INDEX idx_audit_timestamp ON workflow_audit_log(timestamp);
CREATE INDEX idx_audit_event_type ON workflow_audit_log(event_type);
CREATE INDEX idx_audit_result ON workflow_audit_log(result);
CREATE TABLE tool_metrics (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            server_name TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            call_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            total_latency_ms REAL NOT NULL DEFAULT 0,
            avg_latency_ms REAL,
            last_called_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, server_name, tool_name)
        );
CREATE INDEX idx_tool_metrics_project ON tool_metrics(project_id);
CREATE INDEX idx_tool_metrics_server ON tool_metrics(server_name);
CREATE INDEX idx_tool_metrics_tool ON tool_metrics(tool_name);
CREATE INDEX idx_tool_metrics_call_count ON tool_metrics(call_count DESC);
CREATE INDEX idx_tool_metrics_last_called ON tool_metrics(last_called_at);
CREATE TABLE tool_schema_hashes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_name TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            project_id TEXT NOT NULL,
            schema_hash TEXT NOT NULL,
            last_verified_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, server_name, tool_name)
        );
CREATE INDEX idx_schema_hashes_server ON tool_schema_hashes(server_name);
CREATE INDEX idx_schema_hashes_project ON tool_schema_hashes(project_id);
CREATE INDEX idx_schema_hashes_verified ON tool_schema_hashes(last_verified_at);
CREATE TABLE task_validation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            iteration INTEGER NOT NULL,
            status TEXT NOT NULL,
            feedback TEXT,
            issues TEXT,
            context_type TEXT,
            context_summary TEXT,
            validator_type TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
CREATE INDEX idx_validation_history_task ON task_validation_history(task_id);
CREATE TABLE tool_metrics_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            server_name TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            date TEXT NOT NULL,
            call_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            total_latency_ms REAL NOT NULL DEFAULT 0,
            avg_latency_ms REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, server_name, tool_name, date)
        );
CREATE INDEX idx_tool_metrics_daily_project ON tool_metrics_daily(project_id);
CREATE INDEX idx_tool_metrics_daily_date ON tool_metrics_daily(date);
CREATE INDEX idx_tool_metrics_daily_server ON tool_metrics_daily(server_name);
CREATE INDEX idx_sessions_agent_depth ON sessions(agent_depth);
CREATE INDEX idx_sessions_spawned_by ON sessions(spawned_by_agent_id);
CREATE TABLE agent_runs (
            id TEXT PRIMARY KEY,
            parent_session_id TEXT NOT NULL REFERENCES sessions(id),
            child_session_id TEXT REFERENCES sessions(id),
            workflow_name TEXT,
            provider TEXT NOT NULL,
            model TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            prompt TEXT NOT NULL,
            result TEXT,
            error TEXT,
            tool_calls_count INTEGER DEFAULT 0,
            turns_used INTEGER DEFAULT 0,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
CREATE INDEX idx_agent_runs_parent_session ON agent_runs(parent_session_id);
CREATE INDEX idx_agent_runs_child_session ON agent_runs(child_session_id);
CREATE INDEX idx_agent_runs_status ON agent_runs(status);
CREATE INDEX idx_agent_runs_provider ON agent_runs(provider);
CREATE INDEX idx_sessions_workflow ON sessions(workflow_name);
CREATE INDEX idx_sessions_agent_run ON sessions(agent_run_id);
CREATE TABLE worktrees (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
            branch_name TEXT NOT NULL,
            worktree_path TEXT NOT NULL,
            base_branch TEXT DEFAULT 'main',
            agent_session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            merged_at TEXT
        , merge_state TEXT);
CREATE INDEX idx_worktrees_project ON worktrees(project_id);
CREATE INDEX idx_worktrees_status ON worktrees(status);
CREATE INDEX idx_worktrees_task ON worktrees(task_id);
CREATE INDEX idx_worktrees_session ON worktrees(agent_session_id);
CREATE UNIQUE INDEX idx_worktrees_branch ON worktrees(project_id, branch_name);
CREATE UNIQUE INDEX idx_worktrees_path ON worktrees(worktree_path);
CREATE TABLE session_stop_signals (
            session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
            source TEXT NOT NULL,
            reason TEXT,
            requested_at TEXT NOT NULL,
            acknowledged_at TEXT
        );
CREATE INDEX idx_stop_signals_pending
            ON session_stop_signals(acknowledged_at)
            WHERE acknowledged_at IS NULL;
CREATE TABLE loop_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            progress_type TEXT NOT NULL,
            tool_name TEXT,
            details TEXT,
            recorded_at TEXT NOT NULL,
            is_high_value INTEGER NOT NULL DEFAULT 0
        );
CREATE INDEX idx_loop_progress_session
            ON loop_progress(session_id, recorded_at DESC);
CREATE INDEX idx_loop_progress_high_value
            ON loop_progress(session_id, is_high_value, recorded_at DESC)
            WHERE is_high_value = 1;
CREATE TABLE task_selection_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            task_id TEXT NOT NULL,
            selected_at TEXT NOT NULL,
            context TEXT
        );
CREATE INDEX idx_task_selection_session
            ON task_selection_history(session_id, selected_at DESC);
CREATE INDEX idx_task_selection_task
            ON task_selection_history(session_id, task_id, selected_at DESC);
CREATE TABLE session_artifacts (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            artifact_type TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata_json TEXT,
            source_file TEXT,
            line_start INTEGER,
            line_end INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
CREATE INDEX idx_session_artifacts_session ON session_artifacts(session_id);
CREATE INDEX idx_session_artifacts_type ON session_artifacts(artifact_type);
CREATE INDEX idx_session_artifacts_created ON session_artifacts(created_at);
CREATE VIRTUAL TABLE session_artifacts_fts USING fts5(id UNINDEXED, content)
/* session_artifacts_fts(id,content) */;
CREATE TABLE IF NOT EXISTS 'session_artifacts_fts_data'(id INTEGER PRIMARY KEY, block BLOB);
CREATE TABLE IF NOT EXISTS 'session_artifacts_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS 'session_artifacts_fts_content'(id INTEGER PRIMARY KEY, c0, c1);
CREATE TABLE IF NOT EXISTS 'session_artifacts_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB);
CREATE TABLE IF NOT EXISTS 'session_artifacts_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID;
CREATE TABLE merge_resolutions (
            id TEXT PRIMARY KEY,
            worktree_id TEXT NOT NULL REFERENCES worktrees(id) ON DELETE CASCADE,
            source_branch TEXT NOT NULL,
            target_branch TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            tier_used TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
CREATE INDEX idx_merge_resolutions_worktree ON merge_resolutions(worktree_id);
CREATE INDEX idx_merge_resolutions_status ON merge_resolutions(status);
CREATE INDEX idx_merge_resolutions_source_branch ON merge_resolutions(source_branch);
CREATE INDEX idx_merge_resolutions_target_branch ON merge_resolutions(target_branch);
CREATE TABLE merge_conflicts (
            id TEXT PRIMARY KEY,
            resolution_id TEXT NOT NULL REFERENCES merge_resolutions(id) ON DELETE CASCADE,
            file_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            ours_content TEXT,
            theirs_content TEXT,
            resolved_content TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
CREATE INDEX idx_merge_conflicts_resolution ON merge_conflicts(resolution_id);
CREATE INDEX idx_merge_conflicts_file_path ON merge_conflicts(file_path);
CREATE INDEX idx_merge_conflicts_status ON merge_conflicts(status);
CREATE TABLE memory_crossrefs (
            source_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
            target_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
            similarity REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (source_id, target_id)
        );
CREATE INDEX idx_crossrefs_source ON memory_crossrefs(source_id);
CREATE INDEX idx_crossrefs_target ON memory_crossrefs(target_id);
CREATE INDEX idx_crossrefs_similarity ON memory_crossrefs(similarity DESC);
CREATE UNIQUE INDEX idx_tasks_seq_num ON tasks(project_id, seq_num);
CREATE INDEX idx_tasks_path_cache ON tasks(path_cache);
CREATE UNIQUE INDEX idx_sessions_seq_num ON sessions(seq_num);
CREATE UNIQUE INDEX idx_sessions_unique
            ON sessions(external_id, machine_id, source, project_id);
CREATE TABLE inter_session_messages (
            id TEXT PRIMARY KEY,
            from_session TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            to_session TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'normal',
            sent_at TEXT NOT NULL,
            read_at TEXT
        );
CREATE INDEX idx_inter_session_messages_from_session ON inter_session_messages(from_session);
CREATE INDEX idx_inter_session_messages_to_session ON inter_session_messages(to_session);
CREATE INDEX idx_inter_session_messages_unread ON inter_session_messages(to_session, read_at) WHERE read_at IS NULL;
CREATE TABLE skills (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            content TEXT NOT NULL,
            version TEXT,
            license TEXT,
            compatibility TEXT,
            allowed_tools TEXT,
            metadata TEXT,
            source_path TEXT,
            source_type TEXT,
            source_ref TEXT,
            enabled INTEGER DEFAULT 1,
            project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
CREATE INDEX idx_skills_name ON skills(name);
CREATE INDEX idx_skills_project_id ON skills(project_id);
CREATE INDEX idx_skills_enabled ON skills(enabled);
CREATE UNIQUE INDEX idx_skills_name_project ON skills(name, project_id);
CREATE UNIQUE INDEX idx_skills_name_global ON skills(name) WHERE project_id IS NULL;
CREATE TABLE clones (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            branch_name TEXT NOT NULL,
            clone_path TEXT NOT NULL,
            base_branch TEXT DEFAULT 'main',
            task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
            agent_session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
            status TEXT DEFAULT 'active',
            remote_url TEXT,
            last_sync_at TEXT,
            cleanup_after TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
CREATE INDEX idx_clones_project ON clones(project_id);
CREATE INDEX idx_clones_status ON clones(status);
CREATE INDEX idx_clones_task ON clones(task_id);
CREATE INDEX idx_clones_session ON clones(agent_session_id);
CREATE UNIQUE INDEX idx_clones_path ON clones(clone_path);
