use crate::config::Context;
use crate::output::Format;

pub fn search(
    _ctx: &Context,
    _query: &str,
    _limit: usize,
    _kind: Option<&str>,
    _format: Format,
) -> anyhow::Result<()> {
    eprintln!("gcode search: not yet implemented");
    Ok(())
}

pub fn search_text(
    _ctx: &Context,
    _query: &str,
    _limit: usize,
    _format: Format,
) -> anyhow::Result<()> {
    eprintln!("gcode search-text: not yet implemented");
    Ok(())
}

pub fn search_content(
    _ctx: &Context,
    _query: &str,
    _limit: usize,
    _format: Format,
) -> anyhow::Result<()> {
    eprintln!("gcode search-content: not yet implemented");
    Ok(())
}
