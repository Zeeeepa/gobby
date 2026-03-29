use crate::config::Context;
use crate::output::Format;

pub fn summary(_ctx: &Context, _symbol_id: &str, _format: Format) -> anyhow::Result<()> {
    eprintln!("gcode summary: not yet implemented");
    Ok(())
}

pub fn repo_outline(_ctx: &Context, _format: Format) -> anyhow::Result<()> {
    eprintln!("gcode repo-outline: not yet implemented");
    Ok(())
}
