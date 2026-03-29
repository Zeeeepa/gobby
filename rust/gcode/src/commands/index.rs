use crate::config::Context;

pub fn run(
    _ctx: &Context,
    _path: Option<String>,
    _files: Option<Vec<String>>,
) -> anyhow::Result<()> {
    eprintln!("gcode index: not yet implemented");
    Ok(())
}
