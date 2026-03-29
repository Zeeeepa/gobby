use crate::config::Context;
use crate::db;
use crate::models::Symbol;
use crate::output::{self, Format};

pub fn outline(ctx: &Context, file: &str, format: Format) -> anyhow::Result<()> {
    let conn = db::open_readonly(&ctx.db_path)?;
    let mut stmt = conn.prepare(
        "SELECT * FROM code_symbols WHERE project_id = ?1 AND file_path = ?2 ORDER BY line_start",
    )?;
    let symbols: Vec<Symbol> = stmt
        .query_map(rusqlite::params![&ctx.project_id, file], Symbol::from_row)?
        .filter_map(|r| r.ok())
        .collect();

    match format {
        Format::Json => output::print_json(&symbols),
        Format::Text => {
            for s in &symbols {
                let indent = if s.parent_symbol_id.is_some() {
                    "  "
                } else {
                    ""
                };
                println!(
                    "{indent}{}:{} [{}] {}",
                    s.file_path, s.line_start, s.kind, s.qualified_name
                );
            }
            Ok(())
        }
    }
}

pub fn symbol(ctx: &Context, id: &str, format: Format) -> anyhow::Result<()> {
    let conn = db::open_readonly(&ctx.db_path)?;
    let sym: Option<Symbol> = conn
        .query_row(
            "SELECT * FROM code_symbols WHERE id = ?1",
            rusqlite::params![id],
            Symbol::from_row,
        )
        .ok();

    match sym {
        Some(s) => {
            // Read source from file using byte offsets
            let file_path = ctx.project_root.join(&s.file_path);
            if file_path.exists() {
                let source = std::fs::read(&file_path)?;
                let end = s.byte_end.min(source.len());
                let snippet = String::from_utf8_lossy(&source[s.byte_start..end]);
                match format {
                    Format::Json => {
                        let mut result = serde_json::to_value(&s)?;
                        result["source"] = serde_json::Value::String(snippet.to_string());
                        output::print_json(&result)
                    }
                    Format::Text => {
                        println!("{snippet}");
                        Ok(())
                    }
                }
            } else {
                match format {
                    Format::Json => output::print_json(&s),
                    Format::Text => {
                        println!("{}: file not found on disk", s.file_path);
                        Ok(())
                    }
                }
            }
        }
        None => {
            eprintln!("Symbol not found: {id}");
            std::process::exit(1);
        }
    }
}

pub fn symbols(ctx: &Context, ids: &[String], format: Format) -> anyhow::Result<()> {
    let conn = db::open_readonly(&ctx.db_path)?;
    let placeholders: Vec<String> = (1..=ids.len()).map(|i| format!("?{i}")).collect();
    let sql = format!(
        "SELECT * FROM code_symbols WHERE id IN ({})",
        placeholders.join(",")
    );
    let mut stmt = conn.prepare(&sql)?;
    let params: Vec<&dyn rusqlite::types::ToSql> =
        ids.iter().map(|s| s as &dyn rusqlite::types::ToSql).collect();
    let results: Vec<Symbol> = stmt
        .query_map(&*params, Symbol::from_row)?
        .filter_map(|r| r.ok())
        .collect();

    match format {
        Format::Json => output::print_json(&results),
        Format::Text => {
            for s in &results {
                println!(
                    "{}:{} [{}] {}",
                    s.file_path, s.line_start, s.kind, s.qualified_name
                );
            }
            Ok(())
        }
    }
}

pub fn tree(ctx: &Context, format: Format) -> anyhow::Result<()> {
    let conn = db::open_readonly(&ctx.db_path)?;
    let mut stmt = conn.prepare(
        "SELECT file_path, language, symbol_count FROM code_indexed_files \
         WHERE project_id = ?1 ORDER BY file_path",
    )?;

    let files: Vec<serde_json::Value> = stmt
        .query_map(rusqlite::params![&ctx.project_id], |row| {
            Ok(serde_json::json!({
                "file_path": row.get::<_, String>(0)?,
                "language": row.get::<_, String>(1)?,
                "symbol_count": row.get::<_, i64>(2)?,
            }))
        })?
        .filter_map(|r| r.ok())
        .collect();

    match format {
        Format::Json => output::print_json(&files),
        Format::Text => {
            for f in &files {
                println!(
                    "{} [{}] ({} symbols)",
                    f["file_path"].as_str().unwrap_or(""),
                    f["language"].as_str().unwrap_or(""),
                    f["symbol_count"].as_i64().unwrap_or(0),
                );
            }
            Ok(())
        }
    }
}
