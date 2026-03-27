use regex::Regex;

use crate::config::{Config, Step};
use crate::primitives::{dedup, filter, group, truncate};

pub struct CompressionResult {
    pub compressed: String,
    pub original_chars: usize,
    pub compressed_chars: usize,
    pub strategy_name: String,
}

impl CompressionResult {
    pub fn savings_pct(&self) -> f64 {
        if self.original_chars == 0 {
            return 0.0;
        }
        (1.0 - self.compressed_chars as f64 / self.original_chars as f64) * 100.0
    }
}

struct CompiledPipeline {
    name: String,
    regex: Regex,
    steps: Vec<Step>,
}

pub struct Compressor {
    pipelines: Vec<CompiledPipeline>,
    fallback_steps: Vec<Step>,
    excluded: Vec<Regex>,
    min_length: usize,
    max_lines: usize,
}

impl Compressor {
    pub fn new(config: &Config) -> Self {
        let pipelines = config
            .pipelines
            .iter()
            .filter_map(|(name, p)| {
                Regex::new(&p.match_pattern).ok().map(|regex| CompiledPipeline {
                    name: name.clone(),
                    regex,
                    steps: p.steps.clone(),
                })
            })
            .collect();

        let excluded = config
            .excluded_commands
            .iter()
            .filter_map(|p| Regex::new(p).ok())
            .collect();

        Self {
            pipelines,
            fallback_steps: config.fallback.steps.clone(),
            excluded,
            min_length: config.settings.min_output_length,
            max_lines: config.settings.max_compressed_lines,
        }
    }

    pub fn compress(&self, command: &str, output: &str) -> CompressionResult {
        let original_chars = output.len();

        // Skip if too short
        if original_chars < self.min_length {
            return CompressionResult {
                compressed: output.to_string(),
                original_chars,
                compressed_chars: original_chars,
                strategy_name: "passthrough".into(),
            };
        }

        // Skip excluded commands
        if self.excluded.iter().any(|r| r.is_match(command)) {
            return CompressionResult {
                compressed: output.to_string(),
                original_chars,
                compressed_chars: original_chars,
                strategy_name: "excluded".into(),
            };
        }

        // Find matching pipeline
        let mut lines: Vec<String> = output.lines().map(|l| format!("{}\n", l)).collect();
        let mut strategy_name = "fallback".to_string();

        let mut matched = false;
        for pipeline in &self.pipelines {
            if pipeline.regex.is_match(command) {
                strategy_name = pipeline.name.clone();
                lines = apply_steps(lines, &pipeline.steps);
                matched = true;
                break;
            }
        }

        if !matched {
            lines = apply_steps(lines, &self.fallback_steps);
        }

        // Apply max_lines cap
        if self.max_lines > 0 && lines.len() > self.max_lines {
            let cap_head = (self.max_lines * 3) / 5;
            let cap_tail = self.max_lines - cap_head;
            lines = truncate::truncate(lines, cap_head, cap_tail, 0, "");
        }

        let compressed = lines.join("");
        let compressed_chars = compressed.len();

        // If compression produced empty output, pass through
        if compressed.trim().is_empty() {
            return CompressionResult {
                compressed: output.to_string(),
                original_chars,
                compressed_chars: original_chars,
                strategy_name: "passthrough".into(),
            };
        }

        // If compression didn't help much, return original
        if compressed_chars >= (original_chars * 95) / 100 {
            return CompressionResult {
                compressed: output.to_string(),
                original_chars,
                compressed_chars: original_chars,
                strategy_name: "passthrough".into(),
            };
        }

        CompressionResult {
            compressed,
            original_chars,
            compressed_chars,
            strategy_name,
        }
    }
}

fn apply_steps(mut lines: Vec<String>, steps: &[Step]) -> Vec<String> {
    for step in steps {
        lines = match step {
            Step::FilterLines(args) => filter::filter_lines(lines, &args.patterns),
            Step::GroupLines(args) => group::group_lines(lines, &args.mode),
            Step::Truncate(args) => {
                truncate::truncate(lines, args.head, args.tail, args.per_file_lines, &args.file_marker)
            }
            Step::Dedup(_) => dedup::dedup(lines),
        };
    }
    lines
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> Config {
        Config::load(None)
    }

    #[test]
    fn test_passthrough_short_output() {
        let compressor = Compressor::new(&test_config());
        let result = compressor.compress("uv run pytest", "ok");
        assert_eq!(result.strategy_name, "passthrough");
        assert_eq!(result.compressed, "ok");
    }

    #[test]
    fn test_pipeline_match() {
        let compressor = Compressor::new(&test_config());
        let output = (0..200)
            .map(|i| format!("tests/test_{}.py PASSED\n", i))
            .collect::<String>();
        let result = compressor.compress("uv run pytest tests/", &output);
        assert_eq!(result.strategy_name, "pytest");
        assert!(result.compressed_chars < result.original_chars);
    }
}
