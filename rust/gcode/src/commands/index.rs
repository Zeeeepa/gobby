use crate::config::Context;
use crate::db;
use crate::index::indexer;

pub fn run(
    ctx: &Context,
    path: Option<String>,
    files: Option<Vec<String>>,
) -> anyhow::Result<()> {
    let conn = db::open_readwrite(&ctx.db_path)?;
    let root = path
        .as_deref()
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| ctx.project_root.clone());

    if let Some(file_list) = files {
        let result = indexer::index_files(&conn, &root, &ctx.project_id, &file_list)?;
        if !ctx.quiet {
            eprintln!(
                "Indexed {} files, {} symbols in {}ms",
                result.files_indexed, result.symbols_found, result.duration_ms
            );
        }
    } else {
        indexer::index_directory(&conn, &root, &ctx.project_id, true)?;
    }

    Ok(())
}
