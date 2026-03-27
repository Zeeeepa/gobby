use std::collections::BTreeMap;

use regex::Regex;

use once_cell::sync::Lazy;

/// Group/aggregate lines by mode.
pub fn group_lines(lines: Vec<String>, mode: &str) -> Vec<String> {
    match mode {
        "git_status" => group_git_status(lines),
        "pytest_failures" => group_pytest_failures(lines),
        "test_failures" => group_test_failures(lines),
        "lint_by_rule" => group_lint_by_rule(lines),
        "by_extension" => group_by_extension(lines),
        "by_directory" => group_by_directory(lines),
        "by_file" => group_by_file(lines),
        "errors_warnings" => group_errors_warnings(lines),
        _ => lines,
    }
}

// --- Git status ---

static GIT_STATUS_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"^[\t ]*([MADRCU?! ]{1,2})\s+(.+)$").unwrap());

fn group_git_status(lines: Vec<String>) -> Vec<String> {
    let mut groups: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut order: Vec<String> = Vec::new();
    let mut other: Vec<String> = Vec::new();

    for line in &lines {
        let stripped = line.trim();
        if stripped.is_empty() {
            continue;
        }
        if let Some(caps) = GIT_STATUS_RE.captures(stripped) {
            let status = caps[1].trim().to_string();
            let filename = caps[2].trim().to_string();
            if !groups.contains_key(&status) {
                order.push(status.clone());
            }
            groups.entry(status).or_default().push(filename);
        } else {
            other.push(line.clone());
        }
    }

    let mut result = Vec::new();
    let status_labels: &[(&str, &str)] = &[
        ("M", "Modified"),
        ("A", "Added"),
        ("D", "Deleted"),
        ("R", "Renamed"),
        ("C", "Copied"),
        ("??", "Untracked"),
        ("U", "Unmerged"),
    ];
    let label_map: std::collections::HashMap<&str, &str> =
        status_labels.iter().cloned().collect();

    for status in &order {
        if let Some(files) = groups.get(status) {
            let label = label_map
                .get(status.as_str())
                .copied()
                .unwrap_or(status.as_str());
            result.push(format!("{} ({}):\n", label, files.len()));
            for f in files.iter().take(20) {
                result.push(format!("  {}\n", f));
            }
            if files.len() > 20 {
                result.push(format!("  [... and {} more]\n", files.len() - 20));
            }
        }
    }
    result.extend(other);
    result
}

// --- Pytest failures ---

fn group_pytest_failures(lines: Vec<String>) -> Vec<String> {
    static FAILURES_HEADER: Lazy<Regex> =
        Lazy::new(|| Regex::new(r"^=+ (?:FAILURES|ERRORS) =+").unwrap());
    static SUMMARY_HEADER: Lazy<Regex> =
        Lazy::new(|| Regex::new(r"^=+ short test summary").unwrap());
    static SECTION_BOUNDARY: Lazy<Regex> = Lazy::new(|| Regex::new(r"^=+").unwrap());
    static FINAL_SUMMARY: Lazy<Regex> =
        Lazy::new(|| Regex::new(r"^=+.*(?:passed|failed|error|warning)").unwrap());

    let mut result = Vec::new();
    let mut in_failure_section = false;
    let mut in_summary = false;

    for line in &lines {
        let stripped = line.trim();
        if FAILURES_HEADER.is_match(stripped) {
            in_failure_section = true;
            result.push(line.clone());
            continue;
        }
        if SUMMARY_HEADER.is_match(stripped) {
            in_failure_section = false;
            in_summary = true;
            result.push(line.clone());
            continue;
        }
        if in_summary && SECTION_BOUNDARY.is_match(stripped) {
            result.push(line.clone());
            in_summary = false;
            continue;
        }
        if in_failure_section || in_summary {
            result.push(line.clone());
            continue;
        }
        if FINAL_SUMMARY.is_match(stripped) {
            result.push(line.clone());
        }
    }

    if result.is_empty() {
        return group_test_failures(lines);
    }
    result
}

// --- Generic test failures ---

