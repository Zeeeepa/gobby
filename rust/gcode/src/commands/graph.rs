use crate::config::Context;
use crate::neo4j;
use crate::output::{self, Format};

pub fn callers(
    ctx: &Context,
    symbol_name: &str,
    limit: usize,
    format: Format,
) -> anyhow::Result<()> {
    let results = neo4j::find_callers(ctx, symbol_name, limit)?;
    match format {
        Format::Json => output::print_json(&results),
        Format::Text => {
            if results.is_empty() {
                println!("No callers found for '{symbol_name}'");
            } else {
                for r in &results {
                    println!("{}:{} {} -> {}", r.file_path, r.line, r.name, symbol_name);
                }
            }
            Ok(())
        }
    }
}

pub fn usages(
    ctx: &Context,
    symbol_name: &str,
    limit: usize,
    format: Format,
) -> anyhow::Result<()> {
    let results = neo4j::find_usages(ctx, symbol_name, limit)?;
    match format {
        Format::Json => output::print_json(&results),
        Format::Text => {
            if results.is_empty() {
                println!("No usages found for '{symbol_name}'");
            } else {
                for r in &results {
                    let rel = r.relation.as_deref().unwrap_or("unknown");
                    println!(
                        "{}:{} [{}] {} -> {}",
                        r.file_path, r.line, rel, r.name, symbol_name
                    );
                }
            }
            Ok(())
        }
    }
}

pub fn imports(ctx: &Context, file: &str, format: Format) -> anyhow::Result<()> {
    let results = neo4j::get_imports(ctx, file)?;
    match format {
        Format::Json => output::print_json(&results),
        Format::Text => {
            if results.is_empty() {
                println!("No imports found for '{file}'");
            } else {
                for r in &results {
                    println!("{}", r.name);
                }
            }
            Ok(())
        }
    }
}

pub fn blast_radius(
    ctx: &Context,
    target: &str,
    depth: usize,
    format: Format,
) -> anyhow::Result<()> {
    let results = neo4j::blast_radius(ctx, target, depth)?;
    match format {
        Format::Json => output::print_json(&results),
        Format::Text => {
            if results.is_empty() {
                println!("No blast radius found for '{target}'");
            } else {
                for r in &results {
                    let dist = r.distance.unwrap_or(0);
                    println!(
                        "{}:{} [distance={}] {}",
                        r.file_path, r.line, dist, r.name
                    );
                }
            }
            Ok(())
        }
    }
}
