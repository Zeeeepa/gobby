---
name: canvas
description: Instructions for rendering rich A2UI canvas elements to the chat interface. Auto-injected for web UI sessions.
category: core
triggers: canvas, ui, interface, form, a2ui, interactive
conditions:
  - "{{ session.source in ['claude_sdk_web_chat', 'gemini_sdk_web_chat'] }}"
---

# Canvas Frontend Integration

When interacting with a user in the web chat interface, you can render rich interactive elements (forms, layouts, status cards) directly in their chat view using the Canvas tools.

## When to use the Canvas

Use the canvas when you need to:
- Collect multiple pieces of structured input (e.g., a configuration form with checkboxes and text fields).
- Present a complex dashboard or interactive summary.
- Display a rich card with actionable buttons instead of a plain text list.
- Keep the chat clean by replacing long text prompts with a visual form.

## Available Tools

The canvas tools are available through the `gobby-canvas` (or internal MCP) server:

1. `render_surface`: Renders a declarative JSON UI. Pass the root `A2UIComponentDef` tree and an initial `data_model`.
2. `update_surface`: Patches an existing canvas with new components or data.
3. `wait_for_interaction`: Pauses execution until the user interacts with the canvas (e.g., clicking a submit button). Returns the action name and the updated data model.
4. `close_canvas`: Manually closes/completes the canvas when interaction is done.
5. `canvas_present`: Checks if a canvas is currently active for this session.

## A2UI Component System

A2UI is a declarative JSON layout system. Key components include:
- Layouts: `A2UIColumn`, `A2UIRow`, `A2UICard`
- Inputs: `A2UITextField`, `A2UICheckBox`
- Displays: `A2UIText`, `A2UIBadge`, `A2UIIcon`
- Actions: `A2UIButton`

Bindings use JSON pointers (e.g., `#/user/name`).

## Example Workflow

```python
# 1. Render a form
result = call_tool("gobby-canvas", "render_surface", {
    "root_component": {
        "type": "A2UICard",
        "label": "Configuration",
        "children": [
            {
                "type": "A2UITextField",
                "label": "Username",
                "bind": "#/username"
            },
            {
                "type": "A2UIButton",
                "label": "Save",
                "action": "save_config",
                "style": "primary"
            }
        ]
    },
    "data_model": {"username": "admin"}
})

canvas_id = result.get("canvas_id")

# 2. Wait for user to click Save
interaction = call_tool("gobby-canvas", "wait_for_interaction", {
    "canvas_id": canvas_id,
    "timeout": 300
})

if interaction.get("action") == "save_config":
    user_data = interaction.get("data")
    username = user_data.get("username")
    # Process the data...
    
    # 3. Close the canvas
    call_tool("gobby-canvas", "close_canvas", {"canvas_id": canvas_id})
```
