use crate::config::Context;
use crate::db;
use crate::output::{self, Format};
use crate::search::fts;

pub fn search(
    ctx: &Context,
    query: &str,
    limit: usize,
    kind: Option<&str>,
    format: Format,
) -> anyhow::Result<()> {
    // Sprint 1: FTS-only search. Sprint 2 adds semantic + graph boost + RRF.
    let conn = db::open_readonly(&ctx.db_path)?;
    let mut results = fts::search_symbols_fts(&conn, query, &ctx.project_id, kind, limit);
    if results.is_empty() {
        results = fts::search_symbols_by_name(&conn, query, &ctx.project_id, kind, limit);
    }
    let brief: Vec<_> = results.into_iter().map(|s| s.to_brief()).collect();
    match format {
        Format::Json => output::print_json(&brief),
        Format::Text => {
            for r in &brief {
                println!(
                    "{}:{} [{}] {}",
                    r.file_path, r.line_start, r.kind, r.qualified_name
                );
            }
            Ok(())
        }
    }
}

pub fn search_text(
    ctx: &Context,
    query: &str,
    limit: usize,
    format: Format,
) -> anyhow::Result<()> {
    let conn = db::open_readonly(&ctx.db_path)?;
    let results = fts::search_text(&conn, query, &ctx.project_id, limit);
    match format {
        Format::Json => output::print_json(&results),
        Format::Text => {
            for r in &results {
                println!(
                    "{}:{} [{}] {}",
                    r.file_path, r.line_start, r.kind, r.qualified_name
                );
            }
            Ok(())
        }
    }
}

pub fn search_content(
    ctx: &Context,
    query: &str,
    limit: usize,
    format: Format,
) -> anyhow::Result<()> {
    let conn = db::open_readonly(&ctx.db_path)?;
    let results = fts::search_content(&conn, query, &ctx.project_id, limit);
    match format {
        Format::Json => output::print_json(&results),
        Format::Text => {
            for r in &results {
                println!("{}:{}-{} {}", r.file_path, r.line_start, r.line_end, r.snippet);
            }
            Ok(())
        }
    }
}
