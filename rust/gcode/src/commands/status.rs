use crate::config::Context;
use crate::output::Format;

pub fn run(_ctx: &Context, _format: Format) -> anyhow::Result<()> {
    eprintln!("gcode status: not yet implemented");
    Ok(())
}

pub fn invalidate(_ctx: &Context) -> anyhow::Result<()> {
    eprintln!("gcode invalidate: not yet implemented");
    Ok(())
}
