use serde::de::{self, MapAccess, Visitor};
use serde::{Deserialize, Deserializer};
use std::collections::BTreeMap;
use std::fmt;
use std::path::{Path, PathBuf};

const DEFAULT_CONFIG: &str = include_str!("../gsqz.yaml");

#[derive(Debug, Clone, Deserialize)]
pub struct Config {
    #[serde(default)]
    pub settings: Settings,
    #[serde(default)]
    pub pipelines: BTreeMap<String, Pipeline>,
    #[serde(default)]
    pub fallback: Fallback,
    #[serde(default)]
    pub excluded_commands: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Settings {
    #[serde(default = "default_min_output_length")]
    pub min_output_length: usize,
    #[serde(default = "default_max_compressed_lines")]
    pub max_compressed_lines: usize,
    #[serde(default)]
    pub daemon_url: Option<String>,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            min_output_length: default_min_output_length(),
            max_compressed_lines: default_max_compressed_lines(),
            daemon_url: None,
        }
    }
}

fn default_min_output_length() -> usize {
    1000
}

fn default_max_compressed_lines() -> usize {
    100
}

#[derive(Debug, Clone, Deserialize)]
pub struct Pipeline {
    #[serde(rename = "match")]
    pub match_pattern: String,
    #[serde(default)]
    pub steps: Vec<Step>,
}

#[derive(Debug, Clone)]
pub enum Step {
    FilterLines(FilterLinesArgs),
    GroupLines(GroupLinesArgs),
    Truncate(TruncateArgs),
    Dedup(DedupArgs),
}

// Custom deserializer: each step is a YAML map with a single key like
// `filter_lines: {patterns: [...]}` or `dedup: {}`
impl<'de> Deserialize<'de> for Step {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct StepVisitor;

        impl<'de> Visitor<'de> for StepVisitor {
            type Value = Step;

            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
                formatter.write_str("a map with a single key: filter_lines, group_lines, truncate, or dedup")
            }

