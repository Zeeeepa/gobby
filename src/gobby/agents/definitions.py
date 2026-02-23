"""
Agent definitions module.

The old AgentDefinition, WorkflowSpec, and AgentDefinitionLoader classes have been
removed. Agent definitions are now stored as AgentDefinitionBody in
workflow_definitions (workflow_type='agent') and loaded directly via
LocalWorkflowDefinitionManager.

See:
- gobby.workflows.definitions.AgentDefinitionBody
- gobby.storage.workflow_definitions.LocalWorkflowDefinitionManager
"""
