---
name: code-index
description: Instructions for using gobby-code search and retrieval. Auto-injected when project has a code index.
category: core
alwaysApply: true
injectionFormat: full
metadata:
  gobby:
    audience: all
---

# Code Index

This project is indexed in `gobby-code`. Two search modes are available:

## Symbol search (structured)

Before reading large files, prefer symbol-level retrieval:

- `search_symbols(query)` — find symbols by name or description (hybrid: FTS + semantic + graph)
- `get_file_outline(file_path)` — hierarchical symbol map (much cheaper than Read)
- `get_symbol(symbol_id)` — retrieve just the source you need (O(1) via byte offsets)
- `search_text(query)` — search symbol names, signatures, and docstrings

## Content search (full-text)

Search the actual content of all indexed files — comments, string literals, config values, JSX, SQL, etc:

- `search_content(query)` — full-text search across file bodies. Returns file path, line range, and a highlighted snippet. Use this when you need to find arbitrary text that isn't a symbol name.

## When to use which

| Looking for... | Use |
|---|---|
| A function or class by name | `search_symbols` |
| A string literal, config value, comment | `search_content` |
| Structure of a file without reading it | `get_file_outline` |
| Source code of a specific symbol | `get_symbol` |

Discover the full tool list: `list_tools(server_name="gobby-code")`

Symbol-level retrieval saves 90%+ tokens vs reading entire files.