            fn visit_map<A>(self, mut map: A) -> Result<Step, A::Error>
            where
                A: MapAccess<'de>,
            {
                let key: String = map
                    .next_key()?
                    .ok_or_else(|| de::Error::custom("expected a step name"))?;

                let step = match key.as_str() {
                    "filter_lines" => {
                        let args: FilterLinesArgs = map.next_value()?;
                        Step::FilterLines(args)
                    }
                    "group_lines" => {
                        let args: GroupLinesArgs = map.next_value()?;
                        Step::GroupLines(args)
                    }
                    "truncate" => {
                        let args: TruncateArgs = map.next_value()?;
                        Step::Truncate(args)
                    }
                    "dedup" => {
                        let _: serde_yaml::Value = map.next_value()?;
                        Step::Dedup(DedupArgs {})
                    }
                    other => {
                        return Err(de::Error::unknown_variant(
                            other,
                            &["filter_lines", "group_lines", "truncate", "dedup"],
                        ));
                    }
                };

                Ok(step)
            }
        }

        deserializer.deserialize_map(StepVisitor)
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct FilterLinesArgs {
    #[serde(default)]
    pub patterns: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct GroupLinesArgs {
    pub mode: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TruncateArgs {
    #[serde(default = "default_head")]
    pub head: usize,
    #[serde(default = "default_tail")]
    pub tail: usize,
    #[serde(default)]
    pub per_file_lines: usize,
    #[serde(default)]
    pub file_marker: String,
}

fn default_head() -> usize {
    20
}

fn default_tail() -> usize {
    10
}

#[derive(Debug, Clone, Deserialize)]
pub struct DedupArgs {}

#[derive(Debug, Clone, Deserialize)]
pub struct Fallback {
    #[serde(default = "default_fallback_steps")]
    pub steps: Vec<Step>,
}

impl Default for Fallback {
    fn default() -> Self {
        Self {
            steps: default_fallback_steps(),
        }
    }
}

fn default_fallback_steps() -> Vec<Step> {
    vec![Step::Truncate(TruncateArgs {
        head: 20,
        tail: 20,
        per_file_lines: 0,
        file_marker: String::new(),
    })]
}

impl Config {
    /// Load config with layered merging: built-in → global → project → CLI override.
    pub fn load(config_override: Option<&Path>) -> Self {
        let mut config: Config =
            serde_yaml::from_str(DEFAULT_CONFIG).expect("built-in gsqz.yaml is invalid");

        // Layer 2: global config
        if let Some(global_path) = global_config_path() {
            if global_path.exists() {
                merge_from_file(&mut config, &global_path);
            }
        }

        // Layer 3: project config
        if let Some(project_path) = project_config_path() {
            if project_path.exists() {
                merge_from_file(&mut config, &project_path);
            }
        }

        // Layer 4: CLI override
        if let Some(path) = config_override {
            merge_from_file(&mut config, path);
        }

        config
    }

    /// Dump the resolved config as YAML.
    pub fn dump(&self) -> String {
        // Manual dump to avoid serde_yaml output quirks with enums
        let mut out = String::new();
        out.push_str("settings:\n");
        out.push_str(&format!(
            "  min_output_length: {}\n",
            self.settings.min_output_length
        ));
        out.push_str(&format!(
            "  max_compressed_lines: {}\n",
            self.settings.max_compressed_lines
        ));
        if let Some(url) = &self.settings.daemon_url {
            out.push_str(&format!("  daemon_url: \"{}\"\n", url));
        }
        out.push_str(&format!("\npipelines: {} total\n", self.pipelines.len()));
        for (name, pipeline) in &self.pipelines {
            out.push_str(&format!(
                "  {}: match='{}', {} steps\n",
                name,
                pipeline.match_pattern,
                pipeline.steps.len()
            ));
        }
        if !self.excluded_commands.is_empty() {
            out.push_str(&format!(
                "\nexcluded_commands: {:?}\n",
                self.excluded_commands
            ));
        }
        out
    }
}

#[cfg(feature = "gobby")]
fn global_config_path() -> Option<PathBuf> {
    dirs_path(".gobby/gsqz.yaml")
}

#[cfg(not(feature = "gobby"))]
fn global_config_path() -> Option<PathBuf> {
    std::env::var("XDG_CONFIG_HOME")
        .ok()
        .map(PathBuf::from)
        .or_else(|| dirs_path(".config"))
        .map(|p| p.join("gsqz/gsqz.yaml"))
}

#[cfg(feature = "gobby")]
fn project_config_path() -> Option<PathBuf> {
    Some(PathBuf::from(".gobby/gsqz.yaml"))
}

#[cfg(not(feature = "gobby"))]
fn project_config_path() -> Option<PathBuf> {
    Some(PathBuf::from(".gsqz.yaml"))
}

fn dirs_path(suffix: &str) -> Option<PathBuf> {
    std::env::var("HOME")
        .ok()
        .map(|h| PathBuf::from(h).join(suffix))
}

fn merge_from_file(base: &mut Config, path: &Path) {
    let content = match std::fs::read_to_string(path) {
        Ok(c) => c,
        Err(_) => return,
    };
    let overlay: Config = match serde_yaml::from_str(&content) {
        Ok(c) => c,
        Err(_) => return,
    };

    // Merge pipelines (overlay replaces by name, adds new ones)
    for (name, pipeline) in overlay.pipelines {
        base.pipelines.insert(name, pipeline);
    }

    // Merge settings (overlay wins for non-default values)
    if overlay.settings.min_output_length != default_min_output_length() {
        base.settings.min_output_length = overlay.settings.min_output_length;
    }
    if overlay.settings.max_compressed_lines != default_max_compressed_lines() {
        base.settings.max_compressed_lines = overlay.settings.max_compressed_lines;
    }
    if overlay.settings.daemon_url.is_some() {
        base.settings.daemon_url = overlay.settings.daemon_url;
    }

    // Merge excluded commands (additive)
    base.excluded_commands.extend(overlay.excluded_commands);
}
