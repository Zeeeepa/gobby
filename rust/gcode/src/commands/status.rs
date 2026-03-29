use crate::config::Context;
use crate::db;
use crate::index::indexer;
use crate::models::IndexedProject;
use crate::output::{self, Format};

pub fn run(ctx: &Context, format: Format) -> anyhow::Result<()> {
    let conn = db::open_readonly(&ctx.db_path)?;

    let stats: Option<IndexedProject> = conn
        .query_row(
            "SELECT * FROM code_indexed_projects WHERE id = ?1",
            rusqlite::params![&ctx.project_id],
            |row| {
                Ok(IndexedProject {
                    id: row.get("id")?,
                    root_path: row.get("root_path")?,
                    total_files: row.get::<_, i64>("total_files")? as usize,
                    total_symbols: row.get::<_, i64>("total_symbols")? as usize,
                    last_indexed_at: row.get::<_, Option<String>>("last_indexed_at")?
                        .unwrap_or_default(),
                    index_duration_ms: row.get::<_, i64>("index_duration_ms")? as u64,
                })
            },
        )
        .ok();

    match stats {
        Some(s) => match format {
            Format::Json => output::print_json(&s),
            Format::Text => {
                println!("Project: {}", s.id);
                println!("Root: {}", s.root_path);
                println!("Files: {}", s.total_files);
                println!("Symbols: {}", s.total_symbols);
                println!("Last indexed: {}", s.last_indexed_at);
                println!("Duration: {}ms", s.index_duration_ms);
                Ok(())
            }
        },
        None => {
            eprintln!("No index found for project {}. Run `gcode index` first.", ctx.project_id);
            Ok(())
        }
    }
}

pub fn invalidate(ctx: &Context) -> anyhow::Result<()> {
    let conn = db::open_readwrite(&ctx.db_path)?;
    indexer::invalidate(&conn, &ctx.project_id)
}