fn group_test_failures(lines: Vec<String>) -> Vec<String> {
    static FAILURE_MARKERS: Lazy<Vec<Regex>> = Lazy::new(|| {
        vec![
            Regex::new(r"^FAIL").unwrap(),
            Regex::new(r"^FAILED").unwrap(),
            Regex::new(r"^ERROR").unwrap(),
            Regex::new(r"^E\s+").unwrap(),
            Regex::new(r"^---\s*FAIL").unwrap(),
            Regex::new(r"(?i)failures?:").unwrap(),
        ]
    });
    static END_MARKERS: Lazy<Vec<Regex>> = Lazy::new(|| {
        vec![
            Regex::new(r"^=+ ?short test summary").unwrap(),
            Regex::new(r"^=+\s*\d+ (?:passed|failed)").unwrap(),
            Regex::new(r"^FAIL\s*$").unwrap(),
        ]
    });
    static SUMMARY_RE: Lazy<Regex> =
        Lazy::new(|| Regex::new(r"(?i)\d+\s+(?:passed|failed|error)").unwrap());

    let mut result = Vec::new();
    let mut in_failure = false;

    for line in &lines {
        let stripped = line.trim();
        if FAILURE_MARKERS.iter().any(|m| m.is_match(stripped)) {
            in_failure = true;
        }
        if END_MARKERS.iter().any(|m| m.is_match(stripped)) {
            in_failure = true;
        }
        if in_failure {
            result.push(line.clone());
        }
    }

    if result.is_empty() {
        for line in &lines {
            if SUMMARY_RE.is_match(line.trim()) {
                result.push(line.clone());
            }
        }
        if result.is_empty() {
            result.push("All tests passed.\n".into());
        }
    }

    result
}

// --- Lint by rule ---

static LINT_RULE_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"(?::\s*([A-Z]\d{3,4})\s|\[([a-z-]+)\]\s*$|\s{2,}(\S+)\s*$)",
    )
    .unwrap()
});

fn group_lint_by_rule(lines: Vec<String>) -> Vec<String> {
    let mut groups: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut order: Vec<String> = Vec::new();
    let mut other: Vec<String> = Vec::new();

    for line in &lines {
        if let Some(caps) = LINT_RULE_RE.captures(line) {
            let rule = caps
                .get(1)
                .or_else(|| caps.get(2))
                .or_else(|| caps.get(3))
                .map(|m| m.as_str().to_string())
                .unwrap_or_else(|| "unknown".into());
            if !groups.contains_key(&rule) {
                order.push(rule.clone());
            }
            groups.entry(rule).or_default().push(line.clone());
        } else {
            other.push(line.clone());
        }
    }

    if groups.is_empty() {
        return lines;
    }

    let mut result = Vec::new();
    for rule in &order {
        if let Some(rule_lines) = groups.get(rule) {
            result.push(format!("[{}] ({} occurrences):\n", rule, rule_lines.len()));
            for rl in rule_lines.iter().take(5) {
                result.push(format!("  {}\n", rl.trim()));
            }
            if rule_lines.len() > 5 {
                result.push(format!("  [... and {} more]\n", rule_lines.len() - 5));
            }
        }
    }
    result.extend(other);
    result
}

// --- By extension ---

fn group_by_extension(lines: Vec<String>) -> Vec<String> {
    let mut groups: BTreeMap<String, Vec<String>> = BTreeMap::new();

    for line in &lines {
        let stripped = line.trim();
        if stripped.is_empty() {
            continue;
        }
        let last_word = stripped.split_whitespace().last().unwrap_or("");
        let ext = match last_word.rfind('.') {
            Some(pos) => &last_word[pos..],
            None => "(no ext)",
        };
        groups
            .entry(ext.to_string())
            .or_default()
            .push(stripped.to_string());
    }

    if groups.is_empty() {
        return lines;
    }

    // Sort by count descending
    let mut sorted: Vec<_> = groups.into_iter().collect();
    sorted.sort_by(|a, b| b.1.len().cmp(&a.1.len()));

    let mut result = Vec::new();
    for (ext, files) in &sorted {
        let noun = if files.len() == 1 { "file" } else { "files" };
        result.push(format!("{} ({} {}):\n", ext, files.len(), noun));
        for f in files.iter().take(10) {
            result.push(format!("  {}\n", f));
        }
        if files.len() > 10 {
            result.push(format!("  [... and {} more]\n", files.len() - 10));
        }
    }
    result
}

// --- By directory ---

fn group_by_directory(lines: Vec<String>) -> Vec<String> {
    let mut groups: BTreeMap<String, Vec<String>> = BTreeMap::new();

    for line in &lines {
        let stripped = line.trim();
        if stripped.is_empty() {
            continue;
        }
        let dirname = match stripped.rfind('/') {
            Some(pos) => &stripped[..pos],
            None => ".",
        };
        groups
            .entry(dirname.to_string())
            .or_default()
            .push(stripped.to_string());
    }

    if groups.is_empty() {
        return lines;
    }

    let mut sorted: Vec<_> = groups.into_iter().collect();
    sorted.sort_by(|a, b| b.1.len().cmp(&a.1.len()));

    let mut result = Vec::new();
    for (dirname, files) in &sorted {
        let noun = if files.len() == 1 { "item" } else { "items" };
        result.push(format!("{}/ ({} {}):\n", dirname, files.len(), noun));
        for f in files.iter().take(10) {
            result.push(format!("  {}\n", f));
        }
        if files.len() > 10 {
            result.push(format!("  [... and {} more]\n", files.len() - 10));
        }
    }
    result
}

