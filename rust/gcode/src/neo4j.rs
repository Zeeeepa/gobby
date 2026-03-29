//! Neo4j HTTP API client for graph queries.
//!
//! Sends Cypher queries via POST /db/{database}/query/v2 with Basic Auth.
//! Placeholder — full implementation in Sprint 2.

use crate::config::Context;
use crate::models::GraphResult;

/// Placeholder Neo4j client. Returns empty results until Sprint 2.
pub fn find_callers(
    _ctx: &Context,
    _symbol_name: &str,
    _limit: usize,
) -> anyhow::Result<Vec<GraphResult>> {
    Ok(vec![])
}

pub fn find_usages(
    _ctx: &Context,
    _symbol_name: &str,
    _limit: usize,
) -> anyhow::Result<Vec<GraphResult>> {
    Ok(vec![])
}

pub fn get_imports(_ctx: &Context, _file_path: &str) -> anyhow::Result<Vec<GraphResult>> {
    Ok(vec![])
}

pub fn blast_radius(
    _ctx: &Context,
    _target: &str,
    _depth: usize,
) -> anyhow::Result<Vec<GraphResult>> {
    Ok(vec![])
}
