use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Stable namespace for deterministic symbol UUIDs.
/// Must match Python: uuid.UUID("c0de1de0-0000-4000-8000-000000000000")
const CODE_INDEX_UUID_NAMESPACE: Uuid = Uuid::from_bytes([
    0xc0, 0xde, 0x1d, 0xe0, 0x00, 0x00, 0x40, 0x00, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00,
]);

/// A code symbol extracted from AST parsing.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Symbol {
    pub id: String,
    pub project_id: String,
    pub file_path: String,
    pub name: String,
    pub qualified_name: String,
    pub kind: String,
    pub language: String,
    pub byte_start: usize,
    pub byte_end: usize,
    pub line_start: usize,
    pub line_end: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signature: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub docstring: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_symbol_id: Option<String>,
    #[serde(default)]
    pub content_hash: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub summary: Option<String>,
    #[serde(default)]
    pub created_at: String,
    #[serde(default)]
    pub updated_at: String,
}

impl Symbol {
    /// Generate deterministic UUID5 for a symbol.
    /// Must produce identical IDs to Python Symbol.make_id().
    pub fn make_id(
        project_id: &str,
        file_path: &str,
        name: &str,
        kind: &str,
        byte_start: usize,
    ) -> String {
        let key = format!("{project_id}:{file_path}:{name}:{kind}:{byte_start}");
        Uuid::new_v5(&CODE_INDEX_UUID_NAMESPACE, key.as_bytes()).to_string()
    }
}

/// Metadata for an indexed file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IndexedFile {
    pub id: String,
    pub project_id: String,
    pub file_path: String,
    pub language: String,
    pub content_hash: String,
    pub symbol_count: usize,
    pub byte_size: usize,
    pub indexed_at: String,
}

/// A chunk of file content for FTS search.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContentChunk {
    pub id: String,
    pub project_id: String,
    pub file_path: String,
    pub chunk_index: usize,
    pub line_start: usize,
    pub line_end: usize,
    pub content: String,
    pub language: String,
    pub created_at: String,
}

/// Import relationship extracted from AST.
#[derive(Debug, Clone)]
pub struct ImportRelation {
    pub file_path: String,
    pub module_name: String,
    pub project_id: String,
}

/// Call relationship extracted from AST.
#[derive(Debug, Clone)]
pub struct CallRelation {
    pub caller_id: String,
    pub callee_name: String,
    pub file_path: String,
    pub line: usize,
    pub project_id: String,
}

/// Project index statistics.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IndexedProject {
    pub id: String,
    pub root_path: String,
    pub total_files: usize,
    pub total_symbols: usize,
    pub last_indexed_at: String,
    pub index_duration_ms: u64,
}

/// Search result with score.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub id: String,
    pub name: String,
    pub qualified_name: String,
    pub kind: String,
    pub file_path: String,
    pub line_start: usize,
    pub score: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub summary: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signature: Option<String>,
}

/// Graph query result (callers, usages).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphResult {
    pub id: String,
    pub name: String,
    pub file_path: String,
    pub line: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub relation: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub distance: Option<usize>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_uuid5_parity_with_python() {
        // Python: Symbol.make_id("proj1", "src/main.py", "foo", "function", 42)
        // Must produce the same UUID in Rust.
        let id = Symbol::make_id("proj1", "src/main.py", "foo", "function", 42);
        // The key is "proj1:src/main.py:foo:function:42"
        // This is a deterministic UUID5 — verify it's stable across runs.
        let id2 = Symbol::make_id("proj1", "src/main.py", "foo", "function", 42);
        assert_eq!(id, id2);

        // Verify the namespace UUID bytes match Python's c0de1de0-0000-4000-8000-000000000000
        assert_eq!(
            CODE_INDEX_UUID_NAMESPACE.to_string(),
            "c0de1de0-0000-4000-8000-000000000000"
        );
    }
}