// --- By file (grep-style) ---

static GREP_FILE_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"^([^:]+:\d+):").unwrap());

fn group_by_file(lines: Vec<String>) -> Vec<String> {
    let mut groups: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut order: Vec<String> = Vec::new();
    let mut other: Vec<String> = Vec::new();

    for line in &lines {
        if let Some(caps) = GREP_FILE_RE.captures(line) {
            let filepath = line.split(':').next().unwrap_or("").to_string();
            let _ = caps; // used for matching only
            if !groups.contains_key(&filepath) {
                order.push(filepath.clone());
            }
            groups.entry(filepath).or_default().push(line.clone());
        } else {
            other.push(line.clone());
        }
    }

    if groups.is_empty() {
        return lines;
    }

    let mut result = Vec::new();
    for filepath in &order {
        if let Some(matches) = groups.get(filepath) {
            let noun = if matches.len() == 1 {
                "match"
            } else {
                "matches"
            };
            result.push(format!("{} ({} {}):\n", filepath, matches.len(), noun));
            for ml in matches.iter().take(5) {
                result.push(format!("  {}\n", ml.trim()));
            }
            if matches.len() > 5 {
                result.push(format!("  [... and {} more]\n", matches.len() - 5));
            }
        }
    }
    result.extend(other);
    result
}

// --- Errors and warnings ---

static ERROR_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"(?i)\berror\b").unwrap());
static WARN_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"(?i)\bwarn(?:ing)?\b").unwrap());

fn group_errors_warnings(lines: Vec<String>) -> Vec<String> {
    let mut errors: Vec<String> = Vec::new();
    let mut warnings: Vec<String> = Vec::new();
    let mut other: Vec<String> = Vec::new();

    for line in &lines {
        if ERROR_RE.is_match(line) {
            errors.push(line.clone());
        } else if WARN_RE.is_match(line) {
            warnings.push(line.clone());
        } else {
            other.push(line.clone());
        }
    }

    if errors.is_empty() && warnings.is_empty() {
        return lines;
    }

    let mut result = Vec::new();
    if !errors.is_empty() {
        result.push(format!("Errors ({}):\n", errors.len()));
        result.extend(errors.iter().take(20).cloned());
        if errors.len() > 20 {
            result.push(format!("  [... and {} more errors]\n", errors.len() - 20));
        }
    }
    if !warnings.is_empty() {
        result.push(format!("\nWarnings ({}):\n", warnings.len()));
        result.extend(warnings.iter().take(10).cloned());
        if warnings.len() > 10 {
            result.push(format!(
                "  [... and {} more warnings]\n",
                warnings.len() - 10
            ));
        }
    }
    // Include last few non-error/warning lines (usually summary)
    if !other.is_empty() {
        let start = if other.len() > 3 { other.len() - 3 } else { 0 };
        result.extend(other[start..].iter().cloned());
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_git_status_grouping() {
        let lines = vec![
            " M src/main.rs\n".into(),
            " M src/lib.rs\n".into(),
            "?? new_file.txt\n".into(),
            " D old_file.txt\n".into(),
        ];
        let result = group_git_status(lines);
        assert!(result[0].contains("Modified (2)"));
        assert!(result.iter().any(|l| l.contains("Untracked (1)")));
        assert!(result.iter().any(|l| l.contains("Deleted (1)")));
    }

    #[test]
    fn test_errors_warnings_grouping() {
        let lines = vec![
            "error: something broke\n".into(),
            "warning: deprecated\n".into(),
            "info: all good\n".into(),
            "error: another thing\n".into(),
        ];
        let result = group_errors_warnings(lines);
        assert!(result[0].contains("Errors (2)"));
        assert!(result.iter().any(|l| l.contains("Warnings (1)")));
    }

    #[test]
    fn test_all_tests_passed() {
        let lines = vec![
            "running tests\n".into(),
            "test a ... ok\n".into(),
            "test b ... ok\n".into(),
        ];
        let result = group_test_failures(lines);
        assert_eq!(result, vec!["All tests passed.\n"]);
    }
}
