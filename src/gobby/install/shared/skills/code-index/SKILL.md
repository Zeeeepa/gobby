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

This project is indexed in `gobby-code`. Prefer these tools over reading entire files — saves 90%+ tokens.

## Search

- `search_symbols(query)` — find symbols by name or description (hybrid: FTS + semantic + graph)
- `search_text(query)` — search symbol names, signatures, and docstrings
- `search_content(query)` — full-text search across file bodies (comments, strings, config, SQL, etc.)

## Retrieval

- `get_file_outline(file_path)` — hierarchical symbol map (much cheaper than Read)
- `get_symbol(symbol_id)` — retrieve just the source you need (O(1) via byte offsets)
- `get_symbols(symbol_ids)` — batch-retrieve multiple symbols
- `get_summary(symbol_id)` — AI-generated one-line summary (cached)

## Navigation

- `get_repo_outline()` — high-level project summary with module symbol counts
- `get_file_tree()` — file tree with symbol counts per file

## Impact analysis

Use these **before making changes** to understand what you'll affect:

- `blast_radius(symbol_name or file_path)` — walk call/import graph transitively to find all affected code
- `find_callers(symbol_name)` — who calls this function/method?
- `find_usages(symbol_name)` — all usages (calls + imports)
- `get_imports(file_path)` — what does this file import?

## When to use which

| Looking for... | Use |
|---|---|
| A function or class by name | `search_symbols` |
| A string literal, config value, comment | `search_content` |
| Structure of a file without reading it | `get_file_outline` |
| Source code of a specific symbol | `get_symbol` |
| What breaks if I change X | `blast_radius` |
| Who calls a function | `find_callers` |
| All references to a symbol | `find_usages` |
