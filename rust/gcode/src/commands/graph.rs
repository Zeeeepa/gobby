use crate::config::Context;
use crate::output::{self, Format};

pub fn callers(
    ctx: &Context,
    symbol_name: &str,
    limit: usize,
    format: Format,
) -> anyhow::Result<()> {
    let results = crate::neo4j::find_callers(ctx, symbol_name, limit)?;
    output::print_json(&results)
}

pub fn usages(
    ctx: &Context,
    symbol_name: &str,
    limit: usize,
    format: Format,
) -> anyhow::Result<()> {
    let results = crate::neo4j::find_usages(ctx, symbol_name, limit)?;
    output::print_json(&results)
}

pub fn imports(ctx: &Context, file: &str, format: Format) -> anyhow::Result<()> {
    let results = crate::neo4j::get_imports(ctx, file)?;
    output::print_json(&results)
}

pub fn blast_radius(
    ctx: &Context,
    target: &str,
    depth: usize,
    format: Format,
) -> anyhow::Result<()> {
    let results = crate::neo4j::blast_radius(ctx, target, depth)?;
    output::print_json(&results)
}
