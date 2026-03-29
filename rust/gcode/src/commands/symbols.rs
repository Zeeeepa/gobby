use crate::config::Context;
use crate::output::Format;

pub fn outline(_ctx: &Context, _file: &str, _format: Format) -> anyhow::Result<()> {
    eprintln!("gcode outline: not yet implemented");
    Ok(())
}

pub fn symbol(_ctx: &Context, _id: &str, _format: Format) -> anyhow::Result<()> {
    eprintln!("gcode symbol: not yet implemented");
    Ok(())
}

pub fn symbols(_ctx: &Context, _ids: &[String], _format: Format) -> anyhow::Result<()> {
    eprintln!("gcode symbols: not yet implemented");
    Ok(())
}

pub fn tree(_ctx: &Context, _format: Format) -> anyhow::Result<()> {
    eprintln!("gcode tree: not yet implemented");
    Ok(())
}
