# Workflow Diagrams

This document contains Mermaid diagrams visualizing the Gobby workflow system, based on actual workflow definitions.

## Session Lifecycle (`session-lifecycle.yaml`)

This diagram illustrates the lifecycle triggers and actions that occur during a session, using the `session-lifecycle.yaml` workflow. It shows how context handoff and memory operations are orchestrated at different points in the session.

```mermaid
graph TD
    %% Triggers
    start_event((on_session_start))
    before_agent_event((on_before_agent))
    before_tool_event((on_before_tool))
    stop_event((on_stop))
    pre_compact_event((on_pre_compact))
    end_event((on_session_end))

    %% on_session_start
    subgraph "Session Start"
        start_event --> check_source{Source?}
        check_source -->|clear| inject_prev[Action: inject_context<br/>Previous Session Summary]
        check_source -->|compact| inject_compact[Action: inject_context<br/>Compact Handoff]
        start_event --> mem_import[Action: memory_sync_import]
    end

    %% Interaction Loop
    subgraph "Interaction Loop"
        before_agent_event --> mem_recall[Action: memory_recall_relevant]
        before_tool_event --> req_task[Action: require_active_task]
        stop_event --> req_commit[Action: require_commit_before_stop]
    end

    %% on_session_end
    subgraph "Session End"
        end_event --> check_reason{Reason?}
        check_reason -->|clear| gen_handoff[Action: generate_handoff<br/>Session Summary]
        end_event --> mem_extract[Action: memory_extract]
        end_event --> mem_export[Action: memory_sync_export]
    end

    %% on_pre_compact
    subgraph "Compaction"
        pre_compact_event --> extract_ctx[Action: extract_handoff_context]
        pre_compact_event --> gen_compact[Action: generate_handoff<br/>Compact Mode]
    end

    classDef trigger fill:#f9f,stroke:#333,stroke-width:2px;
    class start_event,before_agent_event,before_tool_event,stop_event,pre_compact_event,end_event trigger;
```

## Autonomous Task (`autonomous-task.yaml`)

This diagram details the state machine for the `autonomous-task` step workflow. It visualizes the flow from activation to completion, including the `work` loop where the agent has full tool access, and the transition to `complete` once the task tree is finished.

```mermaid
stateDiagram-v2
    direction LR

    %% Initial state
    [*] --> work: Activate with session_task

    %% Work Step
    state work {
        [*] --> inject_msg_work
        inject_msg_work: Action inject_message
        inject_msg_work --> working
        working: Allowed Tools ALL

        note right of working
            Agent works autonomously
            until subtasks complete
        end note
    }

    %% Transition
    work --> complete: task_tree_complete(variables.session_task)

    %% Complete Step
    state complete {
        [*] --> inject_msg_complete
        inject_msg_complete: Action inject_message

        note right of inject_msg_complete
            Notifies user of completion
        end note
    }

    %% Exit
    complete --> [*]: Workflow Exit

    %% Premature Stop Handler
    state "Premature Stop Attempt" as stop_attempt
    note right of stop_attempt
        Triggered if agent tries to stop
        while task incomplete
    end note
    stop_attempt --> work: Action guide_continuation
```
