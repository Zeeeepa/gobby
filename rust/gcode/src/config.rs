use std::path::{Path, PathBuf};

use anyhow::{Context as _, bail};

/// Resolved runtime context for gcode commands.
pub struct Context {
    /// Path to gobby-hub.db
    pub db_path: PathBuf,
    /// Project root directory
    pub project_root: PathBuf,
    /// Project ID (from .gobby/project.json or DB lookup)
    pub project_id: String,
    /// Suppress warnings
    pub quiet: bool,
}

impl Context {
    /// Resolve context from CLI args and filesystem state.
    pub fn resolve(project_override: Option<&str>, quiet: bool) -> anyhow::Result<Self> {
        let project_root = match project_override {
            Some(p) => PathBuf::from(p).canonicalize()?,
            None => detect_project_root()?,
        };

        let db_path = resolve_db_path()?;
        let project_id = read_project_id(&project_root)?;

        Ok(Self {
            db_path,
            project_root,
            project_id,
            quiet,
        })
    }
}

/// Read database_path from ~/.gobby/bootstrap.yaml, falling back to default.
fn resolve_db_path() -> anyhow::Result<PathBuf> {
    let gobby_dir = dirs::home_dir()
        .context("cannot determine home directory")?
        .join(".gobby");

    let bootstrap_path = gobby_dir.join("bootstrap.yaml");
    if bootstrap_path.exists() {
        let contents = std::fs::read_to_string(&bootstrap_path)?;
        let yaml: serde_yaml::Value = serde_yaml::from_str(&contents)?;
        if let Some(db) = yaml.get("database_path").and_then(|v| v.as_str()) {
            let expanded = db.replace("~", &gobby_dir.parent().unwrap().to_string_lossy());
            return Ok(PathBuf::from(expanded));
        }
    }

    Ok(gobby_dir.join("gobby-hub.db"))
}

/// Walk up from cwd looking for .gobby/project.json.
fn detect_project_root() -> anyhow::Result<PathBuf> {
    let cwd = std::env::current_dir()?;
    let mut dir = cwd.as_path();

    loop {
        if dir.join(".gobby").join("project.json").exists() {
            return Ok(dir.to_path_buf());
        }
        match dir.parent() {
            Some(parent) => dir = parent,
            None => bail!(
                "no .gobby/project.json found (searched from {}). Run `gobby init` first.",
                cwd.display()
            ),
        }
    }
}

/// Read project_id from .gobby/project.json.
fn read_project_id(project_root: &Path) -> anyhow::Result<String> {
    let path = project_root.join(".gobby").join("project.json");
    let contents = std::fs::read_to_string(&path)
        .with_context(|| format!("failed to read {}", path.display()))?;
    let json: serde_json::Value = serde_json::from_str(&contents)?;
    json.get("project_id")
        .and_then(|v| v.as_str())
        .map(String::from)
        .context("project_id not found in .gobby/project.json")
}
